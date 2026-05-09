# -*- coding: utf-8 -*-
"""
keyword_pool_v2.py
────────────────────────────────────────────────────────────
2026 블로그 전략 — 통일 7개 카테고리 (영문 키 시스템).

[카테고리 키 / 라벨 / 이모지]
- money       / 정부 지원금/정책      / 💰
- ai          / AI 도구 활용          / 🤖
- startup     / 초기 사업자 가이드    / 🚀
- finance     / 재테크/투자           / 📈
- realestate  / 부동산/주거           / 🏠
- trending    / 실시간 이슈           / 🔥
- book        / 책 추천               / 📚

[발행 비율 기본값]  money 28 / ai 22 / startup 12 / finance 18 / realestate 10 / trending 5 / book 5
────────────────────────────────────────────────────────────
"""

# ═══════════════════════════════════════════════════════
#  메인 키워드 풀 (시드 — 자동완성/연관어로 확장됨)
# ═══════════════════════════════════════════════════════
KEYWORD_POOL_V2 = {
    "money": [
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
    "ai": [
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
    "startup": [
        # 사업자 등록 / 절차
        "직장인 사업자등록 가능", "1인 사업자 등록 방법", "간이과세자 vs 일반과세자",
        "직장인 부업 사업자등록 절차", "사업자등록 후 4대보험",
        # 세무 기초
        "1인 사업자 세금 신고", "부가가치세 신고 방법 초보", "종합소득세 신고 직장인",
        "직장인 사업소득 절세", "프리랜서 종합소득세",
        # 통장/카드
        "사업자 통장 추천", "사업용 신용카드 추천", "사업자 비용처리 가능 항목",
        # 마케팅 시작
        "초기 사업자 마케팅", "1인 사업자 SNS 운영", "스마트스토어 시작하기",
        # 위험 회피
        "사업 초기 흔한 실수", "직장인 부업 회사 적발",
        # 부수입 (합법)
        "직장인 부업 합법 범위", "회사 몰래 부업 위험",
    ],
    "finance": [
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
    "realestate": [
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
    "trending": [
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
    "book": [
        # 자기계발 고전
        "원칙 레이달리오 요약", "데일카네기 인간관계론 정리", "성공하는 사람들의 7가지 습관 핵심",
        "타이탄의 도구들 요약", "그릿 GRIT 정리",
        # 직장인/커리어
        "직장인 필독서 추천", "이직 준비 책", "30대 직장인 책 추천",
        # 재테크/투자
        "워런 버핏 추천 책", "현명한 투자자 요약", "월급쟁이 재테크 책",
        # 사업/마케팅
        "1인 사업자 책 추천", "마케팅 책 추천 기초",
        # 심리/관계
        "자존감 수업 후기", "감정 관리 책 추천",
        # 박대홍 본인 추천
        "박대홍 인생책", "20대에 읽었어야 할 책",
    ],
}


# ═══════════════════════════════════════════════════════
#  발행 비율 (한 카테고리에 글 몰리지 않도록)
# ═══════════════════════════════════════════════════════
CATEGORY_BALANCE = {
    "money":      0.28,   # CPC 매우 높음, 검색량 폭발
    "ai":         0.22,   # 떠오르는 카테고리, 차별화 핵심
    "startup":    0.12,   # 직장인 → 사업자 전환 가이드
    "finance":    0.18,   # 고CPC, 꾸준한 수요
    "realestate": 0.10,   # 고CPC, 의사결정 정보
    "trending":   0.05,   # 속보형, 트렌드 캐치용
    "book":       0.05,   # 책 추천 (박대홍 정체성)
}


# ═══════════════════════════════════════════════════════
#  카테고리별 글 유형 힌트 (프롬프트가 이걸 보고 형식 결정)
# ═══════════════════════════════════════════════════════
CATEGORY_INTENTS = {
    "money": {
        "primary_format": "step_by_step",   # 단계별 신청 가이드
        "secondary":      "comparison",      # A 정책 vs B 정책 비교
        "tone":           "objective",       # 객관 정보 위주
        "needs_official_link": True,         # 정부 공식 사이트 링크 필수
        "audience":       "정부지원금 신청을 검토하는 직장인·청년",
        "label":          "정부 지원금/정책",
        "emoji":          "💰",
    },
    "ai": {
        "primary_format": "how_to",
        "secondary":      "comparison",
        "tone":           "practical",       # 실전 위주
        "needs_official_link": False,
        "audience":       "업무에 AI를 활용하고 싶은 직장인",
        "label":          "AI 도구 활용",
        "emoji":          "🤖",
    },
    "startup": {
        "primary_format": "guide",
        "secondary":      "step_by_step",
        "tone":           "practical",
        "needs_official_link": True,         # 사업자등록 등 공식 절차 링크
        "audience":       "직장인 부업 → 1인 사업자 전환을 검토하는 사람",
        "label":          "초기 사업자 가이드",
        "emoji":          "🚀",
    },
    "finance": {
        "primary_format": "comparison",      # A vs B 비교 우선
        "secondary":      "step_by_step",
        "tone":           "data_driven",     # 숫자/근거 중심
        "needs_official_link": True,
        "audience":       "월급 200~400만원 직장인 투자 초·중급자",
        "label":          "재테크/투자",
        "emoji":          "📈",
    },
    "realestate": {
        "primary_format": "guide",
        "secondary":      "checklist",
        "tone":           "objective",
        "needs_official_link": True,
        "audience":       "청약·전월세·주거지원을 알아보는 직장인",
        "label":          "부동산/주거",
        "emoji":          "🏠",
    },
    "trending": {
        "primary_format": "insight",         # 분석/해석
        "secondary":      "step_by_step",
        "tone":           "analytical",
        "needs_official_link": True,
        "audience":       "정책 변경이 본인에게 미치는 영향을 알고 싶은 직장인",
        "label":          "실시간 이슈",
        "emoji":          "🔥",
    },
    "book": {
        "primary_format": "experience",      # 책 읽고 본인 경험 녹임
        "secondary":      "guide",
        "tone":           "balanced",        # 솔직한 평 + 적용기
        "needs_official_link": False,
        "audience":       "책 좋아하고 자기계발에 관심있는 직장인",
        "label":          "책 추천",
        "emoji":          "📚",
    },
}


# ═══════════════════════════════════════════════════════
#  Unsplash 썸네일용 단일 쿼리
# ═══════════════════════════════════════════════════════
UNSPLASH_QUERY_V2 = {
    "money":      "korean government policy support",
    "ai":         "artificial intelligence laptop technology",
    "startup":    "small business owner entrepreneur korea",
    "finance":    "money finance investment chart",
    "realestate": "korean apartment real estate building",
    "trending":   "news update breaking analysis",
    "book":       "books reading library cozy",
}


# ═══════════════════════════════════════════════════════
#  Unsplash 본문용 쿼리 풀 (다양성 확보)
# ═══════════════════════════════════════════════════════
UNSPLASH_BODY_QUERIES_V2 = {
    "money": [
        "government building korea", "documents application form",
        "support help hand", "young professional korean",
        "official paperwork", "social welfare assistance",
    ],
    "ai": [
        "ai chatbot interface", "modern laptop coding", "automation workflow",
        "data analysis dashboard", "technology future", "machine learning concept",
    ],
    "startup": [
        "small business owner laptop", "entrepreneur planning", "korean cafe owner",
        "tax document calculator", "first business handshake", "online shop product",
    ],
    "finance": [
        "stock market chart", "financial calculator pen", "savings investment",
        "korean won bills", "etf portfolio analysis", "economy growth",
    ],
    "realestate": [
        "korean apartment exterior", "house keys contract", "real estate model",
        "modern korean home", "apartment building seoul", "moving home boxes",
    ],
    "trending": [
        "news headline breaking", "policy document official", "economic graph trend",
        "city skyline korea", "interest rate concept", "currency exchange",
    ],
    "book": [
        "open book pages", "bookshelf cozy library", "reading coffee table",
        "highlighted book notes", "stack of books warm light", "person reading window",
    ],
}


# ═══════════════════════════════════════════════════════
#  카테고리 → 블로그 카테고리 페이지 매핑
#  (블로그의 category-*.html 파일과 매핑)
# ═══════════════════════════════════════════════════════
CATEGORY_PAGE_MAP = {
    "money":      "category-money.html",
    "ai":         "category-ai.html",
    "startup":    "category-startup.html",
    "finance":    "category-finance.html",
    "realestate": "category-realestate.html",
    "trending":   "category-trending.html",
    "book":       "category-book.html",
}


# ═══════════════════════════════════════════════════════
#  레거시 한글 키 → 신규 영문 키 매핑 (하위호환)
#  manifest 마이그레이션 + 자동화 fallback에 사용
# ═══════════════════════════════════════════════════════
LEGACY_CATEGORY_MAP = {
    "정부지원금":   "money",
    "AI도구":       "ai",
    "직장인커리어": "startup",   # 부업/사업자 전환에 가까움
    "재테크":       "finance",
    "부동산주거":   "realestate",
    "실시간이슈":   "trending",
    "책 추천":      "book",
    "책추천":       "book",
}


# ═══════════════════════════════════════════════════════
#  단독 테스트
# ═══════════════════════════════════════════════════════
if __name__ == "__main__":
    print("=" * 60)
    print("  2026 블로그 - 통일 7개 카테고리 시스템")
    print("=" * 60)

    total = 0
    for cat, seeds in KEYWORD_POOL_V2.items():
        ratio = CATEGORY_BALANCE.get(cat, 0)
        intent = CATEGORY_INTENTS.get(cat, {})
        emoji = intent.get("emoji", "")
        label = intent.get("label", cat)
        print(f"\n{emoji} [{cat} / {label}] 시드 {len(seeds)}개 / 비율 {ratio:.0%}")
        print(f"   형식: {intent.get('primary_format')}, 톤: {intent.get('tone')}")
        print(f"   대상: {intent.get('audience')}")
        print(f"   샘플: {', '.join(seeds[:3])}")
        total += len(seeds)

    print(f"\n총 시드 키워드: {total}개")
    print(f"\n레거시 매핑 표:")
    for old, new in LEGACY_CATEGORY_MAP.items():
        print(f"   {old:20s} -> {new}")
    print(f"비율 합계: {sum(CATEGORY_BALANCE.values()):.2f} (1.00이어야 함)")
