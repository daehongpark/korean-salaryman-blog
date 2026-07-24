# -*- coding: utf-8 -*-
"""
gov24_client.py
────────────────────────────────────────────────────────────
공공데이터포털 "보조금24" API (api.odcloud.kr/api/gov24/v3) 클라이언트.

[전량 벌크 동기화 + 캐시 + 쿼터 가드]
- serviceList / supportConditions: 벌크 페이징(perPage=1000)으로 전량 1회 동기화.
  개별 서비스 조회는 절대 하지 않는다 (호출량 폭증 방지).
- serviceDetail: STEP1·2를 통과한 후보에 한해서만, 1일 상한 내에서 개별 호출.
- 쿼터: 1일 누적 호출 상한(전체) + serviceDetail 전용 상한을 posts/gov24_quota.json에
  永속화해 자정(KST) 기준으로 리셋한다. 상한 초과 시 "QUOTA_GUARD_STOP" 로그 후 중단.
  (승인된 개발계정 실제 한도는 1일 50만 건이므로, 아래 상한은 한도 보호용이 아니라
   무한루프·버그로 인한 과다호출을 조기에 감지하기 위한 안전장치다.)
- 벌크 응답은 posts/gov24_cache.json에 서비스ID 기준으로 조인해 캐시. 같은 날(KST) 재실행 시
  캐시를 우선 사용해 벌크 호출을 반복하지 않는다.
- 키 누락/오류(HTTP 401)는 이 소스만 건너뛰고("SOURCE_DOWN: gov24(키없음)") 나머지
  파이프라인은 계속 진행할 수 있도록 예외를 던지지 않고 None/빈 결과로 신호를 준다.
────────────────────────────────────────────────────────────
"""

from __future__ import annotations

import json
import logging
import os
import re
import sys
from datetime import datetime, timedelta, timezone, date
from pathlib import Path
from typing import Optional

import requests

# Windows 콘솔(cp949)에서 한글 출력 시 UnicodeEncodeError 방지
if sys.stdout.encoding and sys.stdout.encoding.lower() != "utf-8":
    try:
        sys.stdout.reconfigure(encoding="utf-8")
        sys.stderr.reconfigure(encoding="utf-8")
    except Exception:
        pass

try:
    from dotenv import load_dotenv
    load_dotenv()
except ImportError:
    pass

logger = logging.getLogger("gov24_client")
if not logger.handlers:
    _h = logging.StreamHandler()
    _h.setFormatter(logging.Formatter(
        "[%(asctime)s] %(levelname)s gov24_client: %(message)s",
        "%Y-%m-%d %H:%M:%S"
    ))
    logger.addHandler(_h)
    logger.setLevel(logging.INFO)

KST = timezone(timedelta(hours=9))


def today_kst_str() -> str:
    return datetime.now(KST).strftime("%Y-%m-%d")


def today_kst_date() -> date:
    return datetime.now(KST).date()


# ── 경로 ─────────────────────────────────────────────
SCRIPT_DIR   = Path(__file__).parent
POSTS_DIR    = SCRIPT_DIR / "posts"
CACHE_PATH   = POSTS_DIR / "gov24_cache.json"
SNAPSHOT_PATH = POSTS_DIR / "gov24_snapshot.json"
QUOTA_PATH   = POSTS_DIR / "gov24_quota.json"

BASE_URL = "https://api.odcloud.kr/api/gov24/v3"

# 1일 누적 호출 상한 (한도 보호용이 아니라 무한루프/버그 조기감지용. 박대홍 지시 2026-07-24)
QUOTA_DAILY_CAP  = 5000
DETAIL_DAILY_CAP = 200


# ═══════════════════════════════════════════════════════
#  쿼터 가드
# ═══════════════════════════════════════════════════════

class QuotaExceeded(Exception):
    pass


def _load_quota() -> dict:
    today = today_kst_str()
    if QUOTA_PATH.exists():
        try:
            q = json.loads(QUOTA_PATH.read_text(encoding="utf-8"))
            if q.get("date") == today:
                return q
        except Exception:
            pass
    return {"date": today, "calls": 0, "detail_calls": 0}


def _save_quota(q: dict) -> None:
    try:
        POSTS_DIR.mkdir(parents=True, exist_ok=True)
        QUOTA_PATH.write_text(json.dumps(q, ensure_ascii=False, indent=2), encoding="utf-8")
    except Exception as e:
        logger.warning(f"쿼터 파일 저장 실패: {e}")


_quota_state = None  # 프로세스 내 캐시


def _get_quota_state() -> dict:
    global _quota_state
    if _quota_state is None:
        _quota_state = _load_quota()
    return _quota_state


def _register_call(is_detail: bool = False) -> None:
    """호출 1건을 쿼터에 반영. 상한 초과 시 QuotaExceeded 발생."""
    q = _get_quota_state()
    if q["calls"] + 1 > QUOTA_DAILY_CAP:
        logger.error(f"QUOTA_GUARD_STOP: 1일 누적 호출 상한({QUOTA_DAILY_CAP}) 초과 → 중단")
        _save_quota(q)
        raise QuotaExceeded("daily total call cap exceeded")
    if is_detail and q["detail_calls"] + 1 > DETAIL_DAILY_CAP:
        logger.error(f"QUOTA_GUARD_STOP: serviceDetail 1일 상한({DETAIL_DAILY_CAP}) 초과 → 중단")
        _save_quota(q)
        raise QuotaExceeded("daily detail call cap exceeded")
    q["calls"] += 1
    if is_detail:
        q["detail_calls"] += 1
    _save_quota(q)


def get_call_counts() -> dict:
    q = _get_quota_state()
    return {"calls": q["calls"], "detail_calls": q["detail_calls"]}


# ═══════════════════════════════════════════════════════
#  키 상태
# ═══════════════════════════════════════════════════════

DATA_GO_KR_KEY = os.environ.get("DATA_GO_KR_KEY", "")


class Gov24Unavailable(Exception):
    """키 누락/401 등으로 gov24 소스 전체를 건너뛰어야 할 때."""
    pass


# ═══════════════════════════════════════════════════════
#  벌크 페이징 (serviceList / supportConditions)
# ═══════════════════════════════════════════════════════

def _bulk_fetch(endpoint: str) -> list:
    """perPage=1000 페이징으로 전량 수집. 호출 수를 로그로 출력.
    HTTP 401이면 Gov24Unavailable을 던져 상위에서 SOURCE_DOWN 처리하게 한다."""
    if not DATA_GO_KR_KEY:
        logger.warning("SOURCE_DOWN: gov24(키없음) — DATA_GO_KR_KEY 환경변수 없음")
        raise Gov24Unavailable("no key")

    url = f"{BASE_URL}/{endpoint}"
    all_items: list = []
    page = 1
    per_page = 1000
    call_count = 0
    total = None

    while True:
        _register_call(is_detail=False)
        call_count += 1
        try:
            r = requests.get(
                url,
                params={"serviceKey": DATA_GO_KR_KEY, "page": page, "perPage": per_page},
                timeout=30,
            )
        except requests.exceptions.RequestException as e:
            logger.warning(f"gov24 {endpoint} 요청 실패(page={page}): {e}")
            break

        if r.status_code == 401:
            logger.warning(f"SOURCE_DOWN: gov24(키없음) — {endpoint} HTTP 401 (status={r.status_code})")
            raise Gov24Unavailable(f"401 on {endpoint}")
        if r.status_code != 200:
            logger.warning(f"gov24 {endpoint} 오류 status={r.status_code} page={page}: {r.text[:200]}")
            break

        data = r.json()
        items = data.get("data", [])
        total = data.get("totalCount", total)
        all_items.extend(items)

        if not items or (total is not None and page * per_page >= total):
            break
        page += 1

    logger.info(f"gov24 {endpoint} 벌크 동기화: {len(all_items)}건 / 호출 {call_count}회 (totalCount={total})")
    return all_items


def fetch_all_service_list() -> list:
    return _bulk_fetch("serviceList")


def fetch_all_support_conditions() -> list:
    return _bulk_fetch("supportConditions")


# ═══════════════════════════════════════════════════════
#  serviceDetail (후보로 좁혀진 건만, 1일 상한 캡)
# ═══════════════════════════════════════════════════════

def fetch_service_detail(service_id: str) -> Optional[dict]:
    """후보 개별 상세조회. 1일 DETAIL_DAILY_CAP 캡 적용."""
    if not DATA_GO_KR_KEY:
        return None
    url = f"{BASE_URL}/serviceDetail"
    try:
        _register_call(is_detail=True)
    except QuotaExceeded:
        return None
    try:
        r = requests.get(
            url,
            params={"serviceKey": DATA_GO_KR_KEY, f"cond[서비스ID::EQ]": service_id},
            timeout=15,
        )
    except requests.exceptions.RequestException as e:
        logger.warning(f"serviceDetail 요청 실패({service_id}): {e}")
        return None
    if r.status_code != 200:
        logger.warning(f"serviceDetail 오류 status={r.status_code} id={service_id}")
        return None
    data = r.json()
    items = data.get("data", [])
    return items[0] if items else None


# ═══════════════════════════════════════════════════════
#  캐시 (당일 KST 기준 재사용)
# ═══════════════════════════════════════════════════════

def load_or_refresh_cache(force_refresh: bool = False) -> dict:
    """
    posts/gov24_cache.json 캐시 우선 사용.
    - 캐시 파일의 date가 오늘(KST)이면 그대로 반환(벌크 호출 없음).
    - 아니면(첫 실행/날짜 변경) serviceList+supportConditions 벌크 재동기화 후 조인·캐시 저장.
    - 키 누락/401이면 SOURCE_DOWN 처리 후 빈 캐시({}) 반환 (예외로 크래시시키지 않음).

    반환: {"date": "YYYY-MM-DD", "services": {서비스ID: {...serviceList 필드, "conditions": {...}}}, "source_down": bool}
    """
    today = today_kst_str()

    if not force_refresh and CACHE_PATH.exists():
        try:
            cached = json.loads(CACHE_PATH.read_text(encoding="utf-8"))
            if cached.get("date") == today and cached.get("services"):
                logger.info(f"gov24 캐시 재사용 (date={today}, {len(cached['services'])}건) — 벌크 호출 생략")
                cached["source_down"] = False
                return cached
        except Exception as e:
            logger.warning(f"gov24 캐시 로드 실패, 재동기화: {e}")

    try:
        service_list = fetch_all_service_list()
        conditions = fetch_all_support_conditions()
    except Gov24Unavailable:
        return {"date": today, "services": {}, "source_down": True}
    except QuotaExceeded:
        logger.error("QUOTA_GUARD_STOP: 벌크 동기화 도중 쿼터 상한 도달 → 이번 실행은 부분 데이터로 진행")
        return {"date": today, "services": {}, "source_down": True}

    cond_by_id = {c.get("서비스ID"): c for c in conditions if c.get("서비스ID")}

    services = {}
    for item in service_list:
        sid = item.get("서비스ID")
        if not sid:
            continue
        merged = dict(item)
        merged["conditions"] = cond_by_id.get(sid, {})
        services[sid] = merged

    cache = {"date": today, "services": services}
    try:
        POSTS_DIR.mkdir(parents=True, exist_ok=True)
        CACHE_PATH.write_text(json.dumps(cache, ensure_ascii=False, indent=2), encoding="utf-8")
        logger.info(f"gov24 캐시 저장: {len(services)}건 → {CACHE_PATH}")
    except Exception as e:
        logger.warning(f"gov24 캐시 저장 실패: {e}")

    cache["source_down"] = False
    return cache


# ═══════════════════════════════════════════════════════
#  STEP1 — 스냅샷 비교 (신규 등장 ID 판별)
# ═══════════════════════════════════════════════════════

def diff_snapshot(current_ids: list) -> dict:
    """
    이전 스냅샷과 비교해 신규 등장 ID를 판별하고, 이번 스냅샷으로 덮어쓴다.
    반환: {"is_first_run": bool, "new_ids": set, "previous_count": int}
    """
    current_set = set(current_ids)
    is_first_run = not SNAPSHOT_PATH.exists()

    previous_ids = set()
    if not is_first_run:
        try:
            prev = json.loads(SNAPSHOT_PATH.read_text(encoding="utf-8"))
            previous_ids = set(prev.get("service_ids", []))
        except Exception as e:
            logger.warning(f"이전 스냅샷 로드 실패(신규 없음으로 처리): {e}")
            is_first_run = True

    new_ids = set() if is_first_run else (current_set - previous_ids)

    try:
        POSTS_DIR.mkdir(parents=True, exist_ok=True)
        SNAPSHOT_PATH.write_text(
            json.dumps({"date": today_kst_str(), "service_ids": sorted(current_set)},
                       ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
    except Exception as e:
        logger.warning(f"스냅샷 저장 실패: {e}")

    logger.info(
        f"스냅샷 비교: {'첫 실행(비교 없음)' if is_first_run else f'신규 {len(new_ids)}건'} "
        f"(이번 {len(current_set)}건 / 이전 {len(previous_ids)}건)"
    )
    return {"is_first_run": is_first_run, "new_ids": new_ids, "previous_count": len(previous_ids)}


# ═══════════════════════════════════════════════════════
#  STEP2 — GATE (코드 기반)
# ═══════════════════════════════════════════════════════

# 소관기관유형별 지역 대표성 판정 (박대홍 지시: 광역시·도 단위/전국 PASS, 소도시 전용 REJECT)
_REGION_PASS_ORG_TYPES = {"중앙행정기관", "공공기관", "광역시도", "교육청"}
_REGION_REJECT_ORG_TYPES = {"시군구", "지방공기업", "지방출자_출연기관"}


def region_gate(item: dict) -> dict:
    org_type = (item.get("소관기관유형") or "").strip()
    if org_type in _REGION_PASS_ORG_TYPES:
        return {"pass": True, "reason": f"지역 PASS ({org_type})"}
    if org_type in _REGION_REJECT_ORG_TYPES:
        org_name = item.get("소관기관명") or ""
        return {"pass": False, "reason": f"지역 REJECT: 소도시/자치단체 전용 ({org_type}: {org_name})"}
    # 알 수 없는 유형은 느슨 원칙에 따라 PASS
    return {"pass": True, "reason": f"지역 확인필요로 PASS (미분류 소관기관유형: {org_type or '없음'})"}


# 소득 GATE: 중위소득 구간 코드 (JA02xx)
def income_gate(conditions: dict) -> dict:
    def is_y(code):
        return conditions.get(code) == "Y"

    ja0201, ja0202 = is_y("JA0201"), is_y("JA0202")
    ja0203 = is_y("JA0203")
    ja0204, ja0205 = is_y("JA0204"), is_y("JA0205")
    any_income_field = any(conditions.get(c) is not None for c in
                           ("JA0201", "JA0202", "JA0203", "JA0204", "JA0205"))

    if ja0204 or ja0205:
        return {"pass": True, "tier": "strong", "flag": None, "reason": "소득 PASS (101%초과 구간 포함)"}
    if ja0203 and not (ja0204 or ja0205):
        return {"pass": True, "tier": "boundary", "flag": "⚠️경계",
                "reason": "소득 PASS·경계 (JA0203 76~100%만 해당)"}
    if not any_income_field:
        return {"pass": True, "tier": "strong", "flag": "⚠️확인필요",
                "reason": "소득조건 정보 없음 → PASS(확인필요)"}
    if ja0201 or ja0202:
        return {"pass": False, "tier": "low_only", "flag": None,
                "reason": "소득 REJECT (저소득 전용: JA0201/JA0202만 해당)"}
    # 이론상 도달하지 않지만 느슨 원칙에 따라 PASS
    return {"pass": True, "tier": "strong", "flag": "⚠️확인필요", "reason": "소득 조건 미분류 → PASS(확인필요)"}


# 신청기한 파싱: 실제 API 필드가 자유서술형이라(예: "매년 5월경", "공고 후 접수기한내")
# 완전한 날짜 파싱은 불가능 → 아래 휴리스틱으로 best-effort 처리.
_RECURRING_MARKERS = ["매년", "연초", "분기별", "매월", "상시", "수시", "연중", "매 회차"]
_DATE_PATTERN = re.compile(r"(20\d{2})[.\-\s]\s*(\d{1,2})[.\-\s]\s*(\d{1,2})")


def parse_deadline(text: Optional[str], today: Optional[date] = None) -> dict:
    """
    반환: {"status": "urgent"|"normal"|"none"|"expired", "next_date": iso|None, "days_left": int|None}
    - urgent: 30일 이내 마감
    - normal: 30일 초과 마감일이 명확히 존재
    - none:   상시/수시/문구뿐이라 마감일 특정 불가 (시의성 낮음)
    - expired: 명시적 날짜가 모두 과거이고 반복 문구도 없는 경우(신청기한 지난 것으로 판단)
    """
    if today is None:
        today = today_kst_date()
    t = (text or "").strip()
    if not t:
        return {"status": "none", "next_date": None, "days_left": None}

    dates = []
    for m in _DATE_PATTERN.finditer(t):
        y, mo, d = int(m.group(1)), int(m.group(2)), int(m.group(3))
        try:
            dates.append(date(y, mo, d))
        except ValueError:
            continue

    has_recurring = any(k in t for k in _RECURRING_MARKERS)

    if dates:
        future = [d for d in dates if d >= today]
        if future:
            nd = min(future)
            days_left = (nd - today).days
            status = "urgent" if days_left <= 30 else "normal"
            return {"status": status, "next_date": nd.isoformat(), "days_left": days_left}
        if has_recurring:
            # 반복 일정인데 올해분 날짜는 이미 지남 → 다음 회차 정확한 날짜 특정 불가
            return {"status": "none", "next_date": None, "days_left": None}
        latest = max(dates)
        return {"status": "expired", "next_date": latest.isoformat(),
                "days_left": (latest - today).days}

    # 명시적 날짜 없음 (반복/상시/문구형) → 마감 특정 불가
    return {"status": "none", "next_date": None, "days_left": None}


def deadline_gate(item: dict, today: Optional[date] = None) -> dict:
    parsed = parse_deadline(item.get("신청기한"), today=today)
    if parsed["status"] == "expired":
        return {"pass": False, "reason": f"종료: 신청기한 지남 ({parsed['next_date']})", **parsed}
    return {"pass": True, "reason": "마감 미도래", **parsed}


def apply_gates(item: dict, today: Optional[date] = None) -> dict:
    """서비스 1건에 지역/소득/마감 GATE를 모두 적용해 종합 판정을 반환."""
    region = region_gate(item)
    income = income_gate(item.get("conditions") or {})
    deadline = deadline_gate(item, today=today)

    passed = region["pass"] and income["pass"] and deadline["pass"]
    reasons = []
    if not region["pass"]:
        reasons.append(region["reason"])
    if not income["pass"]:
        reasons.append(income["reason"])
    if not deadline["pass"]:
        reasons.append(deadline["reason"])
    if not reasons:
        reasons = [r["reason"] for r in (region, income, deadline)]

    return {
        "pass": passed,
        "region": region,
        "income": income,
        "deadline": deadline,
        "reasons": reasons,
    }


if __name__ == "__main__":
    print("=" * 60)
    print("  gov24_client 단독 테스트 (STEP 0 계약 검증)")
    print("=" * 60)
    print(f"\n[키 상태] DATA_GO_KR_KEY: {'OK (len=' + str(len(DATA_GO_KR_KEY)) + ')' if DATA_GO_KR_KEY else 'MISSING'}")

    print("\n[serviceList] perPage=5 원문 확인")
    if not DATA_GO_KR_KEY:
        print("  키 없음 → 스킵")
    else:
        r = requests.get(f"{BASE_URL}/serviceList",
                          params={"serviceKey": DATA_GO_KR_KEY, "page": 1, "perPage": 5}, timeout=15)
        print("  status:", r.status_code)
        print(json.dumps(r.json(), ensure_ascii=False, indent=2)[:2000])

    print("\n[캐시 로드/동기화]")
    cache = load_or_refresh_cache()
    print(f"  source_down={cache.get('source_down')} services={len(cache.get('services', {}))}")
    print(f"  호출 카운트: {get_call_counts()}")
