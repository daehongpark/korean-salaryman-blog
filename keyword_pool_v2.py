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
        "청년정책 모음", "청년도약계좌 가입조건", "청년도약계좌 중도해지",
        "청년월세 특별지원", "청년내일채움공제 신청", "근로장려금 신청자격",
        "근로장려금 지급일", "자녀장려금 받는 법", "중소기업 취업청년 소득세 감면",
        "긴급복지지원 신청", "에너지바우처 신청", "국민내일배움카드 사용처",
        "평생교육바우처", "문화누리카드 잔액", "출산지원금 지자체별",
        "부모급여 신청조건", "전기요금 복지할인", "통신비 감면 대상",
        "국민취업지원제도", "근로자 휴가지원사업", "직장인 복지포인트 사용처",
        "기업 복지몰 할인", "직장인 커피 할인 혜택", "신용카드 숨은 혜택 찾기",
        "카드 포인트 현금화", "통신사 멤버십 100% 활용", "직장인 점심값 아끼는 법",
        "급여통장 우대 은행 비교", "고이율 월급적금 은행", "주거래은행 등급 올리기",
        "은행 수수료 면제 조건", "체크카드 혜택 비교", "교통비 환급 K패스",
        "알뜰교통카드 전환", "연말정산 환급 많이 받는 법", "숨은 정부지원금 찾기",
        "보조금24 조회", "미환급금 찾기", "건강보험 환급금 조회",
        "국민연금 추납 제도", "실업급여 조건 정리", "직장인 절세 꿀팁",
    ],
    "ai": [
        # 비교/큐레이션/최신 각도 (입문 설명·올드 자동화툴 제거 — 2026.06 박대홍 지시)
        "최신 AI 모델 비교", "Claude vs ChatGPT vs Gemini 업무별 추천",
        "직장인 보고서 작성 최강 AI", "AI 코딩 도구 비교",
        "무료 AI 이미지 생성 비교", "AI 검색 서비스 비교",
        "용도별 최강 AI 정리", "엑셀 작업 최강 AI 비교",
        "PPT 자동 생성 AI 비교", "회의록 정리 AI 추천",
        "긴 문서 요약 AI 비교", "번역 품질 좋은 AI 비교",
        "코드 리뷰 AI 도구 비교", "AI 노트앱 비교",
        "ChatGPT 유료 구독 가치 분석", "Claude vs ChatGPT 코딩 비교",
        "AI 영상 편집 도구 비교", "AI 음성 받아쓰기 도구 비교",
        "데이터 분석 AI 도구 비교", "Perplexity vs Gemini 검색 비교",
        "직장인 업무 자동화 AI 추천", "AI 이메일 작성 도구 비교",
        "국산 AI 서비스 비교", "최신 AI 에이전트 도구 정리",
        "AI 발표자료 디자인 도구 비교", "AI 챗봇 성능 비교",
        "무료로 쓰는 AI 도구 모음", "직장인 AI 구독료 가성비 비교",
        "코딩 어시스턴트 AI 비교", "회사 보안 지키며 AI 쓰는 법",
    ],
    "startup": [
        "직장인 부업 추천", "직장인 사업자등록 방법", "부업 종합소득세 신고",
        "투잡 회사 안 걸리게", "부업 4대보험 문제", "스마트스토어 직장인",
        "쿠팡파트너스 수익", "블로그 애드센스 시작", "유튜브 부업 현실",
        "전자책 출판 방법", "크몽 재능판매", "배달 부업 수익",
        "주말 알바 절세", "1인 사업자 비용처리", "간이과세 일반과세 차이",
        "사업용 통장 분리", "홈택스 부가세 신고", "프리랜서 3.3% 환급",
        "온라인 쇼핑몰 창업", "구매대행 시작하기", "무재고 판매 방법",
        "부업 아이템 찾기", "퇴사 전 준비사항", "사업계획서 쓰는 법",
        "정부 창업지원 사업", "부업 세금 폭탄 피하기", "N잡러 시간관리",
        "유튜브 쇼핑 입점", "무자본 부업 모음", "부업 수익 인증",
    ],
    "finance": [
        "S&P500 ETF 비교", "나스닥100 ETF 추천", "TIGER vs KODEX",
        "월배당 ETF 직장인", "직장인 ETF 고르는 법", "ISA 계좌 200% 활용",
        "ISA vs 연금저축 vs IRP", "연금저축 세액공제 한도", "IRP 직장인 절세",
        "연금저축 갈아타기", "고금리 적금 비교", "파킹통장 금리 비교",
        "직장인 종합소득세", "배당소득세 절세", "금 투자 방법",
        "달러 투자 전략", "퇴직연금 운용 방법", "DC형 DB형 차이",
        "연말정산 카드 공제", "월급 통장 쪼개기", "비상금 마련 전략",
        "직장인 대출 갈아타기", "신용점수 올리는 법", "재테크 우선순위 정리",
        "1억 모으기 현실 전략", "리츠 투자 직장인", "절세 계좌 우선순위",
        "AI 반도체 섹터 동향", "2차전지 산업 흐름", "방산주 관심 배경",
        "원전 르네상스 이슈", "글로벌 금리 흐름 읽기", "환율이 월급에 미치는 영향",
        "인플레이션 시대 자산관리", "美 빅테크 시장 동향", "K-방산 수출 이슈",
        "전기차 캐즘 현황", "바이오 섹터 트렌드", "요즘 뜨는 투자 테마",
        "경제 뉴스 직장인 해석법",
    ],
    "realestate": [
        "주택청약 1순위 조건", "청약통장 납입 인정액", "특별공급 자격 총정리",
        "신생아 특공 조건", "신혼부부 특별공급", "생애최초 특별공급",
        "공공분양 사전청약", "디딤돌대출 조건", "버팀목 전세자금대출",
        "전세 보증금 반환보증", "전세사기 예방법",
        "깡통전세 확인법", "등기부등본 보는 법", "전입신고 확정일자",
        "임대차 계약 주의사항", "월세 세액공제", "DSR 규제 계산",
        "LTV DTI 차이", "내집마련 자금계획", "역전세 대응법",
        "전세 vs 월세 비교", "부동산 취득세 계산", "양도세 비과세 요건",
        "서울 아파트 청약 일정", "수도권 분양 단지 정리", "경기도 입주 물량 이슈",
        "GTX 노선 수혜 지역", "재건축 추진 단지 현황", "신도시 청약 전략",
        "지방 미분양 현황", "전세가율 높은 지역", "직장인 통근 좋은 지역",
        "전월세 신고제 의무", "오피스텔 투자 주의", "분양가상한제 단지 찾는 법",
        "청약 가점 계산 전략", "무순위 청약 신청 방법", "임장 체크리스트",
        "부동산 시장 분위기 읽기", "특별공급 vs 일반공급 전략", "청약 통장 갈아타기 전략",
    ],
    "trending": [
        "직장인 번아웃 극복", "직장인 우울증 신호", "퇴근 후 운동 루틴",
        "직장인 홈트 추천", "직장인 다이어트 현실", "직장인 수면 개선법",
        "점심시간 활용법", "직장인 영양제 추천", "직장인 허리 건강",
        "거북목 교정 운동", "직장인 스트레스 관리", "직장인 눈 건강",
        "직장인 손목 통증", "직장인 식단 관리", "직장인 금연 성공법",
        "직장인 절주 방법", "직장인 명상 효과와 방법", "직장인 아침 루틴",
        "직장인 저녁 루틴", "직장인 주말 회복법", "직장인 멘탈 관리",
        "직장인 디지털 디톡스", "직장인 자세 교정", "직장인 두통 원인",
        "직장인 위장 건강", "직장인 면역력 관리", "직장인 카페인 줄이기",
        "직장인 간헐적 단식", "직장인 걷기 운동", "직장인 스트레칭 루틴",
        "직장인 건강검진 항목", "직장인 취미 추천", "직장인 여행 코스",
        "주말 당일치기 여행", "직장인 독서 습관", "직장인 자기계발 추천",
        "직장인 사이드 프로젝트", "혼밥 맛집 노하우", "직장인 점심 도시락",
        "퇴근 후 자격증", "직장인 영어공부 현실", "워라밸 만드는 법",
        "직장인 연차 활용", "직장인 인간관계", "직장인 연봉 인상률",
        "이직 적정 시기", "주 4일제 도입 현황", "유연근무제 신청",
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
        "1인 사업자 책 추천", "마케팅 실무 책 추천",
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
    "money":      0.15,
    "ai":         0.10,
    "finance":    0.30,
    "startup":    0.10,
    "realestate": 0.20,
    "trending":   0.15,
    "book":       0.00,
}


# ═══════════════════════════════════════════════════════
#  카테고리별 글 유형 힌트 (프롬프트가 이걸 보고 형식 결정)
# ═══════════════════════════════════════════════════════
CATEGORY_INTENTS = {
    "money": {
        "primary_format": "step_by_step",   # 단계별 신청 가이드
        "format_pool":    ["step_by_step", "comparison", "guide", "checklist"],
        "secondary":      "comparison",      # A 정책 vs B 정책 비교
        "tone":           "objective",       # 객관 정보 위주
        "needs_official_link": True,         # 정부 공식 사이트 링크 필수
        "audience":       "정부지원금 신청을 검토하는 직장인·청년",
        "label":          "정부 지원금/정책",
        "emoji":          "💰",
    },
    "ai": {
        "primary_format": "how_to",
        "format_pool":    ["how_to", "comparison", "guide", "experience"],
        "secondary":      "comparison",
        "tone":           "practical",       # 실전 위주
        "needs_official_link": False,
        "audience":       "업무에 AI를 활용하고 싶은 직장인",
        "label":          "AI 도구 활용",
        "emoji":          "🤖",
    },
    "startup": {
        "primary_format": "guide",
        "format_pool":    ["guide", "step_by_step", "checklist", "comparison"],
        "secondary":      "step_by_step",
        "tone":           "practical",
        "needs_official_link": True,         # 사업자등록 등 공식 절차 링크
        "audience":       "직장인 부업 → 1인 사업자 전환을 검토하는 사람",
        "label":          "초기 사업자 가이드",
        "emoji":          "🚀",
    },
    "finance": {
        "primary_format": "comparison",      # A vs B 비교 우선
        "format_pool":    ["comparison", "step_by_step", "guide", "insight"],
        "secondary":      "step_by_step",
        "tone":           "data_driven",     # 숫자/근거 중심
        "needs_official_link": True,
        "audience":       "월급 200~400만원 직장인 투자 초·중급자",
        "label":          "재테크/투자",
        "emoji":          "📈",
    },
    "realestate": {
        "primary_format": "guide",
        "format_pool":    ["guide", "checklist", "step_by_step", "comparison"],
        "secondary":      "checklist",
        "tone":           "objective",
        "needs_official_link": True,
        "audience":       "청약·전월세·주거지원을 알아보는 직장인",
        "label":          "부동산/주거",
        "emoji":          "🏠",
    },
    "trending": {
        "primary_format": "insight",         # 분석/해석
        "format_pool":    ["insight", "comparison", "step_by_step", "guide"],
        "secondary":      "step_by_step",
        "tone":           "analytical",
        "needs_official_link": True,
        "audience":       "정책 변경이 본인에게 미치는 영향을 알고 싶은 직장인",
        "label":          "실시간 이슈",
        "emoji":          "🔥",
    },
    "book": {
        "primary_format": "experience",      # 책 읽고 본인 경험 녹임
        "format_pool":    ["experience", "guide", "insight"],
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
