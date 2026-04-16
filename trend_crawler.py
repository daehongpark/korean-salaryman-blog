# -*- coding: utf-8 -*-
"""
trend_crawler.py
────────────────────────────────────────────────────────────
직장인 수익일기 (koreansalaryman.com) - 트렌드 키워드 크롤러
- Google Trends (pytrends)
- Naver DataLab 실시간 트렌드
- 모든 크롤링 실패 시 빈 리스트 반환 → automation.py 쪽에서 KEYWORD_POOL 폴백
────────────────────────────────────────────────────────────
기존 automation.py 는 전혀 건드리지 않고,
이 파일을 같은 폴더에 두고 아래 2~3줄만 automation.py 끝에 추가하면 됩니다.
(추가 스니펫은 하단 주석 참고)
"""

from __future__ import annotations

import logging
import random
import re
import time
from datetime import datetime
from typing import List, Optional

# ─────────────────────────────────────────────────────────
# 로깅 설정 (기존 automation.py 의 logger 와 충돌 없음)
# ─────────────────────────────────────────────────────────
logger = logging.getLogger("trend_crawler")
if not logger.handlers:
    _h = logging.StreamHandler()
    _h.setFormatter(logging.Formatter(
        "[%(asctime)s] %(levelname)s trend_crawler: %(message)s",
        "%Y-%m-%d %H:%M:%S"
    ))
    logger.addHandler(_h)
    logger.setLevel(logging.INFO)


# ─────────────────────────────────────────────────────────
# 1) Google Trends (pytrends)
# ─────────────────────────────────────────────────────────
def fetch_google_trends_kr(top_n: int = 20, timeout: int = 10) -> List[str]:
    """
    한국 구글 실시간 트렌드 키워드를 가져온다.
    실패 시 빈 리스트 반환 (예외 절대 밖으로 던지지 않음).
    """
    try:
        from pytrends.request import TrendReq  # type: ignore
    except ImportError:
        logger.warning("pytrends 미설치 - `pip install pytrends` 필요. 건너뜀.")
        return []

    try:
        pytrends = TrendReq(
            hl="ko-KR",
            tz=540,                # KST
            timeout=(timeout, timeout),
            retries=2,
            backoff_factor=0.3,
        )

        keywords: List[str] = []

        # (a) trending_searches - 국가별 실시간 인기 검색어
        try:
            df = pytrends.trending_searches(pn="south_korea")
            if df is not None and not df.empty:
                keywords.extend([str(x).strip() for x in df[0].tolist() if str(x).strip()])
        except Exception as e:
            logger.info("pytrends.trending_searches 실패: %s", e)

        # (b) today_searches - 오늘의 검색어 (보조 소스)
        if len(keywords) < top_n:
            try:
                tdf = pytrends.today_searches(pn="KR")
                if tdf is not None and len(tdf) > 0:
                    keywords.extend([str(x).strip() for x in list(tdf) if str(x).strip()])
            except Exception as e:
                logger.info("pytrends.today_searches 실패: %s", e)

        # 중복 제거 + 빈 값 제거 + 상위 N개
        seen = set()
        unique = []
        for kw in keywords:
            if kw and kw not in seen:
                seen.add(kw)
                unique.append(kw)
        result = unique[:top_n]
        logger.info("Google Trends 수집: %d개", len(result))
        return result

    except Exception as e:
        logger.warning("Google Trends 크롤링 실패 → 폴백: %s", e)
        return []


# ─────────────────────────────────────────────────────────
# 2) Naver DataLab 급상승 / 쇼핑인사이트 기반 트렌드
# ─────────────────────────────────────────────────────────
_NAVER_UA = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
    "AppleWebKit/537.36 (KHTML, like Gecko) "
    "Chrome/124.0.0.0 Safari/537.36"
)


def fetch_naver_datalab_trends(top_n: int = 20, timeout: int = 10) -> List[str]:
    """
    네이버 데이터랩 공개 페이지에서 트렌드 키워드를 뽑는다.
    공식 API key 가 없을 때도 작동하도록 HTML 파싱 기반.
    실패 시 빈 리스트 반환.
    """
    try:
        import requests  # type: ignore
    except ImportError:
        logger.warning("requests 미설치. 네이버 크롤링 건너뜀.")
        return []

    candidates_urls = [
        "https://datalab.naver.com/keyword/realtimeList.naver?where=main",
        "https://datalab.naver.com/shoppingInsight/sCategory.naver",
    ]

    headers = {
        "User-Agent": _NAVER_UA,
        "Accept-Language": "ko-KR,ko;q=0.9,en-US;q=0.8,en;q=0.7",
        "Referer": "https://datalab.naver.com/",
    }

    collected: List[str] = []

    for url in candidates_urls:
        try:
            resp = requests.get(url, headers=headers, timeout=timeout)
            if resp.status_code != 200:
                logger.info("네이버 %s status=%s", url, resp.status_code)
                continue

            html = resp.text

            # BeautifulSoup 이 있으면 사용, 없으면 정규식 폴백
            try:
                from bs4 import BeautifulSoup  # type: ignore
                soup = BeautifulSoup(html, "html.parser")
                # 가능한 셀렉터 후보들 (네이버가 구조를 자주 바꿈)
                for sel in [
                    "span.item_title",
                    "span.title",
                    "a.keyword",
                    "li.keyword_rank_item",
                    "span.rank_text",
                ]:
                    for tag in soup.select(sel):
                        txt = tag.get_text(strip=True)
                        if txt and 1 < len(txt) <= 30:
                            collected.append(txt)
            except ImportError:
                # BS4 없을 때 간단 정규식
                for m in re.findall(r'"keyword"\s*:\s*"([^"]{2,30})"', html):
                    collected.append(m)
                for m in re.findall(r'class="item_title">\s*([^<]{2,30})\s*<', html):
                    collected.append(m.strip())

            time.sleep(0.3 + random.random() * 0.4)  # 예의상 딜레이

        except Exception as e:
            logger.info("네이버 %s 요청 실패: %s", url, e)
            continue

    # 정제
    cleaned: List[str] = []
    seen = set()
    for kw in collected:
        kw = re.sub(r"\s+", " ", kw).strip()
        if not kw or kw in seen:
            continue
        # 숫자만/특수문자만 된 것 제외
        if re.fullmatch(r"[\d\W_]+", kw):
            continue
        seen.add(kw)
        cleaned.append(kw)

    result = cleaned[:top_n]
    logger.info("Naver DataLab 수집: %d개", len(result))
    return result


# ─────────────────────────────────────────────────────────
# 3) 통합 함수 - automation.py 에서 이것만 호출하면 됨
# ─────────────────────────────────────────────────────────
# 직장인 블로그 타겟 필터: 수익/재테크/커리어/세금/노후 등과 겹치는 키워드에 가중치
_OFFICE_WORKER_HINT = (
    "연봉", "월급", "세금", "재테크", "투자", "주식", "부동산", "청약",
    "연금", "퇴직", "대출", "신용", "카드", "예금", "적금", "ETF",
    "부업", "N잡", "이직", "취업", "면접", "이력서", "커리어",
    "직장", "회사", "사업", "부가세", "종합소득세", "연말정산",
    "청년", "신혼", "전세", "월세", "자취", "결혼", "육아",
)


def _score_keyword_for_office_worker(kw: str) -> int:
    """직장인 블로그 타겟과 관련도 점수(높을수록 우선)."""
    score = 0
    for hint in _OFFICE_WORKER_HINT:
        if hint in kw:
            score += 2
    # 너무 짧거나 숫자뿐인 것 감점
    if len(kw) <= 1:
        score -= 5
    return score


def fetch_trending_keywords(
    top_n: int = 30,
    sources: Optional[List[str]] = None,
) -> List[str]:
    """
    Google + Naver 트렌드를 합쳐 상위 top_n 개 키워드 반환.
    어느 하나라도 실패해도 사용 가능한 것끼리 합쳐 반환.
    전부 실패하면 빈 리스트 반환 → 호출부에서 KEYWORD_POOL 로 폴백.

    sources: ["google", "naver"] 중 선택 (기본 둘 다)
    """
    if sources is None:
        sources = ["google", "naver"]

    merged: List[str] = []

    try:
        if "google" in sources:
            merged.extend(fetch_google_trends_kr(top_n=top_n))
    except Exception as e:
        logger.warning("Google 단계 예외: %s", e)

    try:
        if "naver" in sources:
            merged.extend(fetch_naver_datalab_trends(top_n=top_n))
    except Exception as e:
        logger.warning("Naver 단계 예외: %s", e)

    # 중복 제거 (순서 유지)
    seen = set()
    unique: List[str] = []
    for kw in merged:
        k = kw.strip()
        if k and k not in seen:
            seen.add(k)
            unique.append(k)

    # 직장인 관련도 우선 정렬 (원본 순서는 보조 정렬)
    indexed = list(enumerate(unique))
    indexed.sort(key=lambda x: (-_score_keyword_for_office_worker(x[1]), x[0]))
    sorted_unique = [kw for _, kw in indexed]

    return sorted_unique[:top_n]


# ─────────────────────────────────────────────────────────
# 4) 기존 KEYWORD_POOL 과 병합 + 폴백
# ─────────────────────────────────────────────────────────
def merge_with_pool(
    base_pool: List[str],
    trending: Optional[List[str]] = None,
    trending_ratio: float = 0.5,
    max_total: int = 50,
) -> List[str]:
    """
    base_pool (기존 KEYWORD_POOL) 과 trending 키워드를 섞어서 반환.
    trending 이 비어있으면 base_pool 을 그대로 반환 (완전 폴백).

    trending_ratio: 최종 결과 중 트렌드 키워드가 차지할 비율 (0.0~1.0)
    max_total: 최대 반환 개수
    """
    base_pool = [str(k).strip() for k in (base_pool or []) if str(k).strip()]

    if not trending:
        logger.info("trending 비어있음 → 기존 KEYWORD_POOL 사용 (폴백)")
        return base_pool[:max_total] if base_pool else []

    trending = [str(k).strip() for k in trending if str(k).strip()]

    n_trend = max(1, int(max_total * trending_ratio))
    n_base = max_total - n_trend

    picked_trend = trending[:n_trend]
    picked_base = base_pool[:n_base] if base_pool else []

    # 중복 제거하면서 순서 유지 (트렌드를 앞쪽에)
    seen = set()
    result: List[str] = []
    for kw in picked_trend + picked_base:
        if kw not in seen:
            seen.add(kw)
            result.append(kw)

    # 혹시라도 결과가 비면 최종 안전장치로 base_pool
    if not result:
        return base_pool[:max_total]

    return result[:max_total]


def get_keywords_with_trends(
    base_pool: List[str],
    top_n_trend: int = 30,
    max_total: int = 50,
    trending_ratio: float = 0.5,
) -> List[str]:
    """
    automation.py 의 get_keywords_for_today() 내부에서 호출하기 위한 원스톱 함수.
    - 크롤링 시도
    - 성공하면 병합
    - 실패하면 base_pool 그대로 반환

    사용 예:
        from trend_crawler import get_keywords_with_trends
        keywords = get_keywords_with_trends(KEYWORD_POOL)
    """
    try:
        trending = fetch_trending_keywords(top_n=top_n_trend)
    except Exception as e:
        logger.warning("트렌드 크롤링 전체 실패 → 폴백: %s", e)
        trending = []

    merged = merge_with_pool(
        base_pool=base_pool,
        trending=trending,
        trending_ratio=trending_ratio,
        max_total=max_total,
    )

    if not merged:
        # 정말 모든 게 비어있다면 최후의 안전장치
        logger.error("base_pool 과 trending 모두 비어있음 → 빈 리스트 반환")
        return []

    logger.info(
        "[%s] 최종 키워드 %d개 (트렌드 포함)",
        datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        len(merged),
    )
    return merged


# ─────────────────────────────────────────────────────────
# 단독 실행 시 테스트용
# ─────────────────────────────────────────────────────────
if __name__ == "__main__":
    print("=== Google Trends ===")
    print(fetch_google_trends_kr(top_n=10))
    print("\n=== Naver DataLab ===")
    print(fetch_naver_datalab_trends(top_n=10))
    print("\n=== Merged (with dummy pool) ===")
    dummy_pool = ["연말정산 환급", "직장인 부업", "ETF 추천", "청년 주택청약"]
    print(get_keywords_with_trends(dummy_pool, top_n_trend=15, max_total=20))


# ═════════════════════════════════════════════════════════
# [ automation.py 에 추가할 코드 - 기존 코드는 그대로 두고 아래만 추가 ]
# ═════════════════════════════════════════════════════════
#
# # === 파일 상단 import 근처에 추가 ===
# try:
#     from trend_crawler import get_keywords_with_trends
#     TREND_CRAWLER_AVAILABLE = True
# except Exception as _e:
#     TREND_CRAWLER_AVAILABLE = False
#     print(f"[WARN] trend_crawler import 실패, 기존 KEYWORD_POOL 로 폴백: {_e}")
#
#
# # === 기존 get_keywords_for_today() 함수는 그대로 두고, 아래 함수를 추가 ===
# def get_keywords_for_today_with_trends():
#     """기존 get_keywords_for_today() 를 감싸는 래퍼.
#     트렌드 크롤링 성공 시 병합, 실패 시 기존 동작 그대로."""
#     base = get_keywords_for_today()  # 기존 함수 그대로 호출
#     if not TREND_CRAWLER_AVAILABLE:
#         return base
#     try:
#         return get_keywords_with_trends(
#             base_pool=base,
#             top_n_trend=30,
#             max_total=50,
#             trending_ratio=0.5,
#         )
#     except Exception as _e:
#         print(f"[WARN] 트렌드 병합 실패, 기존 키워드 사용: {_e}")
#         return base
#
# # 이후 본문에서 get_keywords_for_today() 대신
# #     get_keywords_for_today_with_trends()
# # 를 호출하시면 됩니다.
# ═════════════════════════════════════════════════════════