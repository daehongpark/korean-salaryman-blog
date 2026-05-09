# -*- coding: utf-8 -*-
"""
keyword_pool_v2.py
────────────────────────────────────────────────────────────
2026 블로그 전략에 맞춘 신규 6개 카테고리 키워드 시스템.

[카테고리]
1. 정부지원금/정책   (gov_policy)     — 청년/소상공인/복지 정책, CPC 매우 높음
2. AI 도구 활용      (ai_tools)       — Claude/ChatGPT/n8n 등, 폭발적 성장
3. 직장인 커리어     (career)         — 연봉협상/이직/연말정산
4. 재테크/투자       (finance)        — ETF/ISA/연금/주식, 고CPC
5. 부동산/주거       (realestate)     — 청약/전월세/주거지원
6. 실시간 이슈       (trending)       — 정책 변경/세법 개정/금리 (속보형)

[발행 비율 기본값]  정부 30 / AI 25 / 커리어 15 / 재테크 15 / 부동산 10 / 이슈 5
────────────────────────────────────────────────────────────
"""

# ═══════════════════════════════════════════════════════
#  메인 키워드 풀 (시드 — 자동완성/연관어로 확장됨)
# ═══════════════════════════════════════════════════════
KEYWORD_POOL_V2 = {
    "정부지원금": [
        # 청년 정책
        "2026 청년정책 신청", "청년도약계좌 가입조건", "청년월세 특별지원",
        "청년미래적금 vs 청년도약계좌", "청년내일채움공제 신청",
        "청년 전월세 보증금 대출", "청년창업지원금 신청",
        # 근로/세제
        "근로장려금 신청자격", "자녀장려금 받는 법", "중소기업 취업청년 소득세 감면",
        # 복지
        "기초연금 수급자격", "긴급복지지원 신청", "에너지바우처 신청",
        # 소상공인
        "소상공인 정책자금 1.5%", "예비창업패키지 신청", "청년창업사관학교",
        # 신청 가이드
        "정부24 신청 방법", "복지로 사용법", "정책 신청 서류",
    ],
    "AI도구": [
        # Claude
        "Claude Code 사용법", "Claude vs ChatGPT 비교", "Claude 무료 사용",
        # ChatGPT/Gemini
        "ChatGPT 업무 활용법", "Gemini 한국어 사용법", "AI 챗봇 비교 2026",
        # 자동화
        "n8n 사용법 한국어", "Zapier 무료 자동화", "Make 자동화 워크플로우",
        # 직장인 활용
        "직장인 AI 활용법", "AI로 보고서 작성", "AI 엑셀 자동화",
        "프롬프트 엔지니어링 기초", "AI 이미지 생성 무료",
        # 트렌드
        "ChatGPT 5 사용법", "Cursor AI 코딩", "Perplexity 사용법",
        # 부수입
        "AI로 부업하는 법", "AI 자동화 수익화",
    ],
    "직장인커리어": [
        # 연봉/이직
        "연봉협상 잘하는 법", "이직 시 연봉인상 비율", "경력직 면접 질문",
        "이직 타이밍 직장인", "연봉 인상 협상 화법",
        # 연말정산
        "2026 연말정산 가이드", "연말정산 환급 많이 받는 법", "월세 세액공제 신청",
        "연말정산 부양가족 등록", "13월의 월급 받는 법",
        # 자기계발/자격증
        "직장인 가성비 자격증", "직장인 영어공부 루틴", "퇴근 후 자격증 준비",
        # 직장 생활
        "직장인 번아웃 극복", "퇴사 vs 이직 결정", "재택근무 효율 높이기",
        # 부업 (현실적)
        "직장인 부업 합법", "회사 몰래 부업 가능 여부",
    ],
    "재테크": [
        # ETF/주식
        "S&P500 ETF 추천 2026", "나스닥100 ETF 비교", "TIGER vs KODEX 차이",
        "월배당 ETF 추천", "직장인 ETF 시작하기",
        # ISA/연금
        "ISA 계좌 비교", "ISA vs 연금저축 vs IRP", "연금저축 세액공제 한도",
        "IRP 가입 조건 직장인", "연금저축 갈아타기",
        # 적금/저축
        "고금리 적금 추천 2026", "청년도약계좌 수익률", "파킹통장 비교",
        # 부수입/절세
        "직장인 종합소득세 신고", "사업소득 분리과세", "주택청약 소득공제",
        # 환율/금리
        "원달러 환율 전망 2026", "미국 금리 인하 영향",
    ],
    "부동산주거": [
        # 청약
        "주택청약 1순위 조건", "특별공급 청년 신청", "공공분양 자격",
        "청약가점 계산법", "추첨제 vs 가점제",
        # 전월세
        "전세대출 한도 2026", "디딤돌대출 자격", "버팀목전세자금대출",
        "월세 환산보증금 계산", "보증금 반환보증 가입",
        # 주거지원
        "행복주택 신청 자격", "역세권청년주택", "신혼희망타운",
        # 부동산 정책
        "DSR 규제 2026", "부동산 세금 개편", "양도세 비과세 요건",
        "취득세 계산 방법",
        # 실전
        "전세사기 예방 체크리스트", "임대차계약 주의사항",
    ],
    "실시간이슈": [
        # 정책 속보
        "2026 새 정책 시행", "최저임금 2026 인상", "세법 개정안 영향",
        # 경제 이슈
        "한국은행 기준금리 발표", "물가상승률 직장인 영향",
        # 사회 이슈 (직장인 관련)
        "주 4일제 도입 기업", "유연근무제 의무화",
        # 부동산 이슈
        "부동산 정책 변경", "청약 제도 개편",
        # 금융 이슈
        "예금자보호 한도 상향", "스트레스 DSR 시행",
    ],
}


# ═══════════════════════════════════════════════════════
#  발행 비율 (한 카테고리에 글 몰리지 않도록)
# ═══════════════════════════════════════════════════════
CATEGORY_BALANCE = {
    "정부지원금":  0.30,   # CPC 매우 높음, 검색량 폭발
    "AI도구":      0.25,   # 떠오르는 카테고리, 차별화 핵심
    "직장인커리어": 0.15,   # 핵심 정체성 유지
    "재테크":      0.15,   # 고CPC, 꾸준한 수요
    "부동산주거":   0.10,   # 고CPC, 의사결정 정보
    "실시간이슈":   0.05,   # 속보형, 트렌드 캐치용
}


# ═══════════════════════════════════════════════════════
#  카테고리별 글 유형 힌트 (프롬프트가 이걸 보고 형식 결정)
# ═══════════════════════════════════════════════════════
CATEGORY_INTENTS = {
    "정부지원금": {
        "primary_format": "step_by_step",   # 단계별 신청 가이드
        "secondary":      "comparison",      # A 정책 vs B 정책 비교
        "tone":           "objective",       # 객관 정보 위주
        "needs_official_link": True,         # 정부 공식 사이트 링크 필수
        "audience":       "정부지원금 신청을 검토하는 직장인·청년",
    },
    "AI도구": {
        "primary_format": "how_to",
        "secondary":      "comparison",
        "tone":           "practical",       # 실전 위주
        "needs_official_link": False,
        "audience":       "업무에 AI를 활용하고 싶은 직장인",
    },
    "직장인커리어": {
        "primary_format": "guide",
        "secondary":      "experience",      # 경험 일부 허용
        "tone":           "balanced",
        "needs_official_link": False,
        "audience":       "이직·연봉협상·연말정산을 준비하는 직장인",
    },
    "재테크": {
        "primary_format": "comparison",      # A vs B 비교 우선
        "secondary":      "step_by_step",
        "tone":           "data_driven",     # 숫자/근거 중심
        "needs_official_link": True,
        "audience":       "월급 200~400만원 직장인 투자 초·중급자",
    },
    "부동산주거": {
        "primary_format": "guide",
        "secondary":      "checklist",
        "tone":           "objective",
        "needs_official_link": True,
        "audience":       "청약·전월세·주거지원을 알아보는 직장인",
    },
    "실시간이슈": {
        "primary_format": "insight",         # 분석/해석
        "secondary":      "step_by_step",
        "tone":           "analytical",
        "needs_official_link": True,
        "audience":       "정책 변경이 본인에게 미치는 영향을 알고 싶은 직장인",
    },
}


# ═══════════════════════════════════════════════════════
#  Unsplash 썸네일용 단일 쿼리
# ═══════════════════════════════════════════════════════
UNSPLASH_QUERY_V2 = {
    "정부지원금":  "korean government policy support",
    "AI도구":      "artificial intelligence laptop technology",
    "직장인커리어": "korean office worker career",
    "재테크":      "money finance investment chart",
    "부동산주거":   "korean apartment real estate building",
    "실시간이슈":   "news update breaking analysis",
}


# ═══════════════════════════════════════════════════════
#  Unsplash 본문용 쿼리 풀 (다양성 확보)
# ═══════════════════════════════════════════════════════
UNSPLASH_BODY_QUERIES_V2 = {
    "정부지원금": [
        "government building korea", "documents application form",
        "support help hand", "young professional korean",
        "official paperwork", "social welfare assistance",
    ],
    "AI도구": [
        "ai chatbot interface", "modern laptop coding", "automation workflow",
        "data analysis dashboard", "technology future", "machine learning concept",
    ],
    "직장인커리어": [
        "office meeting korea", "interview professional", "career growth ladder",
        "business handshake", "office workspace asian", "salary negotiation",
    ],
    "재테크": [
        "stock market chart", "financial calculator pen", "savings investment",
        "korean won bills", "etf portfolio analysis", "economy growth",
    ],
    "부동산주거": [
        "korean apartment exterior", "house keys contract", "real estate model",
        "modern korean home", "apartment building seoul", "moving home boxes",
    ],
    "실시간이슈": [
        "news headline breaking", "policy document official", "economic graph trend",
        "city skyline korea", "interest rate concept", "currency exchange",
    ],
}


# ═══════════════════════════════════════════════════════
#  카테고리 → 블로그 카테고리 페이지 매핑
#  (블로그의 기존 category-*.html 파일과 매핑)
# ═══════════════════════════════════════════════════════
CATEGORY_PAGE_MAP = {
    "정부지원금":  "category-policy.html",
    "AI도구":      "category-ai.html",
    "직장인커리어": "category-job.html",       # 기존 파일 재활용
    "재테크":      "category-money.html",      # 기존 파일 재활용
    "부동산주거":   "category-realestate.html",
    "실시간이슈":   "category-trending.html",
}


# ═══════════════════════════════════════════════════════
#  단독 테스트
# ═══════════════════════════════════════════════════════
if __name__ == "__main__":
    print("=" * 60)
    print("  2026 블로그 - 신규 카테고리 시스템")
    print("=" * 60)

    total = 0
    for cat, seeds in KEYWORD_POOL_V2.items():
        ratio = CATEGORY_BALANCE.get(cat, 0)
        intent = CATEGORY_INTENTS.get(cat, {})
        print(f"\n[{cat}] 시드 {len(seeds)}개 / 비율 {ratio:.0%}")
        print(f"   형식: {intent.get('primary_format')}, 톤: {intent.get('tone')}")
        print(f"   대상: {intent.get('audience')}")
        print(f"   샘플: {', '.join(seeds[:3])}")
        total += len(seeds)

    print(f"\n총 시드 키워드: {total}개")
    print(f"비율 합계: {sum(CATEGORY_BALANCE.values()):.2f} (1.00이어야 함)")
