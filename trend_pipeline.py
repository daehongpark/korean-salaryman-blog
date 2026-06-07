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
    "finance": "https://news.google.com/rss/headlines/section/topic/BUSINESS?hl=ko&gl=KR&ceid=KR:ko",
    "ai":      "https://news.google.com/rss/headlines/section/topic/TECHNOLOGY?hl=ko&gl=KR&ceid=KR:ko",
}

# ── 언론사 경제 RSS ──
PRESS_FEEDS = {
    "연합경제": "https://www.yna.co.kr/rss/economy.xml",
    "전자신문": "https://rss.etnews.com/Section901.xml",
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
    """RSS에서 (제목, 설명) 추출."""
    try:
        r = requests.get(url, headers=UA, timeout=12)
        if r.status_code != 200:
            print(f"   [trend] RSS {r.status_code}: {url[:50]}")
            return []
        root = ET.fromstring(r.content)
        items = []
        for it in root.findall(".//item")[:limit]:
            title_el = it.find("title")
            desc_el = it.find("description")
            title = (title_el.text or "").strip() if title_el is not None else ""
            desc = ""
            if desc_el is not None and desc_el.text:
                # HTML 태그 제거
                desc = re.sub(r"<[^>]+>", "", desc_el.text).strip()[:300]
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
    # 구글 뉴스
    if category in GOOGLE_NEWS_FEEDS:
        for it in _fetch_rss(GOOGLE_NEWS_FEEDS[category], limit=limit):
            if _is_safe(it["title"]) and _is_safe(it["desc"]):
                results.append(it)
    # 언론사 경제 (finance/money/realestate에 공통 활용)
    if category in ("finance", "money", "realestate"):
        for name, url in PRESS_FEEDS.items():
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


if __name__ == "__main__":
    print("="*52)
    print("  트렌드 수집 테스트")
    print("="*52)
    data = collect_all_trends()
    print(f"\n[구글 실시간 트렌드] {len(data['google_trends'])}개 (안전필터 후)")
    for it in data["google_trends"][:10]:
        print(f"  - {it['title']}")
    print(f"\n[finance 뉴스] {len(data['finance_news'])}개")
    for it in data["finance_news"][:8]:
        print(f"  - {it['title'][:50]}")
        if it["desc"]:
            print(f"      {it['desc'][:80]}")
    print(f"\n[ai 뉴스] {len(data['ai_news'])}개")
    for it in data["ai_news"][:8]:
        print(f"  - {it['title'][:50]}")
