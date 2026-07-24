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
import os
import re
import sys
import time
from datetime import datetime, timedelta, timezone
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
#  점수 (정렬용, 0~5)
# ═══════════════════════════════════════════════════════

def score_gov24_candidate(item: dict, gate: dict, is_new: bool, fields: dict) -> float:
    income_score = {"strong": 5, "boundary": 3.5, "low_only": 2}.get(gate["income"]["tier"], 3)

    deadline = gate["deadline"]
    if is_new:
        timeliness = 5
    elif deadline["status"] == "urgent":
        timeliness = 5
    elif deadline["status"] == "normal":
        timeliness = 3
    else:
        timeliness = 2

    benefit_text = fields.get("실이득_얼마", "") or ""
    benefit_score = 2.0 if (not benefit_text or "확인필요" in benefit_text) else 4.5

    apply_text = item.get("신청방법") or ""
    apply_score = 5.0 if any(k in apply_text for k in ("온라인", "모바일", "홈택스", "인터넷")) else 3.5

    segment = fields.get("세그먼트", "") or ""
    segment_score = 2.0 if (not segment or "확인" in segment or "일반" == segment) else 5.0

    return round((income_score + benefit_score + apply_score + timeliness + segment_score) / 5, 1)


def score_external_candidate(fields: dict, has_link: bool, is_deal: bool) -> float:
    source_score = 5.0 if has_link else 3.0
    benefit_text = fields.get("실이득_얼마", "") or ""
    benefit_score = 2.0 if (not benefit_text or "확인필요" in benefit_text) else 4.5
    apply_text = fields.get("신청법", "") or ""
    apply_score = 4.5 if apply_text and "확인필요" not in apply_text else 2.5
    # 뉴스/딜은 이미 when:3~7d 검색이라 기본 시의성 준수, 딜은 "한정"류 문구면 가점
    timeliness = 4.0
    if is_deal and any(k in (fields.get("조건_소득자격", "") + apply_text) for k in ("한정", "마감", "선착순")):
        timeliness = 5.0
    segment = fields.get("세그먼트", "") or ""
    segment_score = 2.0 if (not segment or "확인" in segment or segment == "일반") else 5.0
    return round((source_score + benefit_score + apply_score + timeliness + segment_score) / 5, 1)


# ═══════════════════════════════════════════════════════
#  gov24 후보 풀 구축 (GATE 적용 + 리젝 샘플 수집)
# ═══════════════════════════════════════════════════════

def build_gov24_pool(cache: dict, snapshot_diff: dict, allow_low_income: bool = False):
    services = cache.get("services", {})
    today = gov24_client.today_kst_date()
    new_ids = snapshot_diff.get("new_ids", set())

    passed = {"trending": [], "money": [], "realestate": []}
    rejected_samples = []

    for sid, item in services.items():
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
        passed[cat].append({
            "item": item, "gate": gate, "is_new": sid in new_ids,
        })

    return passed, rejected_samples


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


def make_gov24_card(entry: dict, fields: dict, category: str) -> dict:
    item, gate = entry["item"], entry["gate"]
    income = gate["income"]
    eligible = "✅" if not income.get("flag") else f"⚠️{income['flag'].replace('⚠️', '')}"
    red_flags = []
    if income["tier"] == "low_only":
        red_flags.append("저소득 전용 항목(GATE 완화 적용)")
    if not fields.get("실이득_얼마") or "확인필요" in (fields.get("실이득_얼마") or ""):
        red_flags.append("실이득 금액 확인필요")

    source_url = item.get("상세조회URL") or ""

    return {
        "제목": item.get("서비스명", ""),
        "카테고리": category,
        "레인": "정책",
        "세그먼트": fields.get("세그먼트", "확인필요") or "확인필요",
        "실이득_얼마": fields.get("실이득_얼마", "확인필요") or "확인필요",
        "조건_소득자격": fields.get("조건_소득자격", "확인필요") or "확인필요",
        "신청법": fields.get("신청법", item.get("신청방법", "")) or "확인필요",
        "적격": eligible,
        "마감": _format_deadline_label(gate["deadline"]),
        "점수": score_gov24_candidate(item, gate, entry["is_new"], fields),
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

    return {
        "제목": raw_item.get("title", ""),
        "카테고리": category,
        "레인": lane,
        "세그먼트": fields.get("세그먼트") or "확인필요",
        "실이득_얼마": fields.get("실이득_얼마") or "확인필요",
        "조건_소득자격": condition,
        "신청법": fields.get("신청법") or "확인필요",
        "적격": "⚠️확인필요" if lane == "정책" else "✅",
        "마감": "확인필요",
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
#  메인 파이프라인
# ═══════════════════════════════════════════════════════

def run_pipeline(verbose: bool = True) -> dict:
    logger.info("=" * 60)
    logger.info("Phase3 scorecard 파이프라인 시작")
    logger.info("=" * 60)

    dedup_ctx = build_dedup_context()
    run_seen_titles: set = set()

    # ── gov24 캐시 로드/동기화 ──
    cache = safe_call("gov24_bulk", gov24_client.load_or_refresh_cache) or {"services": {}, "source_down": True}
    gov24_down = cache.get("source_down", True)
    logger.info(f"gov24 호출 카운트: {gov24_client.get_call_counts()}")

    snapshot_diff = {"is_first_run": True, "new_ids": set(), "previous_count": 0}
    if not gov24_down:
        snapshot_diff = gov24_client.diff_snapshot(list(cache.get("services", {}).keys()))

    # ── STEP2 GATE 1차 통과 ──
    pool, rejected_samples = build_gov24_pool(cache, snapshot_diff, allow_low_income=False)
    pool_counts = {k: len(v) for k, v in pool.items()}
    logger.info(f"gov24 GATE 통과(1차): {pool_counts}")

    # ── STEP4 재시도: 배분에 미달하면 소득 GATE 완화(저소득까지) 1회 ──
    for cat, need in ALLOCATION.items():
        if len(pool[cat]) < need:
            logger.warning(f"{cat} 후보 미달({len(pool[cat])}/{need}) → 소득 GATE 완화 재시도")
            pool2, _ = build_gov24_pool(cache, snapshot_diff, allow_low_income=True)
            existing_ids = {e["item"]["서비스ID"] for e in pool[cat]}
            for e in pool2[cat]:
                if e["item"]["서비스ID"] not in existing_ids:
                    pool[cat].append(e)

    # 중복 가드 적용 + 정렬용 상위 10건만 Gemini 배치
    all_gov24_cards = []
    for cat in ("trending", "money", "realestate"):
        survivors = []
        for e in pool[cat]:
            title = e["item"].get("서비스명", "")
            if is_duplicate(title, dedup_ctx, run_seen_titles):
                continue
            run_seen_titles.add(title)
            survivors.append(e)
        # 조회수 높은 순으로 상위 10건만 Gemini 보강(비용 절감)
        survivors.sort(key=lambda e: e["item"].get("조회수", 0), reverse=True)
        batch = survivors[:10]
        fields_by_idx = gemini_enrich_gov24_batch([e["item"] for e in batch])
        for i, e in enumerate(batch):
            fields = fields_by_idx.get(i, {})
            all_gov24_cards.append((cat, make_gov24_card(e, fields, cat)))

    # ── 딜 레인 ──
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
    for i, it in enumerate(deal_batch):
        fields = deal_fields_by_idx.get(i)
        if fields is None:
            # Gemini 응답 없음(장애) → 느슨 원칙으로 통과, 확인필요 처리
            fields = {"실이득_얼마": "확인필요", "조건_소득자격": "해당없음", "신청법": "확인필요", "세그먼트": "확인필요"}
        elif not fields.get("pass", True):
            continue
        deal_cards.append(make_external_card(it, fields, "trending", "딜"))
    deal_cards.sort(key=lambda c: c["점수"], reverse=True)

    # ── 정책 뉴스(보조) — gov24로 못 채운 슬롯만 ──
    def news_fill(category: str, missing: int) -> list:
        if missing <= 0:
            return []
        raw = fetch_policy_news_secondary(category, limit=10)
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

    result = {
        "date": datetime.now(KST).strftime("%Y-%m-%d"),
        "cards": final_cards,
    }

    stats = {
        "pool_counts": pool_counts,
        "rejected_samples": rejected_samples,
        "snapshot": snapshot_diff,
        "gov24_down": gov24_down,
        "deal_available": len(deal_cards),
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
        print(f"    적격: {c['적격']}   마감: {c['마감']}   점수: {c['점수']}")
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
    print(f"  신규 정책: {new_count}건 (첫 실행={stats['snapshot'].get('is_first_run')})")
    print(f"  마감임박(30일 이내): {urgent_count}건")
    print(f"  gov24 소스 상태: {'SOURCE_DOWN' if stats['gov24_down'] else 'OK'}")
    print(f"  딜 레인 확보: {stats['deal_available']}건")
    print("=" * 70)


if __name__ == "__main__":
    print_step0_contract_check()
    out = run_pipeline()
    print_dry_run(out)
    save_candidates(out["result"])
