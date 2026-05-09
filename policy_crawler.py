# -*- coding: utf-8 -*-
"""
policy_crawler.py
────────────────────────────────────────────────────────────
정부 정책/지원금 키워드 실시간 수집 모듈.

[데이터 소스 -인증키 없이 동작]
1. 네이버 뉴스 API     -이미 보유한 NAVER_CLIENT_ID/SECRET 활용
2. 정부24 보도자료     -HTML 스크래핑 (백업)
3. 기업마당 (bizinfo)  -공지사항 페이지 스크래핑
4. 한국경제 정책 RSS   -정책 섹션 RSS

[향후 확장]
- 공공데이터포털(data.go.kr) 인증키 발급 시 정식 API로 교체
  (youthcenter.go.kr, bokjiro.go.kr 정책 데이터 정식 API)
────────────────────────────────────────────────────────────
"""

from __future__ import annotations

import logging
import os
import re
import time
import xml.etree.ElementTree as ET
from typing import List, Set
from datetime import datetime

import requests

# ── 로깅 ──────────────────────────────────────────────────
logger = logging.getLogger("policy_crawler")
if not logger.handlers:
    _h = logging.StreamHandler()
    _h.setFormatter(logging.Formatter(
        "[%(asctime)s] %(levelname)s policy_crawler: %(message)s",
        "%Y-%m-%d %H:%M:%S"
    ))
    logger.addHandler(_h)
    logger.setLevel(logging.INFO)

# ── 환경 변수 ─────────────────────────────────────────────
NAVER_CLIENT_ID     = os.environ.get("NAVER_CLIENT_ID", "")
NAVER_CLIENT_SECRET = os.environ.get("NAVER_CLIENT_SECRET", "")

# 사용자 에이전트 (스크래핑 시 차단 회피)
_DEFAULT_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/124.0.0.0 Safari/537.36"
    ),
    "Accept-Language": "ko-KR,ko;q=0.9,en;q=0.5",
}


# ═══════════════════════════════════════════════════════
#  1. 네이버 뉴스 API (가장 안정적)
# ═══════════════════════════════════════════════════════

# 정책 카테고리별 검색 쿼리 (다양화로 커버리지 확대)
_POLICY_NEWS_QUERIES = [
    "청년 정책 지원금",
    "청년도약계좌",
    "소상공인 지원",
    "근로장려금",
    "주거 지원 청년",
    "정부지원금 신청",
    "복지 신규 정책",
    "전세대출 청년",
]


def fetch_naver_policy_news(query: str, count: int = 20) -> List[dict]:
    """
    네이버 뉴스 검색 API로 최근 정책 뉴스 가져오기.
    반환: [{title, description, link, pubDate}, ...]
    """
    if not NAVER_CLIENT_ID or not NAVER_CLIENT_SECRET:
        logger.warning("NAVER_CLIENT_ID/SECRET 없음 → 뉴스 API 건너뜀")
        return []

    url = "https://openapi.naver.com/v1/search/news.json"
    headers = {
        "X-Naver-Client-Id":     NAVER_CLIENT_ID,
        "X-Naver-Client-Secret": NAVER_CLIENT_SECRET,
    }
    params = {
        "query":   query,
        "display": min(count, 100),
        "sort":    "date",
    }

    try:
        resp = requests.get(url, headers=headers, params=params, timeout=10)
        if resp.status_code != 200:
            logger.warning(f"뉴스 API 오류 ({resp.status_code}): {query}")
            return []

        items = resp.json().get("items", [])
        # HTML 태그 제거
        clean = []
        for it in items:
            title = re.sub(r"<[^>]+>", "", it.get("title", ""))
            title = title.replace("&quot;", '"').replace("&amp;", "&").replace("&lt;", "<").replace("&gt;", ">")
            clean.append({
                "title":       title.strip(),
                "description": re.sub(r"<[^>]+>", "", it.get("description", ""))[:200],
                "link":        it.get("link", ""),
                "pubDate":     it.get("pubDate", ""),
            })
        return clean
    except Exception as e:
        logger.warning(f"뉴스 API 호출 실패 ({query}): {e}")
        return []


# ═══════════════════════════════════════════════════════
#  2. 기업마당 (bizinfo.go.kr) 공지사항
# ═══════════════════════════════════════════════════════

def fetch_bizinfo_notices(top_n: int = 20) -> List[str]:
    """
    기업마당 메인 페이지에서 신규 정책/공지 제목 스크래핑.
    인증키 없이 가능한 안전한 백업 소스.
    """
    url = "https://www.bizinfo.go.kr/web/lay1/bbs/S1T122C128/AS/74/list.do"
    try:
        resp = requests.get(url, headers=_DEFAULT_HEADERS, timeout=10)
        if resp.status_code != 200:
            return []

        # 게시판 제목 패턴 추출 (HTML 구조 변경 시 빈 결과 → 폴백)
        # <a ... class="title">제목</a> 또는 <td class="title"><a>제목</a></td>
        titles = re.findall(
            r'class=["\'](?:title|tit)["\'][^>]*>\s*(?:<a[^>]*>)?\s*([^<\n]{4,80})',
            resp.text,
        )
        # 중복 제거 & 정리
        seen, result = set(), []
        for t in titles:
            t = t.strip()
            if t and t not in seen and len(t) >= 5:
                seen.add(t)
                result.append(t)
        logger.info(f"기업마당 공지: {len(result)}개")
        return result[:top_n]
    except Exception as e:
        logger.debug(f"기업마당 스크래핑 실패: {e}")
        return []


# ═══════════════════════════════════════════════════════
#  3. 한국경제 정책 RSS
# ═══════════════════════════════════════════════════════

_KOREAN_FINANCE_RSS = [
    # (이름, URL) - 정책 비중 높은 소스 우선
    ("한경 경제정책",   "https://www.hankyung.com/feed/economy"),
    ("한경 부동산",     "https://www.hankyung.com/feed/realestate"),
    ("머니투데이 정책", "https://rss.mt.co.kr/news/mtv_policy.xml"),
    ("연합뉴스 경제",   "https://www.yonhapnewstv.co.kr/category/news/economy/feed/"),
    # 정부 부처 보도자료 RSS
    ("기획재정부",     "https://www.moef.go.kr/rss/news.do?rssCd=newsBriefing"),
    ("고용노동부",     "https://www.moel.go.kr/rss/n_pressbriefing.xml"),
    ("국토교통부",     "http://www.molit.go.kr/USR/NEWS/m_71/rss.do?p_section=N1010"),
]


def fetch_finance_rss(top_n: int = 20) -> List[str]:
    """
    한국 경제지 RSS에서 정책/경제 관련 헤드라인 수집.
    """
    titles: List[str] = []
    for name, url in _KOREAN_FINANCE_RSS:
        try:
            resp = requests.get(url, headers=_DEFAULT_HEADERS, timeout=8)
            if resp.status_code != 200:
                continue

            try:
                root = ET.fromstring(resp.content)
            except ET.ParseError:
                continue

            for item in root.findall(".//item"):
                title_elem = item.find("title")
                if title_elem is not None and title_elem.text:
                    t = title_elem.text.strip()
                    if 5 <= len(t) <= 100:
                        titles.append(t)
        except Exception as e:
            logger.debug(f"RSS 실패 ({name}): {e}")
            continue

    logger.info(f"경제 RSS 수집: {len(titles)}개")
    return titles[:top_n]


# ═══════════════════════════════════════════════════════
#  4. 정책 키워드 추출 (제목 → 검색 키워드)
# ═══════════════════════════════════════════════════════

# 정책 제목에서 자주 등장하는 패턴 (이걸 시드로 키워드 생성)
_POLICY_HINT = [
    "청년", "신혼", "소상공인", "중소기업", "근로", "장려금", "지원금",
    "특별지원", "정책자금", "보조금", "바우처", "장학금", "전세", "월세",
    "임차", "임대", "주택", "분양", "청약", "복지", "수당", "급여",
    "감면", "공제", "환급", "세제", "혜택", "지원", "신청", "도약",
    "내일채움", "두루누리", "디딤돌", "버팀목", "행복주택",
]

# 제거할 일반어 (의미 없는 것들)
_STOP_WORDS = {
    "기자", "단독", "속보", "사진", "영상", "포토", "인터뷰", "오피니언",
    "사설", "칼럼", "더팩트", "헤럴드", "한경", "머투", "매경",
}


def extract_policy_keywords(titles: List[str], max_count: int = 30) -> List[str]:
    """
    뉴스/공지 제목 리스트에서 정책 검색 키워드 추출.

    전략:
    1. 정책 힌트 단어가 포함된 제목만 필터
    2. 제목을 의미 단위로 자르기 (괄호/특수문자 제거 후 어절 단위)
    3. 정책 힌트 단어 + 인접 1~2어절을 묶어 검색 키워드로
    """
    keywords: Set[str] = set()

    for title in titles:
        # 전처리
        clean = re.sub(r"\[[^\]]+\]", "", title)        # [속보] [단독] 제거
        clean = re.sub(r"\([^)]+\)", "", clean)          # (사진) 제거
        clean = re.sub(r"['\"·…]", " ", clean)
        clean = re.sub(r"\s+", " ", clean).strip()

        # 정책 힌트 단어 포함 여부
        if not any(h in clean for h in _POLICY_HINT):
            continue

        # 어절 분리 → 정책 힌트 + 주변 단어로 2~4어절 조합
        words = clean.split()
        for i, w in enumerate(words):
            if w in _STOP_WORDS:
                continue
            for hint in _POLICY_HINT:
                if hint in w:
                    # 힌트 단어 중심으로 좌1~우2 범위에서 키워드 추출
                    start = max(0, i - 1)
                    end = min(len(words), i + 3)
                    chunk = words[start:end]
                    # 너무 짧거나 중지어로 시작/끝나면 스킵
                    chunk = [c for c in chunk if c not in _STOP_WORDS and len(c) >= 2]
                    if 2 <= len(chunk) <= 4:
                        kw = " ".join(chunk)
                        # 한글 비율 검증 (영문/숫자만 있으면 제외)
                        if len(re.findall(r"[가-힣]", kw)) >= 4:
                            keywords.add(kw[:30])
                    break

    result = list(keywords)[:max_count]
    logger.info(f"정책 키워드 추출: {len(result)}개")
    return result


# ═══════════════════════════════════════════════════════
#  5. 통합 함수 - 정부지원금 시드 키워드 보강
# ═══════════════════════════════════════════════════════

def get_policy_seed_keywords(base_seeds: List[str] = None,
                              max_total: int = 40) -> List[str]:
    """
    KEYWORD_POOL_V2['정부지원금']에 실시간 정책 키워드를 추가 공급.

    동작:
    1. 네이버 뉴스 API로 최근 정책 뉴스 헤드라인 수집
    2. 기업마당 공지 백업 수집
    3. 경제지 RSS 백업 수집
    4. 헤드라인 → 검색 키워드 추출
    5. 기본 시드와 병합 → 중복 제거 → 반환
    """
    if base_seeds is None:
        base_seeds = []

    all_titles: List[str] = []

    # 1. 네이버 뉴스 (메인 소스)
    if NAVER_CLIENT_ID:
        for q in _POLICY_NEWS_QUERIES[:6]:  # 6개 쿼리 (API 호출 6회)
            news = fetch_naver_policy_news(q, count=10)
            all_titles.extend([n["title"] for n in news])
            time.sleep(0.3)
    else:
        logger.warning("네이버 API 키 없음 → 백업 소스만 사용")

    # 2. 기업마당 백업
    try:
        all_titles.extend(fetch_bizinfo_notices(top_n=20))
    except Exception:
        pass

    # 3. 경제지/정부부처 RSS 백업 (네이버 뉴스 권한 없을 때 메인 소스가 됨)
    try:
        all_titles.extend(fetch_finance_rss(top_n=120))
    except Exception:
        pass

    logger.info(f"전체 헤드라인 수집: {len(all_titles)}개")

    # 4. 키워드 추출
    extracted = extract_policy_keywords(all_titles, max_count=max_total)

    # 5. 기본 시드와 병합 (중복 제거)
    seen = set()
    merged: List[str] = []
    for kw in list(base_seeds) + extracted:
        if kw and kw not in seen:
            seen.add(kw)
            merged.append(kw)

    return merged[:max_total]


# ═══════════════════════════════════════════════════════
#  단독 테스트
# ═══════════════════════════════════════════════════════

if __name__ == "__main__":
    from dotenv import load_dotenv
    load_dotenv()
    NAVER_CLIENT_ID     = os.environ.get("NAVER_CLIENT_ID", "")
    NAVER_CLIENT_SECRET = os.environ.get("NAVER_CLIENT_SECRET", "")

    print("=" * 60)
    print("  policy_crawler 단독 테스트")
    print("=" * 60)

    print(f"\n[키 상태] NAVER_CLIENT_ID: {'OK' if NAVER_CLIENT_ID else 'MISSING'}")

    print("\n[1] 네이버 뉴스 -'청년 정책 지원금'")
    news = fetch_naver_policy_news("청년 정책 지원금", count=5)
    for n in news[:5]:
        print(f"  - {n['title'][:60]}")

    print("\n[2] 기업마당 공지")
    biz = fetch_bizinfo_notices(top_n=5)
    for t in biz:
        print(f"  - {t[:60]}")

    print("\n[3] 경제지 RSS")
    rss = fetch_finance_rss(top_n=5)
    for t in rss:
        print(f"  - {t[:60]}")

    print("\n[4] 통합 정책 키워드 추출")
    seeds = get_policy_seed_keywords(
        base_seeds=["2026 청년정책 신청", "청년도약계좌 가입조건"],
        max_total=20,
    )
    for i, kw in enumerate(seeds, 1):
        print(f"  {i:2d}. {kw}")
