# -*- coding: utf-8 -*-
"""
trend_crawler.py
────────────────────────────────────────────────────────────
직장인 수익일기 - 트렌드 키워드 크롤러 (공식 API 버전)
- 네이버 데이터랩 공식 API (차단 없음)
- Google Trends RSS (공식 피드, 차단 없음)
- 모든 실패 시 기존 KEYWORD_POOL 폴백
────────────────────────────────────────────────────────────
"""

from __future__ import annotations

import logging
import os
import random
import re
import xml.etree.ElementTree as ET
from datetime import datetime
from typing import List, Optional

import requests

logger = logging.getLogger("trend_crawler")
if not logger.handlers:
    _h = logging.StreamHandler()
    _h.setFormatter(logging.Formatter(
        "[%(asctime)s] %(levelname)s trend_crawler: %(message)s",
        "%Y-%m-%d %H:%M:%S"
    ))
    logger.addHandler(_h)
    logger.setLevel(logging.INFO)

# ── 직장인 블로그 관련 키워드 가중치 ─────────────────────
_OFFICE_WORKER_HINT = (
    "연봉", "월급", "세금", "재테크", "투자", "주식", "부동산", "청약",
    "연금", "퇴직", "대출", "신용", "카드", "예금", "적금", "ETF",
    "부업", "N잡", "이직", "취업", "면접", "이력서", "커리어",
    "직장", "회사", "사업", "부가세", "종합소득세", "연말정산",
    "청년", "신혼", "전세", "월세", "자취", "결혼", "육아",
    "블로그", "수익", "자기계발", "독서", "습관", "목표",
)


def _score_keyword(kw: str) -> int:
    score = 0
    for hint in _OFFICE_WORKER_HINT:
        if hint in kw:
            score += 2
    if len(kw) <= 1:
        score -= 5
    return score


# ── 1) 네이버 데이터랩 공식 API ───────────────────────────
def fetch_naver_datalab_trends(top_n: int = 20) -> List[str]:
    """
    네이버 데이터랩 검색어트렌드 공식 API로 인기 키워드 수집.
    환경변수 NAVER_CLIENT_ID, NAVER_CLIENT_SECRET 필요.
    """
    client_id = os.environ.get("NAVER_CLIENT_ID", "")
    client_secret = os.environ.get("NAVER_CLIENT_SECRET", "")

    if not client_id or not client_secret:
        logger.warning("NAVER_CLIENT_ID / NAVER_CLIENT_SECRET 없음 → 건너뜀")
        return []

    # 직장인 관련 주요 카테고리 키워드 그룹으로 트렌드 비교
    keyword_groups = [
        {"groupName": "부업", "keywords": ["부업", "N잡", "재택부업", "온라인부업"]},
        {"groupName": "재테크", "keywords": ["재테크", "주식투자", "ETF", "청약"]},
        {"groupName": "자기계발", "keywords": ["자기계발", "독서", "영어공부", "자격증"]},
        {"groupName": "블로그수익", "keywords": ["블로그수익", "에드센스", "블로그운영"]},
        {"groupName": "직장생활", "keywords": ["이직", "연봉협상", "직장스트레스", "퇴사"]},
    ]

    url = "https://openapi.naver.com/v1/datalab/search"
    headers = {
        "X-Naver-Client-Id": client_id,
        "X-Naver-Client-Secret": client_secret,
        "Content-Type": "application/json",
    }

    from datetime import datetime, timedelta
    end_date = datetime.now().strftime("%Y-%m-%d")
    start_date = (datetime.now() - timedelta(days=7)).strftime("%Y-%m-%d")

    body = {
        "startDate": start_date,
        "endDate": end_date,
        "timeUnit": "date",
        "keywordGroups": keyword_groups,
    }

    try:
        resp = requests.post(url, headers=headers, json=body, timeout=10)
        if resp.status_code != 200:
            logger.warning("네이버 데이터랩 API 오류: %s", resp.status_code)
            return []

        data = resp.json()
        results = data.get("results", [])

        # 최근 ratio 기준으로 정렬 (검색량 높은 순)
        scored = []
        for r in results:
            group_name = r.get("title", "")
            data_points = r.get("data", [])
            if data_points:
                latest_ratio = data_points[-1].get("ratio", 0)
                scored.append((group_name, latest_ratio, r.get("keywords", [])))

        scored.sort(key=lambda x: -x[1])

        keywords = []
        for group_name, ratio, kws in scored:
            keywords.extend(kws)

        logger.info("네이버 데이터랩 API 수집: %d개", len(keywords))
        return keywords[:top_n]

    except Exception as e:
        logger.warning("네이버 데이터랩 API 실패: %s", e)
        return []


# ── 2) Google Trends RSS (공식 피드) ──────────────────────
def fetch_google_trends_rss(top_n: int = 20) -> List[str]:
    """
    구글 트렌드 공식 RSS 피드에서 한국 실시간 트렌드 키워드 수집.
    공식 RSS라 차단 없음.
    """
    url = "https://trends.google.com/trending/rss?geo=KR"
    headers = {
        "User-Agent": "Mozilla/5.0 (compatible; RSS Reader)",
        "Accept": "application/rss+xml, application/xml",
    }

    try:
        resp = requests.get(url, headers=headers, timeout=10)
        if resp.status_code != 200:
            logger.warning("Google Trends RSS 오류: %s", resp.status_code)
            return []

        root = ET.fromstring(resp.content)
        keywords = []

        for item in root.findall(".//item"):
            title = item.find("title")
            if title is not None and title.text:
                kw = title.text.strip()
                if kw and 1 < len(kw) <= 30:
                    keywords.append(kw)

        logger.info("Google Trends RSS 수집: %d개", len(keywords))
        return keywords[:top_n]

    except Exception as e:
        logger.warning("Google Trends RSS 실패: %s", e)
        return []


# ── 3) 통합 함수 ──────────────────────────────────────────
def fetch_trending_keywords(top_n: int = 30) -> List[str]:
    """네이버 + 구글 트렌드 통합 수집"""
    merged = []

    try:
        merged.extend(fetch_google_trends_rss(top_n=top_n))
    except Exception as e:
        logger.warning("Google RSS 단계 예외: %s", e)

    try:
        merged.extend(fetch_naver_datalab_trends(top_n=top_n))
    except Exception as e:
        logger.warning("Naver API 단계 예외: %s", e)

    # 중복 제거
    seen = set()
    unique = []
    for kw in merged:
        k = kw.strip()
        if k and k not in seen:
            seen.add(k)
            unique.append(k)

    # 직장인 관련도 우선 정렬
    indexed = list(enumerate(unique))
    indexed.sort(key=lambda x: (-_score_keyword(x[1]), x[0]))
    sorted_unique = [kw for _, kw in indexed]

    logger.info("통합 트렌드 키워드: %d개", len(sorted_unique))
    return sorted_unique[:top_n]


def get_keywords_with_trends(
    base_pool: List[str],
    top_n_trend: int = 30,
    max_total: int = 50,
    trending_ratio: float = 0.5,
) -> List[str]:
    """
    automation.py에서 호출하는 메인 함수.
    트렌드 키워드 + 기존 키워드풀 병합 반환.
    실패 시 base_pool 그대로 반환.
    """
    try:
        trending = fetch_trending_keywords(top_n=top_n_trend)
    except Exception as e:
        logger.warning("트렌드 크롤링 실패 → 폴백: %s", e)
        trending = []

    if not trending:
        logger.info("트렌드 없음 → 기존 KEYWORD_POOL 사용")
        return base_pool

    # 병합
    n_trend = max(1, int(max_total * trending_ratio))
    n_base = max_total - n_trend

    picked_trend = trending[:n_trend]
    picked_base = base_pool[:n_base] if base_pool else []

    seen = set()
    result = []
    for kw in picked_trend + picked_base:
        if kw not in seen:
            seen.add(kw)
            result.append(kw)

    if not result:
        return base_pool

    logger.info(
        "[%s] 최종 키워드 %d개 (트렌드 포함)",
        datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        len(result),
    )
    return result[:max_total]


# ── 단독 테스트 ───────────────────────────────────────────
if __name__ == "__main__":
    print("=== Google Trends RSS ===")
    print(fetch_google_trends_rss(top_n=10))
    print("\n=== 네이버 데이터랩 API ===")
    print(fetch_naver_datalab_trends(top_n=10))
    print("\n=== 통합 결과 ===")
    dummy_pool = ["직장인 부업", "ETF 추천", "연말정산", "블로그 수익"]
    print(get_keywords_with_trends(dummy_pool, top_n_trend=15, max_total=20))
