# -*- coding: utf-8 -*-
"""
trend_pipeline.py
─────────────────
실시간 트렌드/뉴스 수집 (1단계: 수집 + 안전필터까지).
- 구글 트렌드 RSS (실시간 급상승 검색어)
- 구글 뉴스 RSS (경제/기술/부동산 카테고리)
- 연합뉴스/전자신문 RSS (경제 헤드라인)
2단계에서 Gemini 변환 + automation 통합 예정.
"""
import xml.etree.ElementTree as ET
import requests
import re
from datetime import datetime

try:
    from dotenv import load_dotenv
    load_dotenv()
except ImportError:
    pass  # GitHub Actions에서는 env 직접 주입

UA = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0 Safari/537.36"}

# ── 안전 필터: 제외할 주제 (정치/연예/자극/사건사고) ──
BLOCK_KEYWORDS = [
    # 정치
    "대통령", "총리", "장관", "국회", "여당", "야당", "정당", "선거", "탄핵", "특검", "검찰", "구속", "내란",
    # 국제분쟁
    "전쟁", "이스라엘", "우크라이나", "하마스", "북한", "미사일", "테러",
    # 연예/자극
    "연예", "아이돌", "배우", "가수", "열애", "결별", "이혼", "사망", "음주운전", "마약", "성범죄", "논란", "폭행",
    # 사건사고
    "사고", "화재", "참사", "살인", "범죄", "재판", "판결",
]

# ── 카테고리별 구글 뉴스 RSS 토픽 ──
GOOGLE_NEWS_FEEDS = {
    "finance":    "https://news.google.com/rss/headlines/section/topic/BUSINESS?hl=ko&gl=KR&ceid=KR:ko",
    "ai":         "https://news.google.com/rss/headlines/section/topic/TECHNOLOGY?hl=ko&gl=KR&ceid=KR:ko",
    "trending":   "https://news.google.com/rss/headlines/section/topic/HEALTH?hl=ko&gl=KR&ceid=KR:ko",
}

# ── 카테고리별 구글 뉴스 '검색' RSS (토픽보다 카테고리 적중률 높음) ──
# TECHNOLOGY 토픽은 일반 IT 뉴스라 AI 비중이 낮아 → AI 전용 검색 RSS 추가 (박대홍 지시)
SEARCH_FEEDS = {
    "ai": [
        "https://news.google.com/rss/search?q=AI%20인공지능%20when:7d&hl=ko&gl=KR&ceid=KR:ko",
        "https://news.google.com/rss/search?q=ChatGPT%20OR%20Gemini%20OR%20Claude%20when:7d&hl=ko&gl=KR&ceid=KR:ko",
    ],
}

# ── 언론사 경제 RSS ──
PRESS_FEEDS = {
    "연합경제":   "https://www.yna.co.kr/rss/economy.xml",
    "전자신문":   "https://rss.etnews.com/Section901.xml",
}

# 정책/부동산 소스 (money, realestate용 — 카테고리별 분리)
# ※ 연합부동산 RSS는 404 (폐지) → 구글뉴스 검색 RSS로 대체
POLICY_FEEDS = {
    "money": {
        "정책브리핑":   "https://www.korea.kr/rss/policy.xml",
        "지원금뉴스":   "https://news.google.com/rss/search?q=정부지원금+정책&hl=ko&gl=KR&ceid=KR:ko",
    },
    "realestate": {
        "정책브리핑":   "https://www.korea.kr/rss/policy.xml",
        "부동산뉴스":   "https://news.google.com/rss/search?q=부동산+청약&hl=ko&gl=KR&ceid=KR:ko",
    },
}

GOOGLE_TREND_RSS = "https://trends.google.com/trending/rss?geo=KR"


def _is_safe(text: str) -> bool:
    """안전 필터: 정치/연예/자극/사건사고 제외."""
    if not text:
        return False
    for bad in BLOCK_KEYWORDS:
        if bad in text:
            return False
    return True


def _fetch_rss(url: str, limit: int = 20):
    """RSS에서 (제목, 설명) 추출. (일시적 연결끊김 대비 1회 재시도)"""
    try:
        r = None
        for attempt in range(2):
            try:
                r = requests.get(url, headers=UA, timeout=12)
                break
            except requests.exceptions.ConnectionError:
                if attempt == 1:
                    raise
        if r.status_code != 200:
            print(f"   [trend] RSS {r.status_code}: {url[:50]}")
            return []
        root = ET.fromstring(r.content)
        items = []
        for it in root.findall(".//item")[:limit]:
            title_el = it.find("title")
            desc_el = it.find("description")
            import html as _html
            title = ""
            if title_el is not None and title_el.text:
                title = _html.unescape(title_el.text).strip()
            desc = ""
            if desc_el is not None and desc_el.text:
                # HTML 태그 제거 + 엔티티 정리
                desc = re.sub(r"<[^>]+>", "", desc_el.text)
                desc = _html.unescape(desc).strip()[:300]
            if title:
                items.append({"title": title, "desc": desc})
        return items
    except Exception as e:
        print(f"   [trend] RSS 실패 {url[:40]}: {e}")
        return []


def fetch_google_trends(limit: int = 15):
    """구글 실시간 급상승 검색어."""
    items = _fetch_rss(GOOGLE_TREND_RSS, limit=limit)
    safe = [it for it in items if _is_safe(it["title"])]
    return safe


def fetch_category_news(category: str, limit: int = 15):
    """카테고리별 뉴스 수집 (안전 필터 적용)."""
    results = []
    # 구글 뉴스 (finance, ai, trending)
    if category in GOOGLE_NEWS_FEEDS:
        for it in _fetch_rss(GOOGLE_NEWS_FEEDS[category], limit=limit):
            if _is_safe(it["title"]) and _is_safe(it["desc"]):
                results.append(it)
    # 카테고리 전용 검색 RSS (ai 등 — 적중률 높은 최신 뉴스)
    if category in SEARCH_FEEDS:
        for url in SEARCH_FEEDS[category]:
            for it in _fetch_rss(url, limit=limit):
                if _is_safe(it["title"]) and _is_safe(it["desc"]):
                    results.append(it)
    # 언론사 경제 (finance)
    if category == "finance":
        for name, url in PRESS_FEEDS.items():
            for it in _fetch_rss(url, limit=limit):
                if _is_safe(it["title"]) and _is_safe(it["desc"]):
                    results.append(it)
    # 정책/부동산 소스 (money, realestate)
    if category in POLICY_FEEDS:
        for name, url in POLICY_FEEDS[category].items():
            for it in _fetch_rss(url, limit=limit):
                if _is_safe(it["title"]) and _is_safe(it["desc"]):
                    results.append(it)
    return results


def collect_all_trends():
    """전체 트렌드 수집 — 디버깅/검증용 진입점."""
    out = {
        "google_trends": fetch_google_trends(limit=15),
        "finance_news":  fetch_category_news("finance", limit=10),
        "ai_news":       fetch_category_news("ai", limit=10),
    }
    return out


import os
import json as _json

def convert_trends_to_topics(category: str, news_items: list, max_topics: int = 5) -> list:
    """
    뉴스 묶음을 직장인 [category] 블로그 주제로 변환.
    - 뉴스 제목+요약을 자세히 전달
    - 카테고리에 안 맞으면 Gemini가 SKIP
    - 반환: [{"topic": "...", "source_news": "...", "angle": "..."}, ...]
    """
    GEMINI_API_KEY = os.getenv("GEMINI_API_KEY")
    if not GEMINI_API_KEY or not news_items:
        return []

    # 카테고리별 관점 가이드
    angle_guide = {
        "finance":    "직장인 재테크/투자/자산관리 관점. 종목 추천 금지. 직장인이 실제 행동할 수 있는 각도.",
        "ai":         "직장인 실무 활용 또는 사업 활용 관점. 새 AI 도구면 직장인이 어떻게 쓰는지.",
        "money":      "직장인이 받을 수 있는 지원금/복지/절약 꿀팁 관점.",
        "realestate": "직장인 내집마련/청약/전월세/대출 관점. 실시간 지역 이슈 포함.",
        "trending":   "직장인 건강/라이프/자기계발 관점.",
    }
    guide = angle_guide.get(category, "직장인 관점")

    # 뉴스 묶음 텍스트 (제목 + 요약 자세히)
    news_text = ""
    for i, it in enumerate(news_items[:12], 1):
        news_text += f"{i}. 제목: {it['title']}\n"
        if it.get("desc"):
            news_text += f"   요약: {it['desc']}\n"

    prompt = f"""아래는 오늘 수집한 실시간 뉴스/트렌드입니다. 직장인 블로그 '{category}' 카테고리에 쓸 글 주제로 변환하세요.

[카테고리 관점] {guide}

[중요 규칙]
1. 뉴스 내용을 그대로 쓰지 말 것. 뉴스는 "지금 이게 화제"라는 신호로만 활용.
2. 직장인이 검색하고 실제 도움받을 수 있는 구체적 글 주제로 변환.
3. 카테고리 관점과 안 맞는 뉴스는 과감히 버릴 것 (억지로 만들지 말 것).
4. 정치/연예/자극적/사건사고 관련은 무조건 제외.
5. 최대 {max_topics}개만. 정말 좋은 것만. 없으면 빈 배열.

[수집된 뉴스]
{news_text}

[출력 형식] 반드시 JSON 배열만 출력. 설명 없이.
[{{"topic": "직장인이 검색할 구체적 글 제목", "source_news": "근거가 된 뉴스 핵심", "angle": "직장인에게 주는 가치 한 줄"}}]
맞는 게 없으면: []"""

    # automation.py와 동일 모델 사용 (gemini-2.5-flash)
    url = f"https://generativelanguage.googleapis.com/v1beta/models/gemini-2.5-flash:generateContent?key={GEMINI_API_KEY}"
    payload = {
        "contents": [{"parts": [{"text": prompt}]}],
        "generationConfig": {
            "temperature": 0.7,
            "topP": 0.9,
            "maxOutputTokens": 4000,
            "responseMimeType": "application/json",
            # thinking 끔: 변환은 가벼운 작업 + 2.5-flash thinking 토큰이 출력한도
            # 잠식하는 함정 회피 + 호출 부하 경감 (503 스파이크 영향 축소).
            "thinkingConfig": {"thinkingBudget": 0},
        },
    }
    import requests as _rq
    import time as _time
    # 2.5-flash는 "high demand" 503 스파이크가 잦음 → 재시도 5회 + 긴 백오프로
    # 스파이크 구간(보통 수십 초~1분)을 넘긴다. (트렌드 채택 0건의 근본 원인)
    MAX_RETRY = 5
    for attempt in range(MAX_RETRY):
        try:
            r = _rq.post(url, headers={"Content-Type": "application/json"}, json=payload, timeout=45)
            if r.status_code in (429, 500, 503):
                # 과부하/일시 오류 → 점증 백오프 재시도 (최대 ~45초까지 대기)
                wait = min(45, 9 * (attempt + 1))
                if attempt < MAX_RETRY - 1:
                    print(f"   [트렌드변환 API {r.status_code}] 재시도 {attempt+1}/{MAX_RETRY} ({wait}초 대기)")
                    _time.sleep(wait)
                    continue
                print(f"   [트렌드변환 실패] {r.status_code} {MAX_RETRY}회 모두 실패 (high demand 스파이크) → 시드풀 폴백")
                return []
            if r.status_code != 200:
                print(f"   [트렌드변환 API {r.status_code}] → 시드풀 폴백")
                return []
            text = r.json()["candidates"][0]["content"]["parts"][0]["text"].strip()
            # JSON 추출 (```json 감싸진 경우 제거)
            text = re.sub(r"^```(?:json)?\s*", "", text)
            text = re.sub(r"\s*```$", "", text).strip()
            topics = _json.loads(text)
            if isinstance(topics, list):
                valid = [t for t in topics if isinstance(t, dict) and t.get("topic")]
                return valid[:max_topics]
            return []
        except Exception as e:
            print(f"   [트렌드변환 실패] {e}")
            _time.sleep(3)
    return []


if __name__ == "__main__":
    print("="*52)
    print("  트렌드 수집 + 변환 테스트")
    print("="*52)

    for cat in ["finance", "ai", "money", "realestate", "trending"]:
        print(f"\n{'='*52}")
        print(f"  [{cat}] 뉴스 수집")
        print('='*52)
        news = fetch_category_news(cat, limit=10)
        print(f"  수집된 뉴스: {len(news)}개")
        for it in news[:6]:
            print(f"    - {it['title'][:50]}")

        if news and os.getenv("GEMINI_API_KEY"):
            print(f"\n  [{cat}] → 직장인 주제로 변환 중...")
            topics = convert_trends_to_topics(cat, news, max_topics=3)
            print(f"  변환된 주제: {len(topics)}개")
            for t in topics:
                print(f"    ✓ {t['topic']}")
                print(f"       근거: {t.get('source_news','')[:50]}")
                print(f"       가치: {t.get('angle','')[:50]}")
        else:
            print("  (GEMINI_API_KEY 없거나 뉴스 없음 → 변환 스킵)")
