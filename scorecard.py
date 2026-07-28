# -*- coding: utf-8 -*-
"""
scorecard.py
────────────────────────────────────────────────────────────
발행구조 Phase3 — 보조금24 API 연동 + 쓸모 스코어카드 + 후보 큐.

[레인 구성]
- 정책 레인: 보조금24 후보(주, 코드 GATE 통과분) + site:korea.kr 뉴스(보조, 부족분 보충)
- 딜 레인:   trend_pipeline.fetch_deal_news() (발행구조 Phase2에서 만든 딜 검색 피드)

[GATE — 코드 기반, Gemini 미사용]
- 소득: supportConditions JA02xx 중위소득 구간 코드 (gov24_client.income_gate)
- 지역: 소관기관유형 (gov24_client.region_gate) — 광역시·도/전국 PASS, 소도시 전용 REJECT
- 마감: 신청기한 자유서술 파싱 (gov24_client.parse_deadline) — 지난 것만 REJECT

[Gemini 사용 — 코드로 판정 불가한 것만, 10건 배치 1회 호출]
- 딜 레인 GATE (뻔함/시의성없음/출처불명)
- 실이득 3줄 요약(얼마/조건/신청법) — 지원내용 텍스트에서 추출, 불명확하면 "확인필요"
- 세그먼트 분류(청년/신혼부부/가정/시즌)

발행(포스팅)은 하지 않는다 — 여기서는 posts/candidates.json 후보 큐만 만든다.
────────────────────────────────────────────────────────────
"""

from __future__ import annotations

import json
import logging
import math
import os
import re
import sys
import time
from collections import Counter
from datetime import datetime, timedelta, timezone, date
from pathlib import Path

import requests

try:
    from dotenv import load_dotenv
    load_dotenv()
except ImportError:
    pass

# Windows 콘솔(cp949)에서 한글/이모지 출력 시 UnicodeEncodeError 방지
if sys.stdout.encoding and sys.stdout.encoding.lower() != "utf-8":
    try:
        sys.stdout.reconfigure(encoding="utf-8")
        sys.stderr.reconfigure(encoding="utf-8")
    except Exception:
        pass

import gov24_client
import trend_pipeline
import automation  # 기존 중복 가드(TOPIC_GROUPS 등) 재사용

logger = logging.getLogger("scorecard")
if not logger.handlers:
    _h = logging.StreamHandler()
    _h.setFormatter(logging.Formatter(
        "[%(asctime)s] %(levelname)s scorecard: %(message)s",
        "%Y-%m-%d %H:%M:%S"
    ))
    logger.addHandler(_h)
    logger.setLevel(logging.INFO)

KST = timezone(timedelta(hours=9))
GEMINI_API_KEY = os.getenv("GEMINI_API_KEY")

SCRIPT_DIR = Path(__file__).parent
POSTS_DIR = SCRIPT_DIR / "posts"
CANDIDATES_PATH = POSTS_DIR / "candidates.json"
HEALTH_PATH = POSTS_DIR / "source_health.json"

ALLOCATION = {"trending": 3, "money": 3, "realestate": 2}
TRENDING_DEAL_MIN = 2


# ═══════════════════════════════════════════════════════
#  Phase3.5 — 적격 판정 엄격화 (박대홍 지시 2026-07-27)
#  ✅는 "연 3천~맞벌이 직장인이 명백히 대상"일 때만. 아래 중 하나라도 있으면 ⚠️로 낮춘다.
# ═══════════════════════════════════════════════════════

_INCOME_CAP_KEYWORD_PATTERN = re.compile(r"(부부합산|가구|연소득|총소득)")
_MEDIAN_INCOME_KEYWORDS = ["중위소득 100%", "기준 중위소득 100%", "중위소득 100퍼센트"]
_INDUSTRY_SIZE_KEYWORDS = ["제조업", "건설업", "제조·건설업", "50인 미만", "5인 이상", "중소기업", "소기업", "중견기업"]
# "만 19세 이상"처럼 성인 기준 하한(플로어)은 사실상 전 국민이 충족하므로 상한이 아니다.
# "이하/미만"이 바로 뒤에 붙는 경우만 진짜 연령 상한으로 본다.
_AGE_CAP_PATTERN = re.compile(r"만\s*(\d{1,2})\s*세\s*(?:이하|미만)")


_INCOME_SCALE_UNITS = {"천만", "억"}  # 가구 연소득은 늘 이 단위로 표현됨. "만원"/"백만원"은
# 지원금·한도 액수(예: "보증료 40만원 상한")일 확률이 높아 소득 상한 판정에서 제외한다.


def _find_income_cap_restriction(text: str) -> str:
    """소득 상한 문구를 찾는다. 정부 문서는 흔히 '연소득 청년 5천만원, 신혼부부 7.5천만원,
    청년 외 6천만원 이하'처럼 '이하'를 여러 금액 뒤에 한 번만 붙이므로, 키워드~문장 끝(또는
    다음 60자) 구간을 통째로 보고 그 구간에 '이하/미만'이 있으면 구간 내 모든 금액 중
    최솟값을 기준으로 판정한다."""
    for km in _INCOME_CAP_KEYWORD_PATTERN.finditer(text):
        window = text[km.end():km.end() + 60]
        # 문장 끝에서 자르되 "7.5천만원" 같은 소수점은 마침표로 오인하지 않는다
        window = re.split(r"\.(?!\d)|\n", window, maxsplit=1)[0]
        if "이하" not in window and "미만" not in window:
            continue
        amounts = []
        for am in _AMOUNT_WON_PATTERN.finditer(window):
            if am.group(2) not in _INCOME_SCALE_UNITS:
                continue
            num = float(am.group(1).replace(",", ""))
            amounts.append((num * _AMOUNT_UNIT_TO_MANWON[am.group(2)], am.group(0)))
        if not amounts:
            continue
        min_manwon, min_text = min(amounts, key=lambda x: x[0])
        if min_manwon <= 7000:
            return f"소득 상한 {km.group(1)} {min_text} 이하"
    return ""


def detect_eligibility_restrictions(item: dict, income_gate: dict, fields: dict = None) -> list:
    """✅ 남발 방지: 소득상한(부부합산 7천만원 이하)/업종·기업규모/연령상한/중위소득100%이하
    중 하나라도 텍스트나 GATE 결과에서 발견되면 사유 목록을 반환한다(비었으면 제한 없음).
    원문(지원대상/지원내용)뿐 아니라 카드에 실제로 표시되는 조건_소득자격 텍스트도 함께 검사한다
    (Gemini 요약이 원문과 다른 문구를 쓰거나 배치 매칭이 어긋나도 카드 표시 내용과 라벨이
    불일치하지 않도록 보장)."""
    text = " ".join([item.get("지원대상") or "", item.get("지원내용") or "",
                      (fields or {}).get("조건_소득자격") or ""])
    restrictions = []

    income_cap = _find_income_cap_restriction(text)
    if income_cap:
        restrictions.append(income_cap)

    if any(k in text for k in _MEDIAN_INCOME_KEYWORDS) or income_gate.get("tier") in ("boundary", "low_only"):
        restrictions.append("중위소득 100% 이하 조건")

    for kw in _INDUSTRY_SIZE_KEYWORDS:
        if kw in text:
            restrictions.append(f"업종·기업규모 제한({kw})")
            break

    am = _AGE_CAP_PATTERN.search(text)
    if am:
        restrictions.append(f"연령 상한(만 {am.group(1)}세)")

    if not restrictions and income_gate.get("tier") == "strong" and income_gate.get("flag"):
        restrictions.append("소득조건 확인필요(정보 없음)")

    return restrictions


# ═══════════════════════════════════════════════════════
#  Phase3.5 — 정책 레인 신선도 훅 (박대홍 지시 2026-07-27)
#  훅 없는 순수 상시 프로그램은 카드로 승격하지 않고 '보관'한다.
# ═══════════════════════════════════════════════════════

def _parse_update_date(value) -> "date | None":
    """gov24 '수정일시' 필드(YYYYMMDDHHMMSS 문자열)를 date로 변환. 실패하면 None."""
    if not value or len(str(value)) < 8:
        return None
    try:
        return datetime.strptime(str(value)[:8], "%Y%m%d").date()
    except ValueError:
        return None


def has_freshness_hook(entry: dict, news_blob: str, today: "date") -> "str | None":
    """정책 후보 카드 승격 조건(Phase3.6, 박대홍 지시 2026-07-27): 아래 3가지만 훅으로 인정한다.
    (a) 스냅샷 신규 등장 (b) 마감 30일 이내 (c) 최근 공고 뉴스와 매칭.
    '수정일시'는 보조금24가 배치로 일괄 갱신하는 경우가 많아 신선도 신호로 부적합 →
    승격 근거에서 제외하고 점수 동점 미세조정(score_gov24_candidate)에만 쓴다.
    하나도 없으면 None(= 상시 전용, 보관 대상)."""
    if entry["is_new"]:
        return "신규 등장"
    if entry["gate"]["deadline"]["status"] == "urgent":
        return "마감 30일 이내"
    name = entry["item"].get("서비스명", "")
    if news_blob and len(name) >= 4 and name in news_blob:
        return "최근 공고 뉴스 매칭"
    return None


# ═══════════════════════════════════════════════════════
#  STEP5 — 소스 헬스체크 상설화
# ═══════════════════════════════════════════════════════

def _load_health() -> dict:
    if HEALTH_PATH.exists():
        try:
            return json.loads(HEALTH_PATH.read_text(encoding="utf-8"))
        except Exception:
            pass
    return {}


def _save_health(h: dict) -> None:
    try:
        POSTS_DIR.mkdir(parents=True, exist_ok=True)
        HEALTH_PATH.write_text(json.dumps(h, ensure_ascii=False, indent=2), encoding="utf-8")
    except Exception as e:
        logger.warning(f"소스 헬스 저장 실패: {e}")


def record_source_health(name: str, ok: bool, detail: str = "") -> None:
    """모든 외부 소스 상태를 매 실행 로그+파일로 남긴다. 연속 3회 실패 시 SOURCE_DOWN 알림."""
    h = _load_health()
    entry = h.get(name, {"consecutive_fail": 0})
    now = datetime.now(KST).isoformat()
    if ok:
        status = "OK"
        entry["consecutive_fail"] = 0
    else:
        status = f"FAIL:{detail}" if detail else "FAIL"
        entry["consecutive_fail"] = entry.get("consecutive_fail", 0) + 1
    entry["last_status"] = status
    entry["last_checked"] = now
    h[name] = entry
    _save_health(h)

    logger.info(f"[헬스체크] {name}: {status}")
    if not ok and entry["consecutive_fail"] >= 3:
        logger.error(f"SOURCE_DOWN: {name} (연속 {entry['consecutive_fail']}회 실패)")


def safe_call(name: str, fn, *args, **kwargs):
    """외부 소스 호출 1건을 감싸 실패해도 전체 파이프라인을 죽이지 않는다."""
    try:
        result = fn(*args, **kwargs)
        record_source_health(name, True)
        return result
    except gov24_client.Gov24Unavailable as e:
        record_source_health(name, False, "키없음/401")
        return None
    except Exception as e:
        record_source_health(name, False, str(e)[:80])
        logger.warning(f"소스 실패({name}), 스킵하고 계속: {e}")
        return None


# ═══════════════════════════════════════════════════════
#  gov24 후보 → 카테고리 분류
# ═══════════════════════════════════════════════════════

_REALESTATE_FIELD = "주거·자립"
_HOUSING_KEYWORDS = ["주택", "전세", "월세", "청약", "임대", "분양", "보증금",
                     "매입임대", "행복주택", "디딤돌", "버팀목", "입주"]
_MONEY_FIELDS = {"생활안정", "고용·창업", "행정·안전"}
_TRENDING_FIELDS = {"임신·출산", "보육·교육", "보호·돌봄", "보건·의료", "문화·환경", "농림축산어업"}


def classify_gov24_category(item: dict) -> str:
    field = item.get("서비스분야") or ""
    text = f"{item.get('서비스명', '')} {item.get('지원내용', '')}"
    if field == _REALESTATE_FIELD:
        return "realestate" if any(k in text for k in _HOUSING_KEYWORDS) else "money"
    if field in _MONEY_FIELDS:
        return "money"
    if field in _TRENDING_FIELDS:
        return "trending"
    return "trending"


# ═══════════════════════════════════════════════════════
#  Phase3.6 — 소스 오염 제거 (박대홍 지시 2026-07-27)
#  "평범한 직장인 대상" 밖의 특수대상/지역특화 정책은 후보 풀 진입 전에 제외한다.
#  제외 키워드는 상수로 분리해 나중에 조정 가능하게 유지.
# ═══════════════════════════════════════════════════════

_SCOPE_EXCLUDE_KEYWORDS = [
    "국가유공자", "보훈", "제대군인", "상이유공자", "상이등급", "참전유공자", "참전용사",
    "독립유공자", "5·18", "5.18", "특수임무유공자", "특수임무수행자", "전몰군경", "전몰",
    "순직", "고엽제후유의증",
]

_REGION_NAME_KEYWORDS = [
    "서울", "부산", "대구", "인천", "광주", "대전", "울산", "세종",
    "경기도", "강원도", "충청북도", "충청남도", "전라북도", "전라남도", "경상북도", "경상남도", "제주",
    "수원", "성남", "고양", "용인", "청주", "전주", "포항", "창원", "안산", "안양", "천안", "김해",
]
_REGIONAL_ORG_TYPES = {"광역시도", "시군구"}


def detect_out_of_scope(item: dict) -> str:
    """평범한 직장인 대상 밖의 특수대상(보훈 계열) 정책이면 제외 사유를 반환, 해당 없으면 빈 문자열."""
    text = f"{item.get('서비스명', '')} {item.get('지원대상', '')}"
    for kw in _SCOPE_EXCLUDE_KEYWORDS:
        if kw in text:
            return f"특수대상(보훈 계열) 제외: {kw}"
    return ""


def detect_regional_specific(item: dict) -> str:
    """소관기관이 광역/시군구 단위이고 서비스명에 특정 지역명이 있으면(=전국 공통이 아님)
    제외 사유를 반환, 해당 없으면 빈 문자열. 중앙행정기관/공공기관 소관은 지역명이 있어도 제외 대상 아님."""
    org_type = (item.get("소관기관유형") or "").strip()
    if org_type not in _REGIONAL_ORG_TYPES:
        return ""
    name = item.get("서비스명", "")
    for region in _REGION_NAME_KEYWORDS:
        if region in name:
            return f"지역특화 제외(전국 공통 아님): {region}"
    return ""


# ═══════════════════════════════════════════════════════
#  중복 가드 (automation.py 재사용)
# ═══════════════════════════════════════════════════════

def build_dedup_context():
    recent_30 = automation._recent_keywords_by_count(30)
    recent_group_kws = automation._recent_keywords_by_count(automation.GROUP_COOLDOWN_POSTS)
    used_groups = set()
    for kw in recent_group_kws:
        g = automation._topic_group(kw)
        if g:
            used_groups.add(g)
    return {"recent_30": recent_30, "used_groups": used_groups}


def is_duplicate(title: str, ctx: dict, run_seen_titles: set) -> bool:
    if automation._has_strong_overlap(title, ctx["recent_30"]):
        return True
    if automation._has_strong_overlap(title, run_seen_titles):
        return True
    if automation._group_in_cooldown(title, ctx["used_groups"]):
        return True
    return False


# ═══════════════════════════════════════════════════════
#  Gemini 배치 호출 (10건씩 1회)
# ═══════════════════════════════════════════════════════

def _gemini_json_call(prompt: str, max_tokens: int = 4000) -> list:
    """trend_pipeline.convert_trends_to_topics와 동일한 백오프 정책의 배치 JSON 호출."""
    if not GEMINI_API_KEY:
        logger.warning("GEMINI_API_KEY 없음 → Gemini 보강 스킵")
        return []
    url = f"https://generativelanguage.googleapis.com/v1beta/models/gemini-2.5-flash:generateContent?key={GEMINI_API_KEY}"
    payload = {
        "contents": [{"parts": [{"text": prompt}]}],
        "generationConfig": {
            "temperature": 0.4,
            "topP": 0.9,
            "maxOutputTokens": max_tokens,
            "responseMimeType": "application/json",
            "thinkingConfig": {"thinkingBudget": 0},
        },
    }
    MAX_RETRY = 3
    for attempt in range(MAX_RETRY):
        try:
            r = requests.post(url, headers={"Content-Type": "application/json"}, json=payload, timeout=45)
            if r.status_code in (429, 500, 503):
                wait = min(30, 8 * (attempt + 1))
                if attempt < MAX_RETRY - 1:
                    logger.warning(f"Gemini {r.status_code} 재시도 {attempt + 1}/{MAX_RETRY} ({wait}초 대기)")
                    time.sleep(wait)
                    continue
                logger.warning(f"Gemini 배치 호출 최종 실패({r.status_code}) → 이 배치는 폴백 처리")
                record_source_health("gemini_api", False, str(r.status_code))
                return []
            if r.status_code != 200:
                logger.warning(f"Gemini API {r.status_code} → 배치 폴백")
                record_source_health("gemini_api", False, str(r.status_code))
                return []
            text = r.json()["candidates"][0]["content"]["parts"][0]["text"].strip()
            text = re.sub(r"^```(?:json)?\s*", "", text)
            text = re.sub(r"\s*```$", "", text).strip()
            parsed = json.loads(text)
            record_source_health("gemini_api", True)
            return parsed if isinstance(parsed, list) else []
        except Exception as e:
            logger.warning(f"Gemini 배치 호출 실패: {e}")
            time.sleep(2)
    record_source_health("gemini_api", False, "예외/재시도소진")
    return []


def gemini_enrich_gov24_batch(items: list) -> dict:
    """gov24 후보(최대 10건)의 실이득 3줄 요약 + 세그먼트 분류. GATE는 이미 코드로 통과함."""
    if not items:
        return {}
    lines = []
    for i, it in enumerate(items):
        lines.append(
            f"{i}. 서비스명: {it['서비스명']}\n"
            f"   지원내용: {(it.get('지원내용') or '')[:400]}\n"
            f"   지원대상: {(it.get('지원대상') or '')[:300]}\n"
            f"   신청방법: {(it.get('신청방법') or '')[:150]}"
        )
    prompt = f"""아래는 보조금24 정부지원 서비스 {len(items)}건이다. 각 항목에서 "평범한 직장인이 실제로 얻는 이득"을
3줄로 뽑아라 (금액/조건/신청법). 지원내용에 구체 금액이 없으면 "확인필요"라고 써라.
세그먼트는 청년/신혼부부/가정/시즌/일반 중 가장 맞는 것 하나만.

[항목들]
{chr(10).join(lines)}

[출력] JSON 배열만. 설명 없이. idx는 위 번호와 동일하게.
[{{"idx":0,"실이득_얼마":"...","조건_소득자격":"...","신청법":"...","세그먼트":"청년|신혼부부|가정|시즌|일반"}}]"""

    result = _gemini_json_call(prompt)
    out = {}
    for r in result:
        idx = r.get("idx")
        if idx is not None and 0 <= idx < len(items):
            out[idx] = r
    return out


def gemini_enrich_external_batch(items: list, lane_hint: str) -> dict:
    """뉴스/딜 등 외부 텍스트(최대 10건)의 GATE + 실이득 3줄 요약 + 세그먼트 분류.
    코드로 판정 불가능한 뻔함/시의성없음/출처불명 GATE를 여기서 수행한다."""
    if not items:
        return {}
    lines = []
    for i, it in enumerate(items):
        lines.append(f"{i}. 제목: {it.get('title', '')}\n   요약: {(it.get('desc') or '')[:250]}")

    prompt = f"""아래는 직장인 블로그 '{lane_hint}' 후보로 수집한 뉴스/딜 {len(items)}건이다.
1) 다음 기준으로 GATE 판정: 너무 뻔한 내용(pass=false), 시의성 없음(pass=false), 출처 불명확(pass=false).
   애매하면 통과(pass=true)시켜라(느슨 원칙).
2) pass=true인 것만 "실이득 3줄"(얼마/조건/신청법)을 뽑아라. 딜이면 조건=구매/참여조건, 신청법=구매/신청 방법.
   불명확하면 "확인필요".
3) 세그먼트는 청년/신혼부부/가정/시즌/일반 중 하나.

[항목들]
{chr(10).join(lines)}

[출력] JSON 배열만. 설명 없이. idx는 위 번호와 동일하게. pass=false면 reject_reason만 채우고 나머지는 빈 문자열.
[{{"idx":0,"pass":true,"reject_reason":"","실이득_얼마":"...","조건_소득자격":"...","신청법":"...","세그먼트":"..."}}]"""

    result = _gemini_json_call(prompt)
    out = {}
    for r in result:
        idx = r.get("idx")
        if idx is not None and 0 <= idx < len(items):
            out[idx] = r
    return out


# ═══════════════════════════════════════════════════════
#  점수 (정렬용, 0~5) — Phase3.5: 시의성 40% > 실이득 규모 30% > 적격 확실성 20% > 신청편의 10%
#  (박대홍 지시 2026-07-27: 기존 5요소 이산버킷 방식은 대부분 같은 버킷에 몰려 전부 4.3으로 수렴함)
# ═══════════════════════════════════════════════════════

_AMOUNT_WON_PATTERN = re.compile(r"(\d[\d,]*(?:\.\d+)?)\s*(억|천만|백만|만)\s*원")
_PERCENT_PATTERN = re.compile(r"(\d{1,3})\s*%")
_AMOUNT_UNIT_TO_MANWON = {"억": 10000, "천만": 1000, "백만": 100, "만": 1}


def _benefit_score_generic(text: str) -> float:
    """실이득 텍스트의 금액/할인율 규모를 0~5 연속값으로 변환 (변별력 확보용)."""
    text = text or ""
    if not text or "확인필요" in text:
        return 0.5
    pm = _PERCENT_PATTERN.search(text)
    if pm:
        pct = int(pm.group(1))
        if pct >= 70:
            return 5.0
        if pct >= 40:
            return 4.0
        if pct >= 20:
            return 3.0
        return 2.0
    best_manwon = 0.0
    for m in _AMOUNT_WON_PATTERN.finditer(text):
        num = float(m.group(1).replace(",", ""))
        best_manwon = max(best_manwon, num * _AMOUNT_UNIT_TO_MANWON[m.group(2)])
    if best_manwon <= 0:
        return 1.5
    if best_manwon >= 1000:
        return 5.0
    if best_manwon >= 300:
        return 4.0
    if best_manwon >= 50:
        return 3.0
    return 2.0


def score_gov24_candidate(item: dict, gate: dict, is_new: bool, fields: dict,
                           restrictions: list, evergreen_fill: bool = False) -> float:
    deadline = gate["deadline"]
    if evergreen_fill:
        # 훅 없이 할당량 채움용으로 온 상시 프로그램 — 시의성 0점 처리
        timeliness = 0.0
    elif is_new:
        timeliness = 5.0
    elif deadline["status"] == "urgent" and deadline.get("days_left") is not None:
        # 마감이 가까울수록 가점(최대 5.0, 30일 남으면 4.0)
        timeliness = round(4.0 + (1 - min(deadline["days_left"], 30) / 30), 2)
    else:
        # 훅 풀에 속한다는 것 자체가 신규/마감임박이 아니면 뉴스 매칭으로 들어온 것.
        # 기본 시의성은 고정 baseline이고, 수정일시는 승격 근거가 아니라 동점 미세조정에만
        # 쓴다(Phase3.6, 박대홍 지시 2026-07-27 — 보조금24 배치 일괄 갱신은 신선도 신호로 부적합).
        timeliness = 2.5
        updated = _parse_update_date(item.get("수정일시"))
        days_since = (gov24_client.today_kst_date() - updated).days if updated else None
        if days_since is not None and 0 <= days_since <= 365:
            timeliness += (1 - days_since / 365) * 0.5  # 최대 +0.5, 미세조정용
        timeliness = round(timeliness, 2)

    # Phase4 (박대홍 지시 2026-07-28): 저소득 전용(JA0201/JA0202만 해당, allow_low_income
    # 완화로만 풀에 들어올 수 있는 항목)은 대상이 아닌 다수 독자에게는 시의성이 아무리 높아도
    # 카드 최상단에 노출되면 안 된다. 완전 제외는 아니고 시의성 가점만 눌러서 정렬 후순위로 보낸다.
    if gate["income"]["tier"] == "low_only":
        timeliness = min(timeliness, 1.0)

    benefit_score = _benefit_score_generic(fields.get("실이득_얼마", ""))
    eligibility_score = {0: 5.0, 1: 3.0}.get(len(restrictions), 1.5)

    apply_text = item.get("신청방법") or ""
    apply_score = 5.0 if any(k in apply_text for k in ("온라인", "모바일", "홈택스", "인터넷")) else 3.0

    # 조회수 기반 미세 변별력(관심도) — 이산 버킷이 같은 후보끼리도 실질적으로 겹치지 않는
    # 연속값이라 동점을 줄여준다. 가중치가 작아 주요 우선순위(시의성>실이득>적격성)는 바뀌지 않는다.
    views = item.get("조회수", 0) or 0
    popularity_score = min(5.0, math.log10(max(views, 1)) * (5.0 / 7))

    score = (timeliness * 0.38 + benefit_score * 0.29 + eligibility_score * 0.19
             + apply_score * 0.1 + popularity_score * 0.04)
    return round(score, 2)


def score_external_candidate(fields: dict, has_link: bool, is_deal: bool) -> float:
    benefit_score = _benefit_score_generic(fields.get("실이득_얼마", ""))
    apply_text = fields.get("신청법", "") or ""
    apply_score = 4.5 if apply_text and "확인필요" not in apply_text else 2.0

    cond_text = fields.get("조건_소득자격", "") or ""
    if is_deal:
        timeliness = 5.0 if any(k in (cond_text + apply_text) for k in ("한정", "마감", "선착순")) else 4.0
    else:
        timeliness = 3.0  # 뉴스 기반 정책 후보는 gov24 신규/마감임박보다 훅 신뢰도가 낮음

    # 외부 후보는 구조화된 자격판정이 없으므로 출처 신뢰도를 적격 확실성 대체값으로 쓴다
    eligibility_score = 5.0 if has_link else 2.0

    score = timeliness * 0.4 + benefit_score * 0.3 + eligibility_score * 0.2 + apply_score * 0.1
    return round(score, 2)


# ═══════════════════════════════════════════════════════
#  gov24 후보 풀 구축 (GATE 적용 + 리젝 샘플 수집)
# ═══════════════════════════════════════════════════════

def build_gov24_pool(cache: dict, snapshot_diff: dict, news_blob: str = "", allow_low_income: bool = False):
    """소스 오염 제거(보훈 계열/지역특화 사전 제외, Phase3.6) 후 GATE 통과분을 신선도 훅 유무로
    나눈다 (Phase3.5, 박대홍 지시 2026-07-27).
    - passed:    훅 있는 후보(카드 승격 대상)
    - evergreen: 훅 없는 상시 프로그램(보관 — 할당량 미달시에만 명시적으로 백필)
    """
    services = cache.get("services", {})
    today = gov24_client.today_kst_date()
    new_ids = snapshot_diff.get("new_ids", set())

    passed = {"trending": [], "money": [], "realestate": []}
    evergreen = {"trending": [], "money": [], "realestate": []}
    rejected_samples = []
    archived_samples = []
    scope_excluded_samples = []

    for sid, item in services.items():
        scope_reason = detect_out_of_scope(item) or detect_regional_specific(item)
        if scope_reason:
            # 전체 건수를 정확히 세기 위해 캡 없이 누적(문자열 3개짜리 dict라 메모리 부담 적음)
            scope_excluded_samples.append({
                "서비스ID": sid, "서비스명": item.get("서비스명"), "사유": scope_reason,
            })
            continue

        gate = gov24_client.apply_gates(item, today=today)
        ok = gate["pass"]
        if not ok and allow_low_income and gate["income"]["tier"] == "low_only" \
                and gate["region"]["pass"] and gate["deadline"]["pass"]:
            ok = True  # STEP4 재시도: 소득 GATE를 저소득까지 완화

        if not ok:
            if len(rejected_samples) < 30:
                rejected_samples.append({
                    "서비스ID": sid, "서비스명": item.get("서비스명"),
                    "사유": " / ".join(gate["reasons"]),
                })
            continue

        cat = classify_gov24_category(item)
        entry = {"item": item, "gate": gate, "is_new": sid in new_ids, "evergreen_fill": False}
        hook = has_freshness_hook(entry, news_blob, today)
        entry["hook"] = hook
        if hook:
            passed[cat].append(entry)
        else:
            evergreen[cat].append(entry)
            if len(archived_samples) < 30:
                archived_samples.append({
                    "서비스ID": sid, "서비스명": item.get("서비스명"),
                    "사유": "상시 전용(신선도 훅 없음) → 보관",
                })

    return passed, evergreen, rejected_samples, archived_samples, scope_excluded_samples


# ═══════════════════════════════════════════════════════
#  카드 조립
# ═══════════════════════════════════════════════════════

def _format_deadline_label(deadline: dict) -> str:
    if deadline["status"] == "none":
        return "상시/미상"
    if deadline["status"] == "expired":
        return f"종료({deadline['next_date']})"
    label = "마감임박" if deadline["status"] == "urgent" else "마감예정"
    return f"{label} {deadline['next_date']} (D-{deadline['days_left']})"


_BENEFIT_LINE_KEYWORDS = ("지원내용", "지원금", "지급", "지원액", "혜택", "지원사항", "지원규모")
_ELIGIBILITY_LINE_KEYWORDS = ("대상", "자격", "재산", "소득기준", "요건", "기준중위소득")


def _fallback_benefit_from_text(item: dict) -> str:
    """Gemini가 '확인필요'로 남겼어도 원문(지원내용)에 금액/할인율이 있으면 그 문장을 그대로
    뽑아 쓴다. LLM 샘플링 변동성에 기대지 않는 결정적 백업(박대홍 지시 2026-07-27,
    '확인필요' 카드가 3개 이상 나오면 안 된다는 검증 기준을 충족하기 위함).
    금액이 있는 줄이 여러 개면 '참여대상: ... 재산 4억원 이하' 같은 자격조건 설명 줄이 아니라
    '지원내용/지급' 같은 혜택 설명 줄을 우선한다."""
    text = item.get("지원내용") or ""
    lines = [l for l in re.split(r"[\r\n]+", text)
             if _AMOUNT_WON_PATTERN.search(l) or _PERCENT_PATTERN.search(l)]
    if not lines:
        return ""

    def rank(line: str) -> int:
        if any(k in line for k in _BENEFIT_LINE_KEYWORDS):
            return 0
        if any(k in line for k in _ELIGIBILITY_LINE_KEYWORDS):
            return 2
        return 1

    lines.sort(key=rank)
    snippet = lines[0].strip(" \r\t○-·ㆍ")
    return snippet[:150] if snippet else ""


def make_gov24_card(entry: dict, fields: dict, category: str, evergreen_fill: bool = False) -> dict:
    item, gate = entry["item"], entry["gate"]
    income = gate["income"]
    restrictions = detect_eligibility_restrictions(item, income, fields)
    if restrictions:
        eligible = f"⚠️{restrictions[0]}"
        disqualifier = restrictions[0]
    else:
        eligible = "✅"
        disqualifier = "뚜렷한 제한 없음(세부조건은 신청 시 확인)"

    benefit_text = fields.get("실이득_얼마") or "확인필요"
    if "확인필요" in benefit_text:
        fallback = _fallback_benefit_from_text(item)
        if fallback:
            benefit_text = fallback
            fields = {**fields, "실이득_얼마": fallback}

    red_flags = []
    if evergreen_fill:
        red_flags.append("상시 전용(신선도 훅 없음, 할당량 채움용)")
    if income["tier"] == "low_only":
        red_flags.append("저소득 전용 항목(GATE 완화 적용)")
    if "확인필요" in benefit_text:
        red_flags.append("실이득 금액 확인필요")

    source_url = item.get("상세조회URL") or ""
    freshness_reason = entry.get("hook") or "상시 전용(신선도 훅 없음, 할당량 채움용)"

    return {
        "제목": item.get("서비스명", ""),
        "카테고리": category,
        "레인": "정책",
        "세그먼트": fields.get("세그먼트", "확인필요") or "확인필요",
        "실이득_얼마": benefit_text,
        "조건_소득자격": fields.get("조건_소득자격", "확인필요") or "확인필요",
        "신청법": fields.get("신청법", item.get("신청방법", "")) or "확인필요",
        "적격": eligible,
        "탈락조건": disqualifier,
        "마감": _format_deadline_label(gate["deadline"]),
        "신선도근거": freshness_reason,
        "점수": score_gov24_candidate(item, gate, entry["is_new"], fields, restrictions, evergreen_fill),
        "레드플래그": red_flags,
        "출처URL": source_url,
        "서비스ID": item.get("서비스ID", ""),
    }


def make_external_card(raw_item: dict, fields: dict, category: str, lane: str) -> dict:
    red_flags = []
    if not fields.get("실이득_얼마") or "확인필요" in (fields.get("실이득_얼마") or ""):
        red_flags.append("실이득 확인필요")
    if not raw_item.get("link"):
        red_flags.append("출처 링크 미확인")

    condition_default = "확인필요" if lane == "정책" else "해당없음"
    condition = fields.get("조건_소득자격") or condition_default
    disqualifier = ("해당없음(구매형 딜, 자격제한 없음)" if lane == "딜"
                     else "적격 조건 확인필요(원문 미분석, 뉴스 기반 후보)")
    freshness_reason = "최근 딜 뉴스(7일 이내 검색 매칭)" if lane == "딜" else "최근 공고 뉴스(7일 이내 검색 매칭)"

    return {
        "제목": raw_item.get("title", ""),
        "카테고리": category,
        "레인": lane,
        "세그먼트": fields.get("세그먼트") or "확인필요",
        "실이득_얼마": fields.get("실이득_얼마") or "확인필요",
        "조건_소득자격": condition,
        "신청법": fields.get("신청법") or "확인필요",
        "적격": "⚠️확인필요" if lane == "정책" else "✅",
        "탈락조건": disqualifier,
        "마감": fields.get("마감") or "확인필요",
        "신선도근거": freshness_reason,
        "점수": score_external_candidate(fields, bool(raw_item.get("link")), lane == "딜"),
        "레드플래그": red_flags,
        "출처URL": raw_item.get("link", ""),
        "서비스ID": "",
    }


# ═══════════════════════════════════════════════════════
#  레인별 후보 수집 (뉴스/딜)
# ═══════════════════════════════════════════════════════

def fetch_policy_news_secondary(category: str, limit: int = 10) -> list:
    """site:korea.kr 뉴스만(보조). trend_pipeline.POLICY_FEEDS 그대로 사용."""
    feeds = trend_pipeline.POLICY_FEEDS.get(category, {})
    results = []
    for name, url in feeds.items():
        items = safe_call(f"news:{category}:{name}", trend_pipeline._fetch_rss, url, limit)
        if items:
            for it in items:
                if trend_pipeline._is_safe(it["title"]) and trend_pipeline._is_safe(it.get("desc", "")):
                    results.append(it)
    return results


def fetch_deal_lane(limit: int = 20) -> list:
    return safe_call("deal_feed", trend_pipeline.fetch_deal_news, limit) or []


# ═══════════════════════════════════════════════════════
#  Phase3.5 — 딜 카드 정보 공백 해소 (박대홍 지시 2026-07-27)
#  실이득/마감/조건이 전부 확인필요인 빈 카드는 올리지 않는다.
#  원문 링크를 1회 fetch해서 마감일·할인율·조건 추출을 시도하고, 실패하면 탈락시킨다.
# ═══════════════════════════════════════════════════════

_DEAL_DATE_PATTERN = re.compile(r"(\d{1,2})\s*월\s*(\d{1,2})\s*일")
_DEAL_COND_KEYWORDS = ["선착순", "한정수량", "얼리버드", "사전예약", "사전예매"]


def fetch_deal_page_text(url: str) -> str:
    """딜 원문 링크를 1회 fetch해 순수 텍스트만 남긴다. 실패하면 빈 문자열."""
    if not url:
        return ""
    try:
        r = requests.get(url, headers=trend_pipeline.UA, timeout=10, allow_redirects=True)
        if r.status_code != 200:
            return ""
        text = re.sub(r"<script[\s\S]*?</script>", " ", r.text, flags=re.I)
        text = re.sub(r"<style[\s\S]*?</style>", " ", text, flags=re.I)
        text = re.sub(r"<[^>]+>", " ", text)
        import html as _html
        text = _html.unescape(text)
        return re.sub(r"\s+", " ", text).strip()[:6000]
    except Exception:
        return ""


def extract_deal_fields_from_page(url: str) -> dict:
    """딜 원문에서 할인율/마감일/구매조건을 best-effort로 추출한다. 못 찾으면 빈 dict."""
    text = fetch_deal_page_text(url)
    if not text:
        return {}
    out = {}
    pm = _PERCENT_PATTERN.search(text)
    if pm:
        out["실이득_얼마"] = f"최대 {pm.group(1)}% 할인"
    dm = _DEAL_DATE_PATTERN.search(text)
    if dm:
        out["마감"] = f"{dm.group(1)}월 {dm.group(2)}일까지(원문 추정)"
    for kw in _DEAL_COND_KEYWORDS:
        if kw in text:
            out["조건_소득자격"] = kw
            break
    return out


def _deal_has_real_info(fields: dict) -> bool:
    """실이득/마감/조건 중 하나라도 실제 정보가 있으면 True. 전부 확인필요면 빈 카드."""
    for key in ("실이득_얼마", "마감"):
        v = fields.get(key) or ""
        if v and "확인필요" not in v:
            return True
    v = fields.get("조건_소득자격") or ""
    if v and "확인필요" not in v and v != "해당없음":
        return True
    return False


# ═══════════════════════════════════════════════════════
#  메인 파이프라인
# ═══════════════════════════════════════════════════════

def run_pipeline(verbose: bool = True) -> dict:
    logger.info("=" * 60)
    logger.info("Phase3 scorecard 파이프라인 시작")
    logger.info("=" * 60)

    dedup_ctx = build_dedup_context()
    run_seen_titles: set = set()

    # ── 정책 뉴스 선수집 (보조 소스 + 신선도 훅 매칭용, 1회만 fetch해 news_fill에서 재사용) ──
    policy_news_raw = {cat: fetch_policy_news_secondary(cat, limit=10) for cat in ALLOCATION}
    news_blob = " ".join(
        f"{it.get('title', '')} {it.get('desc', '') or ''}"
        for items in policy_news_raw.values() for it in items
    )

    # ── gov24 캐시 로드/동기화 ──
    cache = safe_call("gov24_bulk", gov24_client.load_or_refresh_cache) or {"services": {}, "source_down": True}
    gov24_down = cache.get("source_down", True)
    logger.info(f"gov24 호출 카운트: {gov24_client.get_call_counts()}")

    snapshot_diff = {"is_first_run": True, "new_ids": set(), "previous_count": 0}
    if not gov24_down:
        snapshot_diff = gov24_client.diff_snapshot(list(cache.get("services", {}).keys()))

    # ── STEP1.5 소스 오염 제거 + STEP2 GATE 1차 통과 (신선도 훅 유무로 분리: 훅 없으면 상시 전용 → 보관) ──
    pool, evergreen, rejected_samples, archived_samples, scope_excluded_samples = build_gov24_pool(
        cache, snapshot_diff, news_blob, allow_low_income=False)
    pool_counts = {k: len(v) for k, v in pool.items()}
    evergreen_counts = {k: len(v) for k, v in evergreen.items()}
    logger.info(f"gov24 소스 오염 제거(보훈/지역특화): {len(scope_excluded_samples)}건 제외")
    logger.info(f"gov24 GATE 통과(훅 있음, 승격 대상): {pool_counts}")
    logger.info(f"gov24 상시 전용(훅 없음, 보관): {evergreen_counts}")

    # ── STEP4 재시도: 훅 있는 후보가 배분에 미달하면 소득 GATE 완화(저소득까지) 1회 ──
    for cat, need in ALLOCATION.items():
        if len(pool[cat]) < need:
            logger.warning(f"{cat} 훅 있는 후보 미달({len(pool[cat])}/{need}) → 소득 GATE 완화 재시도")
            pool2, _, _, _, _ = build_gov24_pool(cache, snapshot_diff, news_blob, allow_low_income=True)
            existing_ids = {e["item"]["서비스ID"] for e in pool[cat]}
            for e in pool2[cat]:
                if e["item"]["서비스ID"] not in existing_ids:
                    pool[cat].append(e)

    # ── 훅 있는 후보로도 배분에 못 미치면, 그때만 상시 프로그램으로 명시적으로 채운다 ──
    for cat, need in ALLOCATION.items():
        if len(pool[cat]) < need:
            shortfall = need - len(pool[cat])
            evergreen[cat].sort(key=lambda e: e["item"].get("조회수") or 0, reverse=True)
            backfill = evergreen[cat][:shortfall]
            for e in backfill:
                e["evergreen_fill"] = True
            pool[cat].extend(backfill)
            if backfill:
                logger.warning(f"{cat}: 훅 있는 후보 미달 → 상시 프로그램 {len(backfill)}건 명시적 보충(카드에 '상시' 표기)")

    # 중복 가드 적용 + 정렬용 상위 10건만 Gemini 배치 (훅 있는 후보 우선, evergreen 백필은 뒤로)
    all_gov24_cards = []
    for cat in ("trending", "money", "realestate"):
        survivors = []
        for e in pool[cat]:
            title = e["item"].get("서비스명", "")
            if is_duplicate(title, dedup_ctx, run_seen_titles):
                continue
            run_seen_titles.add(title)
            survivors.append(e)
        survivors.sort(key=lambda e: (e["evergreen_fill"], -(e["item"].get("조회수") or 0)))
        batch = survivors[:10]
        fields_by_idx = gemini_enrich_gov24_batch([e["item"] for e in batch])
        for i, e in enumerate(batch):
            fields = fields_by_idx.get(i, {})
            all_gov24_cards.append((cat, make_gov24_card(e, fields, cat, evergreen_fill=e["evergreen_fill"])))

    # ── 딜 레인 (Phase3.5: 실이득/마감/조건 전부 확인필요면 원문 1회 fetch, 실패시 탈락) ──
    deal_raw = fetch_deal_lane(limit=20)
    deal_survivors = []
    for it in deal_raw:
        if is_duplicate(it.get("title", ""), dedup_ctx, run_seen_titles):
            continue
        run_seen_titles.add(it.get("title", ""))
        deal_survivors.append(it)
    deal_batch = deal_survivors[:10]
    deal_fields_by_idx = gemini_enrich_external_batch(deal_batch, "trending(딜)")
    deal_cards = []
    deal_rejections = []  # Phase3.5: 딜 0건일 때 사유 추적용 (박대홍 지시 2026-07-27)
    for i, it in enumerate(deal_batch):
        fields = deal_fields_by_idx.get(i)
        if fields is None:
            # Gemini 응답 없음(장애) → 느슨 원칙으로 통과, 확인필요 처리
            fields = {"실이득_얼마": "확인필요", "조건_소득자격": "해당없음", "신청법": "확인필요", "세그먼트": "확인필요"}
        elif not fields.get("pass", True):
            reason = f"뻔함/시의성없음/출처불명(GATE): {fields.get('reject_reason', '')}".strip(": ")
            logger.info(f"딜 탈락({reason}): {it.get('title', '')[:40]}")
            deal_rejections.append({"제목": it.get("title", ""), "사유": reason})
            continue
        if not _deal_has_real_info(fields):
            extracted = safe_call("deal_page_fetch", extract_deal_fields_from_page, it.get("link", "")) or {}
            for k in ("실이득_얼마", "조건_소득자격", "마감"):
                if extracted.get(k):
                    fields[k] = extracted[k]
            if not _deal_has_real_info(fields):
                logger.info(f"딜 탈락(정보공백, 원문 확인 불가): {it.get('title', '')[:40]}")
                deal_rejections.append({"제목": it.get("title", ""), "사유": "정보공백(실이득/마감/조건 전부 확인불가, 원문 fetch도 실패)"})
                continue
        deal_cards.append(make_external_card(it, fields, "trending", "딜"))
    deal_cards.sort(key=lambda c: c["점수"], reverse=True)
    logger.info(f"딜 레인 집계: 원본수집 {len(deal_raw)}건 → 중복제거 {len(deal_survivors)}건 → "
                f"배치대상 {len(deal_batch)}건 → 탈락 {len(deal_rejections)}건 → 최종카드 {len(deal_cards)}건")

    # ── 정책 뉴스(보조) — gov24로 못 채운 슬롯만, 위에서 선수집한 뉴스를 재사용 ──
    def news_fill(category: str, missing: int) -> list:
        if missing <= 0:
            return []
        raw = policy_news_raw.get(category, [])
        survivors = []
        for it in raw:
            if is_duplicate(it.get("title", ""), dedup_ctx, run_seen_titles):
                continue
            run_seen_titles.add(it.get("title", ""))
            survivors.append(it)
        batch = survivors[:10]
        fields_by_idx = gemini_enrich_external_batch(batch, f"{category}(정책뉴스)")
        cards = []
        for i, it in enumerate(batch):
            fields = fields_by_idx.get(i)
            if fields is None:
                fields = {"실이득_얼마": "확인필요", "조건_소득자격": "확인필요", "신청법": "확인필요", "세그먼트": "확인필요"}
            elif not fields.get("pass", True):
                continue
            cards.append(make_external_card(it, fields, category, "정책"))
        cards.sort(key=lambda c: c["점수"], reverse=True)
        return cards

    # ── 최종 배분 ──
    final_cards = []
    log_lines = []

    by_cat = {"trending": [c for cat, c in all_gov24_cards if cat == "trending"],
              "money": [c for cat, c in all_gov24_cards if cat == "money"],
              "realestate": [c for cat, c in all_gov24_cards if cat == "realestate"]}
    for cat in by_cat:
        by_cat[cat].sort(key=lambda c: c["점수"], reverse=True)

    # trending: 딜 최소 2 보장 + 나머지 정책으로 3 채움
    deal_take = deal_cards[:max(TRENDING_DEAL_MIN, 0)]
    remaining_trending_slots = ALLOCATION["trending"] - len(deal_take)
    trending_policy = by_cat["trending"][:remaining_trending_slots]
    if len(trending_policy) < remaining_trending_slots:
        fill = news_fill("trending", remaining_trending_slots - len(trending_policy))
        trending_policy.extend(fill[:remaining_trending_slots - len(trending_policy)])
    trending_final = deal_take + trending_policy
    if len(trending_final) < ALLOCATION["trending"]:
        # 딜이 2건 미만이면 정책으로 남는 슬롯을 마저 채운다
        extra_needed = ALLOCATION["trending"] - len(trending_final)
        more_policy = [c for c in by_cat["trending"] if c not in trending_policy][:extra_needed]
        trending_final.extend(more_policy)
    log_lines.append(f"trending: 딜 {len(deal_take)}건 + 정책 {len(trending_final) - len(deal_take)}건 "
                      f"/ 목표 {ALLOCATION['trending']}건")
    if len(trending_final) < ALLOCATION["trending"]:
        logger.warning(f"미달: trending 부족 ({len(trending_final)}/{ALLOCATION['trending']}) — 빈 채로 둠")
    if len(deal_take) < TRENDING_DEAL_MIN:
        logger.warning(f"미달: trending 딜 최소보장 부족 ({len(deal_take)}/{TRENDING_DEAL_MIN})")
    final_cards.extend(trending_final)

    for cat in ("money", "realestate"):
        need = ALLOCATION[cat]
        chosen = by_cat[cat][:need]
        if len(chosen) < need:
            fill = news_fill(cat, need - len(chosen))
            chosen.extend(fill[:need - len(chosen)])
        if len(chosen) < need:
            logger.warning(f"미달: {cat} 부족 ({len(chosen)}/{need}) — 빈 채로 둠")
        log_lines.append(f"{cat}: {len(chosen)}/{need}건")
        final_cards.extend(chosen)

    for line in log_lines:
        logger.info(f"[배분] {line}")

    # ── serviceDetail 보강: 최종 선정된 gov24 카드(최대 8건)에 한해서만, 캡 내에서 호출 ──
    # (헬스체크 키는 서비스ID별이 아니라 "gov24_detail" 엔드포인트 단위로 집계 — ID는 매일 달라져
    #  개별 키로 쌓으면 연속실패 감지가 무의미해진다)
    for card in final_cards:
        sid = card.get("서비스ID")
        if not sid:
            continue
        detail = safe_call("gov24_detail", gov24_client.fetch_service_detail, sid)
        if detail and detail.get("온라인신청사이트URL"):
            card["출처URL"] = detail["온라인신청사이트URL"]

    # ── 점수 변별력 체크: 동점 3개 이상이면 로그 경고 (박대홍 지시 2026-07-27) ──
    score_counts = Counter(c["점수"] for c in final_cards)
    for score_val, cnt in score_counts.items():
        if cnt >= 3:
            logger.warning(f"SCORE_TIE_WARNING: 점수 {score_val}가 {cnt}건 동일 → 변별력 점검 필요")

    result = {
        "date": datetime.now(KST).strftime("%Y-%m-%d"),
        "cards": final_cards,
    }

    stats = {
        "pool_counts": pool_counts,
        "evergreen_counts": evergreen_counts,
        "rejected_samples": rejected_samples,
        "archived_samples": archived_samples,
        "scope_excluded_count": len(scope_excluded_samples),
        "scope_excluded_samples": scope_excluded_samples,
        "snapshot": snapshot_diff,
        "gov24_down": gov24_down,
        "deal_available": len(deal_cards),
        "deal_raw_count": len(deal_raw),
        "deal_batch_count": len(deal_batch),
        "deal_rejections": deal_rejections,
    }
    return {"result": result, "stats": stats, "all_gov24_entries": pool}


def save_candidates(result: dict) -> None:
    try:
        POSTS_DIR.mkdir(parents=True, exist_ok=True)
        CANDIDATES_PATH.write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
        logger.info(f"후보 큐 저장: {CANDIDATES_PATH} ({len(result['cards'])}장)")
    except Exception as e:
        logger.error(f"후보 큐 저장 실패: {e}")


# ═══════════════════════════════════════════════════════
#  검증/dry-run 콘솔 출력
# ═══════════════════════════════════════════════════════

def print_step0_contract_check():
    print("=" * 70)
    print("  STEP 0 — 계약 검증 (serviceList perPage=5 원문)")
    print("=" * 70)
    key = gov24_client.DATA_GO_KR_KEY
    if not key:
        print("  DATA_GO_KR_KEY 없음 → STEP0 스킵")
        return
    r = requests.get(f"{gov24_client.BASE_URL}/serviceList",
                      params={"serviceKey": key, "page": 1, "perPage": 5}, timeout=15)
    print(f"  status={r.status_code}")
    print(json.dumps(r.json(), ensure_ascii=False, indent=2))


def print_dry_run(pipeline_out: dict):
    result = pipeline_out["result"]
    stats = pipeline_out["stats"]

    print("\n" + "=" * 70)
    print(f"  후보 카드 {len(result['cards'])}장 (dry-run, 발행 아님)")
    print("=" * 70)
    for i, c in enumerate(result["cards"], 1):
        print(f"\n[{i}] {c['제목']}")
        print(f"    레인·카테고리: {c['레인']} / {c['카테고리']}  세그먼트: {c['세그먼트']}")
        print(f"    실이득: {c['실이득_얼마']}")
        print(f"    조건:   {c['조건_소득자격']}")
        print(f"    신청법: {c['신청법']}")
        print(f"    적격: {c['적격']}   탈락조건: {c.get('탈락조건', '')}")
        print(f"    마감: {c['마감']}   신선도근거: {c.get('신선도근거', '')}   점수: {c['점수']}")
        if c["레드플래그"]:
            print(f"    ⚠ 레드플래그: {', '.join(c['레드플래그'])}")

    print("\n" + "=" * 70)
    print("  GATE로 걸러진 항목 샘플 5건 (사유 포함)")
    print("=" * 70)
    for r in stats["rejected_samples"][:5]:
        print(f"  - {r['서비스명']} (ID={r['서비스ID']}): {r['사유']}")

    new_count = len(stats["snapshot"].get("new_ids", set()))
    urgent_count = sum(
        1 for cards in pipeline_out.get("all_gov24_entries", {}).values()
        for e in cards if e["gate"]["deadline"]["status"] == "urgent"
    )
    print("\n" + "=" * 70)
    print(f"  소스 오염 제거(보훈/지역특화 사전 제외): {stats['scope_excluded_count']}건")
    for r in stats["scope_excluded_samples"][:5]:
        print(f"    - {r['서비스명']} (ID={r['서비스ID']}): {r['사유']}")
    print(f"  신규 정책: {new_count}건 (첫 실행={stats['snapshot'].get('is_first_run')})")
    print(f"  마감임박(30일 이내): {urgent_count}건")
    print(f"  gov24 훅 있음(승격 대상): {stats['pool_counts']}  /  훅 없음(상시, 보관): {stats['evergreen_counts']}")
    print(f"  gov24 소스 상태: {'SOURCE_DOWN' if stats['gov24_down'] else 'OK'}")
    print(f"  딜 레인: 원본수집 {stats['deal_raw_count']}건 → 배치대상 {stats['deal_batch_count']}건 → "
          f"최종카드 {stats['deal_available']}건 (탈락 {len(stats['deal_rejections'])}건)")
    for r in stats["deal_rejections"]:
        print(f"    - 탈락: {r['제목'][:40]} → {r['사유']}")
    print("=" * 70)


if __name__ == "__main__":
    print_step0_contract_check()
    out = run_pipeline()
    print_dry_run(out)
    save_candidates(out["result"])
