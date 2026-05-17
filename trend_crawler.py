# -*- coding: utf-8 -*-
"""
trend_crawler.py (v2.0)
────────────────────────────────────────────────────────────
직장인 수익일기 - SEO 최적화 키워드 분석 시스템

[데이터 소스]
1. 네이버 검색광고 API     — 월 검색량, 경쟁도, 모바일 비율 (SEO 핵심)
2. 네이버 개발자센터 API   — 블로그/웹 검색 결과 개수 (경쟁도 보조)
3. 네이버 데이터랩 API     — 검색어 트렌드 (상승세 파악)
4. 네이버 자동완성         — 롱테일 키워드 수집
5. 구글 자동완성           — 보조 롱테일
6. Google Trends RSS       — 실시간 트렌드

[핵심 기능]
- 시드 키워드 → 수십~수백 개 확장
- 각 키워드에 SEO 점수 부여
- 노출에 가장 유리한 키워드 자동 선별
────────────────────────────────────────────────────────────
"""

from __future__ import annotations

import hashlib
import hmac
import base64
import logging
import os
import random
import re
import time
import json
import urllib.parse
import xml.etree.ElementTree as ET
from datetime import datetime, timedelta
from typing import List, Dict, Tuple, Optional

import requests

# ── 로깅 ──────────────────────────────────────────────────
logger = logging.getLogger("trend_crawler")
if not logger.handlers:
    _h = logging.StreamHandler()
    _h.setFormatter(logging.Formatter(
        "[%(asctime)s] %(levelname)s trend_crawler: %(message)s",
        "%Y-%m-%d %H:%M:%S"
    ))
    logger.addHandler(_h)
    logger.setLevel(logging.INFO)

# ── 환경 변수 ─────────────────────────────────────────────
NAVER_CLIENT_ID     = os.environ.get("NAVER_CLIENT_ID", "")
NAVER_CLIENT_SECRET = os.environ.get("NAVER_CLIENT_SECRET", "")
NAVER_AD_API_KEY    = os.environ.get("NAVER_AD_API_KEY", "")       # 엑세스라이선스
NAVER_AD_SECRET_KEY = os.environ.get("NAVER_AD_SECRET_KEY", "")    # 비밀키
NAVER_CUSTOMER_ID   = os.environ.get("NAVER_CUSTOMER_ID", "")      # CUSTOMER_ID

# ── 직장인 블로그 관련 키워드 가중치 (2026 신규 6개 카테고리 반영) ──
_OFFICE_WORKER_HINT = (
    # 정부지원금/정책
    "지원금", "정책", "장려금", "보조금", "바우처", "수당", "환급",
    "청년", "신혼", "소상공인", "창업", "공제", "감면", "특별지원",
    "도약계좌", "내일채움", "디딤돌", "버팀목", "행복주택", "복지",
    "정부24", "복지로", "youthcenter", "bizinfo",
    # AI 도구
    "Claude", "ChatGPT", "Gemini", "Perplexity", "Cursor", "AI", "GPT",
    "프롬프트", "자동화", "챗봇", "n8n", "Zapier", "Make", "노션AI",
    # 직장인 커리어
    "연봉", "월급", "이직", "취업", "면접", "이력서", "커리어",
    "직장", "회사", "사업", "부가세", "종합소득세", "연말정산",
    "퇴직", "퇴사", "재택근무", "유연근무",
    # 재테크/투자
    "재테크", "투자", "주식", "ETF", "ISA", "IRP", "연금저축",
    "예금", "적금", "월배당", "S&P500", "나스닥", "TIGER", "KODEX",
    "환율", "금리", "기준금리",
    # 부동산/주거
    "부동산", "청약", "전세", "월세", "임차", "임대", "전월세",
    "DSR", "LTV", "취득세", "양도세", "보증금", "주택", "분양",
    "디딤돌대출", "버팀목", "신혼희망타운", "역세권청년주택",
    # 실시간 이슈
    "시행", "개정", "발표", "인상", "도입", "변경",
    # 일반 (기존 유지)
    "노후", "보험", "절약", "파이어족", "경제적자유",
)

# ── 차단 키워드 (블로그 무관) ───────────────────────────
_BLOCKED_HINT = (
    "아이돌", "배우", "가수", "드라마", "영화", "예능", "스포츠",
    "선거", "정치", "대통령", "사망", "사건", "사고", "범죄",
    "날씨", "태풍", "야구", "축구",
)


# ═══════════════════════════════════════════════════════
#  카테고리별 데이터랩 트렌드 그룹 (박대홍 7카테고리 매핑)
#  각 카테고리당 4~6개 대표 키워드로 그룹 구성.
#  네이버 데이터랩이 그룹별 검색 트렌드 비율을 반환 → 어떤 키워드가 지금 뜨는지 판단.
# ═══════════════════════════════════════════════════════
CATEGORY_DATALAB_GROUPS = {
    "money": [
        {"groupName": "청년정책",    "keywords": ["청년도약계좌", "청년월세지원", "청년내일채움공제", "청년창업지원금"]},
        {"groupName": "근로지원",    "keywords": ["근로장려금", "자녀장려금", "중소기업 청년 소득세 감면"]},
        {"groupName": "복지지원",    "keywords": ["에너지바우처", "긴급복지지원", "기초연금"]},
        {"groupName": "소상공인",    "keywords": ["소상공인 정책자금", "예비창업패키지", "청년창업사관학교"]},
    ],
    "ai": [
        {"groupName": "AI챗봇",      "keywords": ["ChatGPT", "Claude", "Gemini", "Perplexity"]},
        {"groupName": "AI코딩",      "keywords": ["Cursor AI", "Claude Code", "GitHub Copilot"]},
        {"groupName": "AI자동화",    "keywords": ["n8n", "Zapier", "Make"]},
        {"groupName": "AI업무",      "keywords": ["AI 보고서", "AI 엑셀", "프롬프트 엔지니어링"]},
    ],
    "startup": [
        {"groupName": "사업자등록",  "keywords": ["사업자등록", "1인 사업자", "간이과세자", "일반과세자"]},
        {"groupName": "직장인부업",  "keywords": ["직장인 부업", "N잡", "재택부업", "회사 적발"]},
        {"groupName": "세무신고",    "keywords": ["부가가치세 신고", "종합소득세 신고", "프리랜서 세금"]},
        {"groupName": "사업운영",    "keywords": ["사업자 통장", "사업용 카드", "비용처리"]},
    ],
    "finance": [
        {"groupName": "ETF투자",     "keywords": ["S&P500 ETF", "나스닥100 ETF", "TIGER ETF", "KODEX ETF"]},
        {"groupName": "연금세제",    "keywords": ["ISA 계좌", "연금저축", "IRP", "세액공제"]},
        {"groupName": "적금저축",    "keywords": ["고금리 적금", "파킹통장", "청년도약계좌 수익률"]},
        {"groupName": "환율금리",    "keywords": ["원달러 환율", "미국 금리", "한국은행 기준금리"]},
    ],
    "realestate": [
        {"groupName": "주택청약",    "keywords": ["주택청약 1순위", "특별공급", "공공분양", "청약가점"]},
        {"groupName": "전월세",      "keywords": ["전세대출", "디딤돌대출", "버팀목전세자금대출", "보증금 반환"]},
        {"groupName": "주거지원",    "keywords": ["행복주택", "역세권청년주택", "신혼희망타운"]},
        {"groupName": "부동산세제",  "keywords": ["DSR 규제", "양도세 비과세", "취득세"]},
    ],
    "trending": [
        {"groupName": "커리어이직",  "keywords": ["연봉 인상률", "이직", "성과급", "경력직"]},
        {"groupName": "직장문화",    "keywords": ["MZ세대 직장", "회식 문화", "주4일제", "재택근무"]},
        {"groupName": "건강번아웃",  "keywords": ["직장인 번아웃", "직장인 운동", "직장인 정신건강"]},
        {"groupName": "가족정책",    "keywords": ["육아휴직", "맞벌이 세금", "신혼부부 정책"]},
        {"groupName": "정책핫이슈",  "keywords": ["2026 정책", "세법 개정", "연말정산"]},
    ],
    # book은 트렌드 추적 의미 낮음 (장기 콘텐츠) → 카테고리 매핑 제외
}


# ═══════════════════════════════════════════════════════
#  1. 네이버 검색광고 API (가장 강력)
# ═══════════════════════════════════════════════════════

def _ad_api_signature(timestamp: str, method: str, uri: str) -> str:
    """검색광고 API 인증용 HMAC-SHA256 서명 생성"""
    message = f"{timestamp}.{method}.{uri}"
    signature = hmac.new(
        NAVER_AD_SECRET_KEY.encode("utf-8"),
        message.encode("utf-8"),
        hashlib.sha256
    ).digest()
    return base64.b64encode(signature).decode("utf-8")


def _ad_api_headers(method: str, uri: str) -> dict:
    """검색광고 API 호출용 인증 헤더"""
    timestamp = str(int(time.time() * 1000))
    return {
        "Content-Type":      "application/json; charset=UTF-8",
        "X-Timestamp":       timestamp,
        "X-API-KEY":         NAVER_AD_API_KEY,
        "X-Customer":        NAVER_CUSTOMER_ID,
        "X-Signature":       _ad_api_signature(timestamp, method, uri),
    }


def get_keyword_metrics(keywords: List[str]) -> Dict[str, dict]:
    """
    네이버 검색광고 API로 키워드 지표 조회.
    
    반환: { "직장인 부업": {
              "monthly_pc": 2500,            # PC 월 검색량
              "monthly_mobile": 8700,        # 모바일 월 검색량
              "monthly_total": 11200,        # 총 월 검색량
              "mobile_ratio": 0.78,          # 모바일 비율
              "competition": "높음",          # 경쟁도
              "ad_count": 15,                 # 월평균 노출 광고 수
            }, ... }
    """
    if not all([NAVER_AD_API_KEY, NAVER_AD_SECRET_KEY, NAVER_CUSTOMER_ID]):
        logger.warning("검색광고 API 키 없음 → 건너뜀")
        return {}
    
    if not keywords:
        return {}

    # API는 한 번에 최대 5개 키워드 처리
    result = {}
    for i in range(0, len(keywords), 5):
        batch = keywords[i:i+5]
        # 공백 제거 필요 (API 제약)
        clean_batch = [kw.replace(" ", "") for kw in batch]
        
        uri = "/keywordstool"
        # hintKeywords는 쉼표 구분 문자열
        params = {
            "hintKeywords": ",".join(clean_batch),
            "showDetail":   "1",
        }
        full_uri = uri + "?" + urllib.parse.urlencode(params)
        url = "https://api.searchad.naver.com" + full_uri
        
        try:
            headers = _ad_api_headers("GET", uri)
            resp = requests.get(url, headers=headers, timeout=15)
            
            if resp.status_code != 200:
                logger.warning(f"검색광고 API 오류 ({resp.status_code}): {resp.text[:200]}")
                time.sleep(1)
                continue
            
            data = resp.json()
            for item in data.get("keywordList", []):
                kw = item.get("relKeyword", "")
                if not kw:
                    continue
                
                # 검색량 파싱 (문자열 "< 10" 나오면 5로 처리)
                def _parse_count(v):
                    if isinstance(v, (int, float)):
                        return int(v)
                    if isinstance(v, str):
                        v = v.replace(",", "").strip()
                        if v.startswith("<"):
                            return 5
                        try:
                            return int(v)
                        except ValueError:
                            return 0
                    return 0
                
                pc     = _parse_count(item.get("monthlyPcQcCnt", 0))
                mobile = _parse_count(item.get("monthlyMobileQcCnt", 0))
                total  = pc + mobile
                
                result[kw] = {
                    "monthly_pc":     pc,
                    "monthly_mobile": mobile,
                    "monthly_total":  total,
                    "mobile_ratio":   (mobile / total) if total > 0 else 0.0,
                    "competition":    item.get("compIdx", "중간"),
                    "ad_count":       _parse_count(item.get("plAvgDepth", 0)),
                }
            
            time.sleep(0.5)  # API 제한 대응
            
        except Exception as e:
            logger.warning(f"검색광고 API 호출 실패: {e}")
            continue
    
    if result:
        logger.info(f"검색광고 API 수집: {len(result)}개 키워드 지표")
    return result


def get_related_keywords_by_ad_api(seed: str, max_count: int = 20) -> List[str]:
    """
    검색광고 API의 연관 키워드 기능으로 시드 키워드 확장.
    시드 1개 → 연관 키워드 수십 개 반환.
    """
    if not all([NAVER_AD_API_KEY, NAVER_AD_SECRET_KEY, NAVER_CUSTOMER_ID]):
        return []
    
    uri = "/keywordstool"
    params = {
        "hintKeywords": seed.replace(" ", ""),
        "showDetail":   "1",
    }
    full_uri = uri + "?" + urllib.parse.urlencode(params)
    url = "https://api.searchad.naver.com" + full_uri
    
    try:
        headers = _ad_api_headers("GET", uri)
        resp = requests.get(url, headers=headers, timeout=15)
        
        if resp.status_code != 200:
            logger.warning(f"연관 키워드 API 오류: {resp.status_code}")
            return []
        
        data = resp.json()
        keywords = []
        for item in data.get("keywordList", []):
            kw = item.get("relKeyword", "").strip()
            if kw and len(kw) > 1:
                keywords.append(kw)
        
        logger.info(f"'{seed}' 연관 키워드 {len(keywords)}개 수집")
        return keywords[:max_count]
    except Exception as e:
        logger.warning(f"연관 키워드 조회 실패: {e}")
        return []


# ═══════════════════════════════════════════════════════
#  2. 네이버 개발자센터 API (검색 결과 수로 경쟁도 추정)
# ═══════════════════════════════════════════════════════

def get_blog_competition(keyword: str) -> int:
    """
    네이버 블로그 검색 결과 개수를 반환 (경쟁도 측정용).
    결과 많을수록 경쟁 심함.
    """
    if not NAVER_CLIENT_ID or not NAVER_CLIENT_SECRET:
        return -1
    
    url = "https://openapi.naver.com/v1/search/blog.json"
    headers = {
        "X-Naver-Client-Id":     NAVER_CLIENT_ID,
        "X-Naver-Client-Secret": NAVER_CLIENT_SECRET,
    }
    params = {"query": keyword, "display": 1}
    
    try:
        resp = requests.get(url, headers=headers, params=params, timeout=10)
        if resp.status_code == 200:
            return resp.json().get("total", 0)
    except Exception as e:
        logger.warning(f"블로그 검색 API 실패 ({keyword}): {e}")
    return -1


# ═══════════════════════════════════════════════════════
#  3. 자동완성 (롱테일 키워드 수집)
# ═══════════════════════════════════════════════════════

def get_naver_autocomplete(seed: str) -> List[str]:
    """네이버 자동완성 API로 롱테일 키워드 수집"""
    url = "https://ac.search.naver.com/nx/ac"
    params = {
        "q":       seed,
        "st":      "100",
        "r_format": "json",
        "r_enc":    "UTF-8",
        "r_unicode": "0",
        "t_koreng": "1",
        "q_enc":    "UTF-8",
    }
    
    try:
        resp = requests.get(url, params=params, timeout=8)
        if resp.status_code != 200:
            return []
        
        data = resp.json()
        items = data.get("items", [[]])
        if not items or not items[0]:
            return []
        
        keywords = []
        for item in items[0]:
            if isinstance(item, list) and len(item) > 0:
                kw = item[0].strip()
                if kw and kw != seed and len(kw) >= 2:
                    keywords.append(kw)
        return keywords[:15]
    except Exception as e:
        logger.debug(f"네이버 자동완성 실패 ({seed}): {e}")
        return []


def get_google_autocomplete(seed: str) -> List[str]:
    """구글 자동완성으로 롱테일 키워드 수집"""
    url = "http://suggestqueries.google.com/complete/search"
    params = {
        "client": "firefox",
        "q":      seed,
        "hl":     "ko",
    }
    
    try:
        resp = requests.get(url, params=params, timeout=8)
        if resp.status_code != 200:
            return []
        
        data = resp.json()
        if len(data) >= 2 and isinstance(data[1], list):
            return [k for k in data[1] if k != seed and len(k) >= 2][:10]
    except Exception as e:
        logger.debug(f"구글 자동완성 실패 ({seed}): {e}")
    return []


# ═══════════════════════════════════════════════════════
#  4. 네이버 데이터랩 (기존, 계절성/상승세 파악용)
# ═══════════════════════════════════════════════════════

def fetch_naver_datalab_trends(top_n: int = 20) -> List[str]:
    """네이버 데이터랩 검색어 트렌드로 인기 키워드 수집"""
    if not NAVER_CLIENT_ID or not NAVER_CLIENT_SECRET:
        logger.warning("데이터랩용 NAVER_CLIENT_ID/SECRET 없음 → 건너뜀")
        return []
    
    keyword_groups = [
        {"groupName": "부업",     "keywords": ["부업", "N잡", "재택부업", "온라인부업"]},
        {"groupName": "재테크",   "keywords": ["재테크", "주식투자", "ETF", "청약"]},
        {"groupName": "자기계발", "keywords": ["자기계발", "독서", "영어공부", "자격증"]},
        {"groupName": "블로그수익","keywords": ["블로그수익", "에드센스", "블로그운영"]},
        {"groupName": "직장생활", "keywords": ["이직", "연봉협상", "직장스트레스", "퇴사"]},
    ]
    
    url = "https://openapi.naver.com/v1/datalab/search"
    headers = {
        "X-Naver-Client-Id":     NAVER_CLIENT_ID,
        "X-Naver-Client-Secret": NAVER_CLIENT_SECRET,
        "Content-Type":          "application/json",
    }
    
    end_date   = datetime.now().strftime("%Y-%m-%d")
    start_date = (datetime.now() - timedelta(days=7)).strftime("%Y-%m-%d")
    
    body = {
        "startDate":     start_date,
        "endDate":       end_date,
        "timeUnit":      "date",
        "keywordGroups": keyword_groups,
    }
    
    try:
        resp = requests.post(url, headers=headers, json=body, timeout=10)
        if resp.status_code != 200:
            logger.warning(f"데이터랩 API 오류: {resp.status_code}")
            return []
        
        data = resp.json()
        results = data.get("results", [])
        
        scored = []
        for r in results:
            data_points = r.get("data", [])
            if data_points:
                latest_ratio = data_points[-1].get("ratio", 0)
                scored.append((latest_ratio, r.get("keywords", [])))
        
        scored.sort(key=lambda x: -x[0])
        
        keywords = []
        for _, kws in scored:
            keywords.extend(kws)
        
        logger.info(f"데이터랩 수집: {len(keywords)}개")
        return keywords[:top_n]
    except Exception as e:
        logger.warning(f"데이터랩 실패: {e}")
        return []


def fetch_category_trends(category: str, top_n: int = 8) -> List[str]:
    """
    특정 카테고리의 데이터랩 검색 트렌드 + 자동완성을 합쳐서
    '지금 뜨는' 키워드 top_n개를 반환.

    워크플로:
    1. CATEGORY_DATALAB_GROUPS에서 카테고리 그룹들 가져옴
    2. 네이버 데이터랩 호출 → 그룹별 검색 트렌드 비율 측정
    3. 비율 높은 그룹의 키워드를 시드로 자동완성 호출
    4. 합쳐서 top_n 반환
    """
    groups = CATEGORY_DATALAB_GROUPS.get(category)
    if not groups:
        return []

    trending_keywords = []

    # 1단계: 데이터랩으로 인기 그룹 식별
    if NAVER_CLIENT_ID and NAVER_CLIENT_SECRET:
        url = "https://openapi.naver.com/v1/datalab/search"
        headers = {
            "X-Naver-Client-Id":     NAVER_CLIENT_ID,
            "X-Naver-Client-Secret": NAVER_CLIENT_SECRET,
            "Content-Type":          "application/json",
        }
        end_date   = datetime.now().strftime("%Y-%m-%d")
        start_date = (datetime.now() - timedelta(days=7)).strftime("%Y-%m-%d")
        # 데이터랩은 한 요청에 그룹 5개까지만 지원
        body = {
            "startDate":     start_date,
            "endDate":       end_date,
            "timeUnit":      "date",
            "keywordGroups": groups[:5],
        }
        try:
            resp = requests.post(url, headers=headers, json=body, timeout=10)
            if resp.status_code == 200:
                data = resp.json()
                results = data.get("results", [])
                # 각 그룹의 최근 평균 비율로 정렬
                ranked = []
                for r in results:
                    data_points = r.get("data", [])
                    if data_points:
                        recent = data_points[-3:]  # 최근 3일
                        avg_ratio = sum(d.get("ratio", 0) for d in recent) / len(recent)
                        ranked.append((avg_ratio, r.get("keywords", []), r.get("title", "")))
                ranked.sort(key=lambda x: -x[0])

                logger.info(f"[트렌드 {category}] 데이터랩 그룹 순위:")
                for ratio, kws, gname in ranked:
                    logger.info(f"  {gname}: 비율 {ratio:.1f} | {kws}")

                # 상위 그룹의 키워드를 트렌드 시드로 채택
                for _, kws, _ in ranked[:3]:  # 상위 3그룹
                    trending_keywords.extend(kws)
            else:
                logger.warning(f"[트렌드 {category}] 데이터랩 응답 {resp.status_code}")
        except Exception as e:
            logger.warning(f"[트렌드 {category}] 데이터랩 실패: {e}")
    else:
        logger.warning(f"[트렌드 {category}] NAVER_CLIENT_ID/SECRET 없음 → 데이터랩 건너뜀")

    # 2단계: 자동완성으로 신선한 롱테일 키워드 발굴
    auto_keywords = []
    seed_for_auto = trending_keywords[:3] if trending_keywords else [g["keywords"][0] for g in groups[:3]]

    for seed in seed_for_auto:
        try:
            auto = get_naver_autocomplete(seed)
            # 시드 그대로는 제외, 길이 6자 이상만 (롱테일)
            for kw in auto:
                if kw != seed and len(kw) >= 6 and kw not in auto_keywords:
                    auto_keywords.append(kw)
            time.sleep(0.3)
        except Exception:
            continue

    # 최종: 데이터랩 시드 키워드 + 자동완성 롱테일 합침
    combined = []
    seen = set()
    for kw in trending_keywords + auto_keywords:
        if kw not in seen:
            seen.add(kw)
            combined.append(kw)

    logger.info(f"[트렌드 {category}] 최종 {len(combined[:top_n])}개: {combined[:top_n]}")
    return combined[:top_n]


def get_seo_scored_keywords_with_trends(seed_keywords: List[str],
                                         category: str,
                                         top_n: int = 10,
                                         trend_weight: float = 1.3) -> List[dict]:
    """
    기존 get_seo_scored_keywords + 카테고리 트렌드 키워드 동적 주입.

    - 시드 풀에 트렌드 키워드 5~8개 추가하여 확장 → 점수화
    - 트렌드 출신 키워드는 점수 × trend_weight 가중치 적용
    """
    # 트렌드 키워드 가져오기
    trend_kws = fetch_category_trends(category, top_n=8)
    trend_set = set(trend_kws)

    if trend_kws:
        logger.info(f"[SEO+트렌드 {category}] 시드 {len(seed_keywords)}개 + 트렌드 {len(trend_kws)}개 결합")
    else:
        logger.info(f"[SEO+트렌드 {category}] 트렌드 추적 결과 없음 → 시드만 사용")

    # 시드 + 트렌드를 합쳐서 일반 SEO 함수 호출
    merged_seeds = list(set(seed_keywords) | trend_set)
    scored = get_seo_scored_keywords(
        seed_keywords=merged_seeds,
        category_hint=category,
        top_n=top_n * 3,  # 가중치 적용 후 다시 정렬해야 하니까 넉넉히 받음
        check_competition=False,
    )

    # 트렌드 출신 키워드에 가중치 적용
    boosted = []
    for entry in scored:
        kw = entry["keyword"]
        is_trend = any(t in kw or kw in t for t in trend_set)
        if is_trend:
            entry["original_score"] = entry["score"]
            entry["score"] = round(entry["score"] * trend_weight, 1)
            entry["trend_boost"] = True
            entry["detail"]["reasons"].append(f"트렌드 가중치 ×{trend_weight}")
        else:
            entry["trend_boost"] = False
        boosted.append(entry)

    # 가중치 적용 후 재정렬
    boosted.sort(key=lambda x: -x["score"])

    # 로그: top 5
    for i, item in enumerate(boosted[:5], 1):
        trend_mark = "🔥" if item.get("trend_boost") else "  "
        logger.info(f"  #{i} {trend_mark} [{item['score']}점] {item['keyword']}")

    return boosted[:top_n]


# ═══════════════════════════════════════════════════════
#  5. Google Trends RSS
# ═══════════════════════════════════════════════════════

def fetch_google_trends_rss(top_n: int = 20) -> List[str]:
    """구글 트렌드 공식 RSS 피드"""
    url = "https://trends.google.com/trending/rss?geo=KR"
    headers = {
        "User-Agent": "Mozilla/5.0 (compatible; RSS Reader)",
        "Accept":     "application/rss+xml, application/xml",
    }
    
    try:
        resp = requests.get(url, headers=headers, timeout=10)
        if resp.status_code != 200:
            return []
        
        root = ET.fromstring(resp.content)
        keywords = []
        for item in root.findall(".//item"):
            title = item.find("title")
            if title is not None and title.text:
                kw = title.text.strip()
                if kw and 1 < len(kw) <= 30:
                    keywords.append(kw)
        
        logger.info(f"Google Trends RSS 수집: {len(keywords)}개")
        return keywords[:top_n]
    except Exception as e:
        logger.warning(f"Google Trends RSS 실패: {e}")
        return []


# ═══════════════════════════════════════════════════════
#  6. SEO 점수 계산 (핵심 알고리즘)
# ═══════════════════════════════════════════════════════

def calculate_seo_score(keyword: str, metrics: Optional[dict] = None,
                         blog_count: int = -1) -> Tuple[float, dict]:
    """
    키워드의 SEO 노출 유리도를 0~150점으로 평가.
    
    평가 기준:
    - 월 검색량 (있어야 의미 있음, 너무 많으면 경쟁 심함)
    - 경쟁 강도 (낮을수록 좋음)
    - 키워드 길이 (롱테일일수록 상위노출 쉬움)
    - 블로그 관련성 (직장인/부업/재테크 매칭)
    - 블로그 검색 결과 수 (적을수록 경쟁 적음)
    - 차단 키워드 (즉시 0점)
    
    반환: (점수, 세부 지표 dict)
    """
    score  = 30.0  # 기본점 (낮게 시작해서 가산점 위주)
    detail = {"reasons": []}
    
    # ── 0. 차단 키워드 즉시 0점 ─────
    for blocked in _BLOCKED_HINT:
        if blocked in keyword:
            return 0.0, {"blocked": blocked, "reasons": [f"차단어 포함: {blocked}"]}
    
    # ── 1. 길이 점수 (롱테일 보너스 강화) ─
    length = len(keyword)
    if length < 3:
        score -= 20
        detail["reasons"].append(f"너무 짧음 ({length}자) -20")
    elif 3 <= length <= 6:
        score += 3
        detail["reasons"].append(f"짧은 키워드 ({length}자) +3")
    elif 7 <= length <= 10:
        score += 10
        detail["reasons"].append(f"적당한 길이 ({length}자) +10")
    elif 11 <= length <= 15:
        score += 18  # 롱테일 핵심 구간
        detail["reasons"].append(f"롱테일 최적 ({length}자) +18")
    elif 16 <= length <= 20:
        score += 12
        detail["reasons"].append(f"긴 롱테일 ({length}자) +12")
    else:
        score += 5
        detail["reasons"].append(f"매우 긴 키워드 ({length}자) +5")
    
    # ── 2. 카테고리 매칭 (강화) ────────
    match_count = sum(1 for hint in _OFFICE_WORKER_HINT if hint in keyword)
    if match_count >= 3:
        score += 30
        detail["reasons"].append(f"매우 강한 관련성 +30 ({match_count}개 매칭)")
    elif match_count == 2:
        score += 22
        detail["reasons"].append(f"강한 관련성 +22 (2개 매칭)")
    elif match_count == 1:
        score += 12
        detail["reasons"].append("카테고리 매칭 +12")
    else:
        score -= 10
        detail["reasons"].append("카테고리 매칭 없음 -10")
    
    # ── 3. 월 검색량 점수 (블로그 최적 구간 강화) ─
    if metrics and metrics.get("monthly_total") is not None:
        total = metrics["monthly_total"]
        detail["monthly_total"] = total
        if total == 0:
            score -= 25
            detail["reasons"].append("검색량 0 -25")
        elif 1 <= total < 100:
            score -= 5
            detail["reasons"].append(f"검색량 {total} (매우 적음) -5")
        elif 100 <= total < 500:
            score += 10
            detail["reasons"].append(f"검색량 {total} (적정 소규모) +10")
        elif 500 <= total < 3000:
            score += 30  # 블로그에 가장 좋은 구간 — 상한 올림
            detail["reasons"].append(f"검색량 {total} (블로그 골드존) +30")
        elif 3000 <= total < 10000:
            score += 20
            detail["reasons"].append(f"검색량 {total} (좋음) +20")
        elif 10000 <= total < 50000:
            score += 5
            detail["reasons"].append(f"검색량 {total} (경쟁 있음) +5")
        else:
            score -= 15  # 너무 많으면 레드오션
            detail["reasons"].append(f"검색량 {total} (레드오션) -15")
    
    # ── 4. 경쟁 강도 (차별 확대) ────────
    if metrics:
        comp = metrics.get("competition", "")
        detail["competition"] = comp
        if comp == "낮음":
            score += 25  # 블로그 SEO에 가장 중요한 지표
            detail["reasons"].append("경쟁도 낮음 +25")
        elif comp == "중간":
            score += 8
            detail["reasons"].append("경쟁도 중간 +8")
        elif comp == "높음":
            score -= 15
            detail["reasons"].append("경쟁도 높음 -15")
    
    # ── 5. 모바일 비율 (모바일 유저가 블로그 주독자) ─
    if metrics and metrics.get("mobile_ratio", 0) > 0.8:
        score += 8
        detail["reasons"].append("모바일 압도적 +8")
    elif metrics and metrics.get("mobile_ratio", 0) > 0.7:
        score += 5
        detail["reasons"].append("모바일 높음 +5")
    
    # ── 6. 블로그 검색 결과 수 ─────
    if blog_count > 0:
        detail["blog_count"] = blog_count
        if blog_count < 5000:
            score += 18
            detail["reasons"].append("블로그글 매우 적음 +18")
        elif blog_count < 10000:
            score += 12
            detail["reasons"].append("블로그글 적음 +12")
        elif blog_count < 100000:
            score += 5
            detail["reasons"].append("블로그글 적정 +5")
        elif blog_count > 1000000:
            score -= 8
            detail["reasons"].append("블로그글 과다 -8")
    
    # ── 7. 특수 패턴 보너스 ─────────
    # 숫자 포함 (구체적)
    if re.search(r'\d', keyword):
        score += 5
        detail["reasons"].append("숫자 포함 +5")
    # '방법/하는법/추천/후기' (검색 의도 명확)
    intent_words = ["방법", "하는법", "추천", "후기", "비교", "순위", "이유", "현실", "실전"]
    matched_intents = [w for w in intent_words if w in keyword]
    if len(matched_intents) >= 2:
        score += 10
        detail["reasons"].append(f"검색의도 매우 명확 +10 ({matched_intents})")
    elif len(matched_intents) == 1:
        score += 7
        detail["reasons"].append(f"검색의도 명확 +7 ({matched_intents[0]})")
    
    # 점수 범위 제한 (0~150으로 확장)
    score = max(0.0, min(150.0, score))
    detail["final_score"] = round(score, 1)
    
    return score, detail


# ═══════════════════════════════════════════════════════
#  7. 통합: 카테고리별 SEO 최적 키워드 선택
# ═══════════════════════════════════════════════════════

def expand_keywords_by_seeds(seed_keywords: List[str],
                               max_per_seed: int = 10) -> List[str]:
    """
    시드 키워드 리스트 → 자동완성/연관 키워드로 확장
    """
    expanded = set(seed_keywords)
    
    for seed in seed_keywords[:8]:  # 시드 너무 많이 확장하면 시간 초과
        # 자동완성 (네이버)
        try:
            auto = get_naver_autocomplete(seed)
            expanded.update(auto[:max_per_seed])
        except Exception:
            pass
        
        time.sleep(0.3)
        
        # 연관 키워드 (검색광고 API)
        if NAVER_AD_API_KEY:
            try:
                related = get_related_keywords_by_ad_api(seed, max_count=max_per_seed)
                expanded.update(related)
            except Exception:
                pass
        
        time.sleep(0.3)
    
    return list(expanded)


def get_seo_scored_keywords(seed_keywords: List[str],
                             category_hint: str = "",
                             top_n: int = 10,
                             check_competition: bool = False) -> List[dict]:
    """
    시드 키워드로부터 확장 → 점수 계산 → 정렬 → Top N 반환
    
    반환: [
      {
        "keyword":        "퇴근 후 부업 추천",
        "score":          82.5,
        "monthly_total":  1200,
        "competition":    "낮음",
        "detail":         { ... },
      },
      ...
    ]
    """
    logger.info(f"키워드 확장 시작: 시드 {len(seed_keywords)}개")
    
    # 1. 확장
    expanded = expand_keywords_by_seeds(seed_keywords)
    logger.info(f"확장 완료: {len(expanded)}개")
    
    # 2. 사전 필터링 (차단어 제거, 너무 긴/짧은 것 제거)
    filtered = []
    for kw in expanded:
        if len(kw) < 2 or len(kw) > 30:
            continue
        if any(b in kw for b in _BLOCKED_HINT):
            continue
        filtered.append(kw)
    
    logger.info(f"필터 후: {len(filtered)}개")
    
    # 3. 검색광고 API로 지표 수집 (배치 처리)
    metrics_map = {}
    if NAVER_AD_API_KEY and filtered:
        # 너무 많으면 API 호출 과다 → 최대 50개까지만
        batch = filtered[:50]
        metrics_map = get_keyword_metrics(batch)
    
    # 4. (선택) 블로그 경쟁도 조회 (API 호출 많음 — 기본 꺼둠)
    blog_counts = {}
    if check_competition and NAVER_CLIENT_ID and filtered:
        for kw in filtered[:20]:  # 블로그 경쟁도는 상위 20개만
            blog_counts[kw] = get_blog_competition(kw)
            time.sleep(0.1)
    
    # 5. 점수 계산
    scored = []
    for kw in filtered:
        metrics = metrics_map.get(kw) or metrics_map.get(kw.replace(" ", ""))
        blog_count = blog_counts.get(kw, -1)
        score, detail = calculate_seo_score(kw, metrics, blog_count)
        
        if score <= 0:
            continue  # 0점(차단)은 제외
        
        entry = {
            "keyword":       kw,
            "score":         round(score, 1),
            "monthly_total": (metrics or {}).get("monthly_total"),
            "competition":   (metrics or {}).get("competition"),
            "blog_count":    blog_count if blog_count > 0 else None,
            "detail":        detail,
        }
        scored.append(entry)
    
    # 6. 점수 순 정렬
    scored.sort(key=lambda x: -x["score"])
    
    logger.info(f"SEO 점수 계산 완료: {len(scored)}개 / Top {top_n} 반환")
    
    # Top N 로그 출력
    for i, item in enumerate(scored[:min(top_n, 5)], 1):
        total = item.get("monthly_total") or "?"
        comp  = item.get("competition") or "?"
        logger.info(f"  #{i} [{item['score']}점] {item['keyword']} (검색량:{total}, 경쟁:{comp})")
    
    return scored[:top_n]


# ═══════════════════════════════════════════════════════
#  8. 레거시 호환 함수 (automation.py에서 호출)
# ═══════════════════════════════════════════════════════

def fetch_trending_keywords(top_n: int = 30) -> List[str]:
    """네이버 + 구글 트렌드 통합 수집 (레거시 호환)"""
    merged = []
    
    try:
        merged.extend(fetch_google_trends_rss(top_n=top_n))
    except Exception:
        pass
    
    try:
        merged.extend(fetch_naver_datalab_trends(top_n=top_n))
    except Exception:
        pass
    
    # 중복 제거 & 관련도 정렬
    seen = set()
    unique = []
    for kw in merged:
        k = kw.strip()
        if k and k not in seen:
            seen.add(k)
            unique.append(k)
    
    indexed = list(enumerate(unique))
    
    def _legacy_score(kw: str) -> int:
        s = 0
        for hint in _OFFICE_WORKER_HINT:
            if hint in kw:
                s += 2
        if len(kw) <= 1:
            s -= 5
        return s
    
    indexed.sort(key=lambda x: (-_legacy_score(x[1]), x[0]))
    return [kw for _, kw in indexed][:top_n]


def get_keywords_with_trends(
    base_pool: List[str],
    top_n_trend: int = 30,
    max_total: int = 50,
    trending_ratio: float = 0.5,
) -> List[str]:
    """
    레거시: automation.py의 구버전에서 호출
    """
    try:
        trending = fetch_trending_keywords(top_n=top_n_trend)
    except Exception:
        trending = []
    
    if not trending:
        return base_pool
    
    n_trend = max(1, int(max_total * trending_ratio))
    n_base  = max_total - n_trend
    
    picked_trend = trending[:n_trend]
    picked_base  = base_pool[:n_base] if base_pool else []
    
    seen = set()
    result = []
    for kw in picked_trend + picked_base:
        if kw not in seen:
            seen.add(kw)
            result.append(kw)
    
    logger.info(
        "[%s] 최종 키워드 %d개 (트렌드 포함)",
        datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        len(result),
    )
    return result[:max_total] if result else base_pool


# ═══════════════════════════════════════════════════════
#  9. 정부 정책 카테고리 전용 (policy_crawler 연동)
# ═══════════════════════════════════════════════════════

def get_policy_seo_keywords(base_seeds: List[str],
                              top_n: int = 10,
                              max_seeds: int = 25) -> List[dict]:
    """
    정부지원금 카테고리 전용 SEO 키워드 선별.

    1. policy_crawler로 실시간 정책 키워드 보강
    2. 보강된 시드 → 검색광고 API로 지표 조회
    3. SEO 점수 정렬 → Top N 반환

    실패 시(policy_crawler 모듈 없음) 일반 get_seo_scored_keywords로 폴백.
    """
    try:
        from policy_crawler import get_policy_seed_keywords
    except ImportError:
        logger.warning("policy_crawler 모듈 없음 → 기본 시드만 사용")
        return get_seo_scored_keywords(
            seed_keywords=base_seeds,
            category_hint="정부지원금",
            top_n=top_n,
        )

    # 1. 실시간 정책 키워드 보강
    enriched = get_policy_seed_keywords(base_seeds=base_seeds, max_total=max_seeds)
    logger.info(f"정책 시드 보강: 기본 {len(base_seeds)}개 → 통합 {len(enriched)}개")

    # 2. SEO 점수 시스템에 전달
    return get_seo_scored_keywords(
        seed_keywords=enriched,
        category_hint="정부지원금",
        top_n=top_n,
    )


# ═══════════════════════════════════════════════════════
#  단독 테스트
# ═══════════════════════════════════════════════════════

if __name__ == "__main__":
    print("=" * 60)
    print("  트렌드 크롤러 v2.0 단독 테스트")
    print("=" * 60)
    
    print("\n[1] API 키 상태")
    print(f"  개발자센터:   {'✓' if NAVER_CLIENT_ID else '✗'}")
    print(f"  검색광고:    {'✓' if NAVER_AD_API_KEY else '✗'}")
    print(f"  Customer ID: {NAVER_CUSTOMER_ID or '없음'}")
    
    print("\n[2] 네이버 자동완성 테스트: '직장인 부업'")
    auto = get_naver_autocomplete("직장인 부업")
    for kw in auto[:5]:
        print(f"  - {kw}")
    
    if NAVER_AD_API_KEY:
        print("\n[3] 검색광고 API 테스트: '직장인 부업' 지표")
        metrics = get_keyword_metrics(["직장인 부업", "퇴근후 부업"])
        for kw, m in metrics.items():
            print(f"  {kw}: 월{m['monthly_total']:,}회 / 경쟁 {m['competition']}")
    
    print("\n[4] SEO 점수 통합 테스트")
    scored = get_seo_scored_keywords(
        seed_keywords=["직장인 부업", "ETF 투자"],
        top_n=10,
    )
    for item in scored:
        print(f"  [{item['score']:5.1f}점] {item['keyword']}")
