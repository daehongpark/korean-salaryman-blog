# ────────────────────────────────────────────────────────────
#  threads_publisher.py
#  Threads(메타) 자동발행 모듈 — 토큰 교환/갱신 + 텍스트 글 발행
#
#  Threads Graph API: https://graph.threads.net
#  발행은 2단계 컨테이너 모델:
#    1) {user_id}/threads          → creation_id 생성
#    2) {user_id}/threads_publish  → creation_id 발행
#
#  ★ 보안: 토큰/시크릿은 절대 하드코딩 금지. .env(gitignore) 또는 환경변수만 사용.
#  ────────────────────────────────────────────────────────────
import os
import sys
import io
import time

# Windows 한글 콘솔(cp949)에서 유니코드 출력이 죽지 않도록 stdout/stderr 강제 UTF-8
try:
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")
    sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding="utf-8", errors="replace")
except Exception:
    pass

import requests

try:
    from dotenv import load_dotenv
    load_dotenv()  # 로컬 .env 자동 로드 (CI에선 파일 없어도 무해)
except Exception:
    pass

GRAPH = "https://graph.threads.net"
API_VERSION = "v1.0"
TIMEOUT = 30
PUBLISH_WAIT_SEC = 5  # 컨테이너 생성 후 publish 전 대기 (Threads 권장)


def _mask(token: str, keep: int = 10) -> str:
    """토큰 마스킹 (앞 keep자만 노출)."""
    if not token:
        return "(없음)"
    return token[:keep] + "..." + f"(len={len(token)})"


# ── 1. 단기 → 장기 토큰 교환 (60일) ──────────────────────────
def exchange_token(short_token: str, app_secret: str) -> str | None:
    """단기 토큰을 장기(60일) 토큰으로 교환. 실패 시 None."""
    url = f"{GRAPH}/access_token"
    params = {
        "grant_type": "th_exchange_token",
        "client_secret": app_secret,
        "access_token": short_token,
    }
    try:
        r = requests.get(url, params=params, timeout=TIMEOUT)
        if r.status_code != 200:
            print(f"   [exchange] 실패 HTTP {r.status_code}: {r.text}")
            return None
        data = r.json()
        long_token = data.get("access_token")
        expires_in = data.get("expires_in")
        if not long_token:
            print(f"   [exchange] 응답에 access_token 없음: {data}")
            return None
        days = (expires_in or 0) // 86400
        print(f"   [exchange] ✓ 장기토큰 획득 (만료 ~{days}일, {expires_in}s)")
        return long_token
    except Exception as e:
        print(f"   [exchange] 예외: {e}")
        return None


# ── 2. 장기 토큰 갱신 (60일 만료 전 호출) ────────────────────
def refresh_token(long_token: str) -> str | None:
    """장기 토큰을 갱신(다시 60일). 실패 시 None."""
    url = f"{GRAPH}/refresh_access_token"
    params = {
        "grant_type": "th_refresh_token",
        "access_token": long_token,
    }
    try:
        r = requests.get(url, params=params, timeout=TIMEOUT)
        if r.status_code != 200:
            print(f"   [refresh] 실패 HTTP {r.status_code}: {r.text}")
            return None
        data = r.json()
        new_token = data.get("access_token")
        expires_in = data.get("expires_in")
        if not new_token:
            print(f"   [refresh] 응답에 access_token 없음: {data}")
            return None
        days = (expires_in or 0) // 86400
        print(f"   [refresh] ✓ 갱신 완료 (만료 ~{days}일)")
        return new_token
    except Exception as e:
        print(f"   [refresh] 예외: {e}")
        return None


# ── 3. 텍스트 글 발행 (2단계 컨테이너 모델) ──────────────────
def publish_text(user_id: str, token: str, text: str) -> dict | None:
    """텍스트 글을 발행. 성공 시 {'id': thread_id, 'permalink': url} 반환, 실패 시 None."""
    # 1단계: 컨테이너 생성
    create_url = f"{GRAPH}/{API_VERSION}/{user_id}/threads"
    create_params = {
        "media_type": "TEXT",
        "text": text,
        "access_token": token,
    }
    try:
        r = requests.post(create_url, data=create_params, timeout=TIMEOUT)
        if r.status_code != 200:
            print(f"   [publish:1] 컨테이너 생성 실패 HTTP {r.status_code}: {r.text}")
            return None
        creation_id = r.json().get("id")
        if not creation_id:
            print(f"   [publish:1] creation_id 없음: {r.json()}")
            return None
        print(f"   [publish:1] ✓ 컨테이너 생성 creation_id={creation_id}")
    except Exception as e:
        print(f"   [publish:1] 예외: {e}")
        return None

    # Threads 권장: 컨테이너 생성 후 publish 전 대기
    print(f"   [publish] {PUBLISH_WAIT_SEC}초 대기...")
    time.sleep(PUBLISH_WAIT_SEC)

    # 2단계: 발행
    publish_url = f"{GRAPH}/{API_VERSION}/{user_id}/threads_publish"
    publish_params = {
        "creation_id": creation_id,
        "access_token": token,
    }
    try:
        r = requests.post(publish_url, data=publish_params, timeout=TIMEOUT)
        if r.status_code != 200:
            print(f"   [publish:2] 발행 실패 HTTP {r.status_code}: {r.text}")
            return None
        thread_id = r.json().get("id")
        if not thread_id:
            print(f"   [publish:2] thread id 없음: {r.json()}")
            return None
        print(f"   [publish:2] ✓ 발행 완료 thread_id={thread_id}")
    except Exception as e:
        print(f"   [publish:2] 예외: {e}")
        return None

    # 퍼머링크 조회 (선택, 실패해도 발행은 성공)
    permalink = None
    try:
        meta_url = f"{GRAPH}/{API_VERSION}/{thread_id}"
        r = requests.get(meta_url, params={"fields": "permalink", "access_token": token}, timeout=TIMEOUT)
        if r.status_code == 200:
            permalink = r.json().get("permalink")
    except Exception:
        pass

    return {"id": thread_id, "permalink": permalink}


# ════════════════════════════════════════════════════════════
#  2단계: 블로그 글 → 쓰레드 포스트 변환 + 일일 발행 파이프라인
# ════════════════════════════════════════════════════════════
import json
import datetime
from pathlib import Path

ROOT          = Path(__file__).resolve().parent
POSTS_DIR     = ROOT / "posts"
MANIFEST_PATH = POSTS_DIR / "manifest.json"
STATE_PATH    = POSTS_DIR / "threads_state.json"   # 커밋됨(시크릿 없음): 중복실행/만료 가드
NEW_TOKEN_FILE = ROOT / "threads_new_token.txt"    # gitignore: 갱신토큰 임시 전달용

SITE = "https://koreansalaryman.com"

THREADS_PER_DAY   = 5     # 하루 발행 글 수
PUBLISH_GAP_SEC   = 30    # 글 간 발행 간격 (rate limit/스팸 방지)
TOKEN_LIFETIME_DAYS = 60  # 장기토큰 수명
REFRESH_BEFORE_DAYS = 7   # 만료 N일 이내면 갱신
THREAD_MAX_LEN    = 480   # 안전 길이 (Threads 한도 500)


# ── 시간 유틸 (KST) ──────────────────────────────────────────
def _now_kst() -> datetime.datetime:
    return datetime.datetime.now(datetime.timezone.utc) + datetime.timedelta(hours=9)


def _today_kst() -> str:
    return _now_kst().strftime("%Y-%m-%d")


# ── 텍스트 유틸 ──────────────────────────────────────────────
def _as_text(v) -> str:
    """tldr/summary가 list/dict/str 어떤 형태든 평문으로."""
    if not v:
        return ""
    if isinstance(v, str):
        return v.strip()
    if isinstance(v, list):
        return " ".join(_as_text(x) for x in v if x).strip()
    if isinstance(v, dict):
        return " ".join(_as_text(x) for x in v.values() if x).strip()
    return str(v).strip()


def _first_sentence(text: str, max_len: int = 120) -> str:
    t = _as_text(text)
    if not t:
        return ""
    for sep in ("。", ". ", "! ", "? ", "\n"):
        if sep in t:
            t = t.split(sep)[0]
            break
    return t[:max_len].strip()


CAT_TAGS = {
    "finance":    ["#재테크", "#투자"],
    "money":      ["#정부지원금", "#복지"],
    "realestate": ["#부동산", "#내집마련"],
    "startup":    ["#창업", "#사이드잡"],
    "ai":         ["#AI", "#생산성"],
    "book":       ["#책추천", "#자기계발"],
    "trending":   ["#이슈", "#트렌드"],
}


def _hashtags(category: str) -> str:
    tags = ["#직장인"] + CAT_TAGS.get((category or "").lower(), ["#재테크"])
    # 중복 제거 + 최대 3개
    seen, out = set(), []
    for t in tags:
        if t not in seen:
            seen.add(t)
            out.append(t)
        if len(out) >= 3:
            break
    return " ".join(out)


def _post_url(post: dict) -> str:
    """글 공개 URL. slug(매니페스트) 우선, 없으면 파일명 스텁(/p/post_xxx.html 리다이렉트 존재)."""
    slug = (post.get("slug") or "").strip()
    if slug:
        return f"{SITE}/p/{slug}.html"
    fn = (post.get("filename") or "").strip()
    if fn.endswith(".json"):
        return f"{SITE}/p/{fn[:-5]}.html"
    return SITE


# ── 글 변환: 블로그 글 JSON → 쓰레드 포스트 텍스트 ───────────
def _build_thread_prompt(post: dict, url: str) -> str:
    title   = post.get("title", "")
    tldr    = _as_text(post.get("tldr"))
    summary = _as_text(post.get("summary"))
    keyword = post.get("keyword", "")
    trend   = post.get("trend_source", "")
    category = post.get("category", "")

    materials = [f"제목: {title}"]
    if tldr:
        materials.append(f"핵심요약(TLDR): {tldr[:400]}")
    if summary:
        materials.append(f"요약: {summary[:300]}")
    if keyword:
        materials.append(f"키워드: {keyword}")
    if trend:
        materials.append(f"트렌드 출처: {trend}")
    if category:
        materials.append(f"카테고리: {category}")
    material_block = "\n".join(materials)

    return (
        "너는 '직장인 수익일기'(njob_blogosu) 운영자다. 아래 블로그 글을 Threads(쓰레드) "
        "포스트 1개로 변환하라.\n\n"
        f"[입력 재료]\n{material_block}\n\n"
        "[쓰레드 글 작성 규칙 — njob_blogosu 훅 시스템]\n"
        "- 발견자/분석가 톤. 자기계발 설교조 절대 금지.\n"
        "- 훅 4요소 중 가능한 것 적용: 숫자(구체적 수치), 권위(출처/기관), 두려움(놓치면 손해), 출처(근거).\n"
        "- 80% 정보 법칙: 핵심을 다 말하지 말고 궁금하게 남겨 링크 클릭을 유도.\n"
        "- 첫 줄(훅)이 생명: 스크롤을 멈추게. 첫 문장에서 '어?' 하게 만들어라.\n"
        "- 직장인 1인칭 공감 ('저처럼', '우리 직장인은').\n"
        "- 길이: 350자 이내(짧을수록 좋음).\n"
        "- 이모지 1~2개만 자연스럽게.\n"
        "- 해시태그 2~3개(#직장인 등 관련).\n"
        f"- 맨 끝 줄에 반드시 이 링크를 그대로: {url}\n\n"
        "[출력] 쓰레드 포스트 텍스트만. 설명·따옴표·머리말 없이 본문만 출력."
    )


def _gemini_convert(post: dict, url: str) -> str | None:
    """Gemini로 쓰레드 텍스트 생성. 키 없거나 실패 시 None."""
    key = os.getenv("GEMINI_API_KEY", "").strip()
    if not key:
        return None
    api = (
        "https://generativelanguage.googleapis.com/v1beta/models/"
        f"gemini-2.5-flash:generateContent?key={key}"
    )
    payload = {
        "contents": [{"parts": [{"text": _build_thread_prompt(post, url)}]}],
        "generationConfig": {
            "temperature": 0.85,
            "topP": 0.95,
            "maxOutputTokens": 1000,
            "thinkingConfig": {"thinkingBudget": 0},
        },
    }
    try:
        r = requests.post(api, headers={"Content-Type": "application/json"},
                          json=payload, timeout=45)
        if r.status_code != 200:
            print(f"   [convert] Gemini {r.status_code}: {r.text[:200]}")
            return None
        data = r.json()
        text = data["candidates"][0]["content"]["parts"][0]["text"].strip()
        return text or None
    except Exception as e:
        print(f"   [convert] Gemini 예외: {e}")
        return None


def _fallback_thread_text(post: dict, url: str) -> str:
    """Gemini 미사용/실패 시 템플릿 기반 쓰레드 텍스트 (프로덕션 폴백 겸용)."""
    title = _as_text(post.get("title"))
    hook = _first_sentence(post.get("tldr") or post.get("summary")) or title
    body = ""
    summ = _first_sentence(post.get("summary") or post.get("tldr"), 100)
    # 훅과 앞부분이 거의 같으면(중복 느낌) 본문 생략
    if summ and summ[:12] != hook[:12]:
        body = summ
    tags = _hashtags(post.get("category"))
    parts = [p for p in [hook, body, "👉 자세한 건 블로그에 정리했어요.", url, tags] if p]
    return "\n\n".join(parts)


def _finalize_thread_text(text: str, url: str) -> str:
    """링크 보장 + 길이 안전화 (URL은 항상 보존)."""
    t = (text or "").strip().strip('"').strip("'").strip("`").strip()
    if url and url not in t:
        t = t.rstrip() + "\n\n" + url
    if len(t) <= THREAD_MAX_LEN:
        return t
    # 너무 길면: URL 줄을 떼어내고 본문만 컷 후 재결합
    if url in t:
        body = t.replace(url, "").rstrip()
        keep = THREAD_MAX_LEN - len(url) - 4
        body = body[:max(keep, 0)].rstrip()
        t = body + "\n\n" + url
    else:
        t = t[:THREAD_MAX_LEN].rstrip()
    return t


def convert_post_to_thread(post: dict) -> str:
    """블로그 글(dict) → 쓰레드 포스트 텍스트. Gemini 우선, 실패 시 템플릿 폴백."""
    url = _post_url(post)
    text = _gemini_convert(post, url)
    used = "Gemini"
    if not text:
        text = _fallback_thread_text(post, url)
        used = "템플릿폴백"
    final = _finalize_thread_text(text, url)
    post["_convert_via"] = used
    return final


# ── 발행 대상 글 선정 ────────────────────────────────────────
def select_posts_for_threads(count: int = THREADS_PER_DAY) -> list:
    """쓰레드 발행용 글 선정.
       조건: status=published, thread_published 아님.
       우선순위: 오늘(KST) > 트렌드글 > 최신순. 최대 count개."""
    try:
        manifest = json.loads(MANIFEST_PATH.read_text(encoding="utf-8"))
    except Exception as e:
        print(f"   [select] manifest 로드 실패: {e}")
        return []

    today = _today_kst()
    candidates = []
    for entry in manifest:
        if entry.get("status") != "published":
            continue
        fn = entry.get("filename", "")
        if not fn:
            continue
        jp = {}
        try:
            jp = json.loads((POSTS_DIR / fn).read_text(encoding="utf-8"))
        except Exception:
            jp = {}
        if jp.get("thread_published"):
            continue
        created = jp.get("created_at") or entry.get("created_at") or ""
        trend = jp.get("trend_source") or entry.get("trend_source") or ""
        candidates.append({
            "filename":     fn,
            "title":        entry.get("title") or jp.get("title", ""),
            "slug":         entry.get("slug") or "",
            "tldr":         jp.get("tldr"),
            "summary":      jp.get("summary") or entry.get("summary", ""),
            "keyword":      jp.get("keyword") or entry.get("keyword", ""),
            "category":     jp.get("category") or entry.get("category", ""),
            "trend_source": trend,
            "created_at":   created,
            "_is_today":    created[:10] == today,
            "_is_trend":    bool(trend),
        })

    candidates.sort(
        key=lambda c: (c["_is_today"], c["_is_trend"], c["created_at"]),
        reverse=True,
    )
    return candidates[:count]


# ── 상태 파일 (중복실행/토큰만료 가드) ───────────────────────
def _load_state() -> dict:
    try:
        return json.loads(STATE_PATH.read_text(encoding="utf-8"))
    except Exception:
        return {}


def _save_state(state: dict):
    try:
        STATE_PATH.write_text(json.dumps(state, ensure_ascii=False, indent=2), encoding="utf-8")
    except Exception as e:
        print(f"   [state] 저장 실패: {e}")


def _mark_thread_published(filename: str, url: str):
    """post JSON에 thread_published 플래그/URL 기록 (재발행 차단)."""
    path = POSTS_DIR / filename
    try:
        jp = json.loads(path.read_text(encoding="utf-8"))
        jp["thread_published"] = True
        jp["thread_url"] = url
        jp["thread_published_at"] = _now_kst().strftime("%Y-%m-%dT%H:%M:%S+09:00")
        path.write_text(json.dumps(jp, ensure_ascii=False, indent=2), encoding="utf-8")
    except Exception as e:
        print(f"   [mark] {filename} 플래그 기록 실패: {e}")


# ── 시간대 슬롯 (하루 4회 분산: KST 07/12/18/22) ──────────────
SLOTS_KST = [7, 12, 18, 22]


def _current_slot() -> str:
    """현재 KST 시각이 속한 발행 슬롯 id ('YYYY-MM-DD#HH').
    cron은 정시 또는 그 이후에만 발동하므로 '현재시각 이하의 가장 큰 슬롯'으로 버킷팅."""
    now = _now_kst()
    hour = now.hour
    eligible = [s for s in SLOTS_KST if s <= hour]
    slot_hour = eligible[-1] if eligible else SLOTS_KST[0]
    return f"{now.strftime('%Y-%m-%d')}#{slot_hour:02d}"


def _slot_done(state: dict, slot: str) -> bool:
    today = slot.split("#")[0]
    return slot in state.get("done_slots", {}).get(today, [])


def _record_slot(state: dict, slot: str):
    """슬롯 완료 기록 (오늘 날짜만 유지해 상태파일 비대화 방지)."""
    today = slot.split("#")[0]
    done = state.get("done_slots", {}).get(today, [])
    if slot not in done:
        done.append(slot)
    state["done_slots"] = {today: done}  # 과거 날짜 정리


# ── 토큰 만료 임박 시 갱신 (공통 헬퍼) ───────────────────────
def _ensure_token(token: str, state: dict) -> tuple:
    """만료 임박이면 refresh. (token, refreshed) 반환. state(token_expires_at) 갱신."""
    refreshed = False
    exp_iso = state.get("token_expires_at")
    need_refresh = False
    if exp_iso:
        try:
            exp = datetime.datetime.fromisoformat(exp_iso)
            left = (exp - _now_kst()).days
            print(f"   [token] 만료까지 ~{left}일")
            need_refresh = left <= REFRESH_BEFORE_DAYS
        except Exception:
            need_refresh = True
    else:
        # 만료시각 미상(외부 Secret 설정) → 갓 설정됐다고 가정하고 기록만
        state["token_expires_at"] = (
            _now_kst() + datetime.timedelta(days=TOKEN_LIFETIME_DAYS)
        ).isoformat()
        print("   [token] 만료시각 미상 → 신규로 가정해 기록")

    if need_refresh:
        print("   [token] 만료 임박 → 갱신 시도")
        nt = refresh_token(token)
        if nt:
            token = nt
            refreshed = True
            state["token_expires_at"] = (
                _now_kst() + datetime.timedelta(days=TOKEN_LIFETIME_DAYS)
            ).isoformat()
            try:
                NEW_TOKEN_FILE.write_text(nt, encoding="utf-8")
                print(f"   [token] ✓ 갱신됨 → {NEW_TOKEN_FILE.name} 기록 (GitHub Secret 갱신용)")
            except Exception as e:
                print(f"   [token] 갱신토큰 파일 기록 실패: {e}")
        else:
            print("   [token] ⚠ 갱신 실패 → 기존 토큰으로 진행")
    return token, refreshed


def _print_thread_preview(idx: int, total: int, p: dict, text: str, url: str):
    print("-" * 60)
    print(f"[{idx}/{total}] {p['filename']}  (today={p['_is_today']}, trend={p['_is_trend']}, via={p.get('_convert_via')})")
    print(f"   제목: {p['title'][:50]}")
    print(f"   URL : {url}")
    print(f"   ── 변환된 쓰레드 텍스트 ({len(text)}자) ──")
    for line in text.split("\n"):
        print(f"   | {line}")


def select_one_post_for_thread() -> dict | None:
    """쓰레드 발행용 글 1개 (최우선순위) 선정."""
    posts = select_posts_for_threads(1)
    return posts[0] if posts else None


# ── DRY-RUN 미리보기 (실제 Gemini 변환 품질 확인용) ──────────
def preview_samples(n: int = 4):
    print("=" * 60)
    print(f" Threads 변환 미리보기 (DRY-RUN, {n}개) — 발행 안 함")
    has_key = "ON(Gemini)" if os.getenv("GEMINI_API_KEY", "").strip() else "OFF(템플릿폴백)"
    print(f" GEMINI_API_KEY: {has_key}")
    print("=" * 60)
    posts = select_posts_for_threads(n)
    if not posts:
        print("   발행 대상 글 없음")
        return
    for i, p in enumerate(posts, 1):
        url = _post_url(p)
        text = convert_post_to_thread(p)
        _print_thread_preview(i, len(posts), p, text, url)
    print("\n" + "=" * 60)
    print(f"✅ 미리보기 완료 — {len(posts)}개 (발행 안 함)")
    print("=" * 60)


# ── 1개 발행 엔트리 (--once): 시간대 슬롯당 1개 ──────────────
def publish_one_thread(dry_run: bool = False, force: bool = False):
    mode = "DRY-RUN (발행 안 함)" if dry_run else "실발행"
    slot = _current_slot()
    print("=" * 60)
    print(f" Threads 1개 발행 [{slot}] — {mode}")
    print("=" * 60)

    user_id = os.getenv("THREADS_USER_ID", "").strip()
    token   = os.getenv("THREADS_ACCESS_TOKEN", "").strip()
    if not dry_run and not (user_id and token):
        print("❌ THREADS_USER_ID / THREADS_ACCESS_TOKEN 누락 → 중단")
        sys.exit(1)

    state = _load_state()

    # ── 시간대 슬롯 중복 가드 (같은 슬롯 재실행만 차단, 다른 슬롯은 발행) ──
    if not dry_run and not force and _slot_done(state, slot):
        print(f"⏭  슬롯 {slot} 이미 발행됨 → 중복 방지 SKIP (강제: --force)")
        return

    refreshed = False
    if not dry_run:
        token, refreshed = _ensure_token(token, state)

    p = select_one_post_for_thread()
    if not p:
        print("   발행할 신규 글 없음 (모두 thread_published 이거나 published 글 없음)")
        return

    url = _post_url(p)
    text = convert_post_to_thread(p)
    _print_thread_preview(1, 1, p, text, url)

    if dry_run:
        print("\n✅ DRY-RUN 완료 (발행 안 함)")
        return

    res = publish_text(user_id, token, text)
    _record_slot(state, slot)  # cron 중복발동 대비: 시도한 슬롯은 기록
    if res:
        _mark_thread_published(p["filename"], res.get("permalink") or url)
        print(f"   ✓ 발행 성공: {res.get('permalink') or res['id']}")
    else:
        print("   ✗ 발행 실패")
    _save_state(state)

    print("\n" + "=" * 60)
    print(f"✅ 슬롯 {slot} 처리 완료 ({'성공' if res else '실패'})")
    if refreshed:
        print(f"   ★ 토큰 갱신됨 → GitHub Secret THREADS_ACCESS_TOKEN 갱신 필요 ({NEW_TOKEN_FILE.name})")
    print("=" * 60)


# ── 일괄 발행 엔트리 (--daily): 1회 실행에 N개 (수동/레거시) ──
def run_daily_threads(dry_run: bool = False, force: bool = False):
    mode = "DRY-RUN (발행 안 함)" if dry_run else "실발행"
    print("=" * 60)
    print(f" Threads 일괄 발행 ({THREADS_PER_DAY}개) — {mode}")
    print("=" * 60)

    user_id = os.getenv("THREADS_USER_ID", "").strip()
    token   = os.getenv("THREADS_ACCESS_TOKEN", "").strip()

    if not dry_run and not (user_id and token):
        print("❌ THREADS_USER_ID / THREADS_ACCESS_TOKEN 누락 → 중단")
        sys.exit(1)

    state = _load_state()
    today = _today_kst()

    if not dry_run and not force and state.get("last_run_date") == today:
        print(f"⏭  오늘({today}) 이미 일괄실행됨 → 중복 방지 SKIP (강제: --force)")
        return

    refreshed = False
    if not dry_run:
        token, refreshed = _ensure_token(token, state)

    posts = select_posts_for_threads(THREADS_PER_DAY)
    print(f"\n   선정된 글 {len(posts)}개 (최대 {THREADS_PER_DAY})\n")
    if not posts:
        print("   발행할 신규 글 없음 (모두 thread_published 이거나 published 글 없음)")
        return

    ok, fail = 0, 0
    for i, p in enumerate(posts, 1):
        url = _post_url(p)
        text = convert_post_to_thread(p)
        _print_thread_preview(i, len(posts), p, text, url)

        if dry_run:
            continue

        res = publish_text(user_id, token, text)
        if res:
            ok += 1
            _mark_thread_published(p["filename"], res.get("permalink") or url)
            print(f"   ✓ 발행 성공: {res.get('permalink') or res['id']}")
        else:
            fail += 1
            print("   ✗ 발행 실패")

        if i < len(posts):
            print(f"   ...다음 글까지 {PUBLISH_GAP_SEC}초 대기")
            time.sleep(PUBLISH_GAP_SEC)

    if not dry_run:
        state["last_run_date"] = today
        _save_state(state)

    print("\n" + "=" * 60)
    if dry_run:
        print(f"✅ DRY-RUN 완료 — {len(posts)}개 변환 미리보기 (발행 안 함)")
    else:
        print(f"✅ 발행 완료 — 성공 {ok} / 실패 {fail} / 대상 {len(posts)}")
        if refreshed:
            print(f"   ★ 토큰 갱신됨 → GitHub Secret THREADS_ACCESS_TOKEN 갱신 필요 ({NEW_TOKEN_FILE.name})")
    print("=" * 60)


# ── 메인: 테스트 모드 (토큰 교환 → 테스트 발행) ──────────────
TEST_TEXT = "직장인 수익일기 자동발행 테스트입니다 🤖 https://koreansalaryman.com"


def main():
    show_token = "--show-token" in sys.argv  # 마스킹 해제 옵션 (Secret 갱신용)

    short_token = os.getenv("THREADS_ACCESS_TOKEN", "").strip()
    user_id = os.getenv("THREADS_USER_ID", "").strip()
    app_secret = os.getenv("THREADS_APP_SECRET", "").strip()

    print("=" * 60)
    print(" Threads 발행 모듈 — 테스트 모드")
    print("=" * 60)
    print(f"  THREADS_USER_ID:      {user_id or '(미설정)'}")
    print(f"  THREADS_ACCESS_TOKEN: {_mask(short_token)}")
    print(f"  THREADS_APP_SECRET:   {'설정됨' if app_secret else '(미설정)'}")
    print("-" * 60)

    if not (short_token and user_id and app_secret):
        print("\n❌ 환경변수 누락. .env에 아래 3개를 채우세요:")
        print("   THREADS_ACCESS_TOKEN=<단기 액세스 토큰>")
        print("   THREADS_USER_ID=37096544403277101")
        print("   THREADS_APP_SECRET=<앱 시크릿>")
        sys.exit(1)

    # 1) 단기 → 장기 교환
    print("\n[1/2] 단기 → 장기 토큰 교환...")
    long_token = exchange_token(short_token, app_secret)
    if not long_token:
        print("\n❌ 토큰 교환 실패. 단기토큰 만료/오타 여부 확인.")
        sys.exit(1)

    if show_token:
        print(f"\n   ★ 장기토큰(전체) ↓↓↓ — GitHub Secret THREADS_ACCESS_TOKEN 에 넣으세요")
        print(f"   {long_token}\n")
    else:
        print(f"   장기토큰(마스킹): {_mask(long_token)}")
        print(f"   (전체 출력은 `python threads_publisher.py --show-token`)")

    # 2) 테스트 글 발행 (장기토큰 사용)
    print("\n[2/2] 테스트 글 발행...")
    result = publish_text(user_id, long_token, TEST_TEXT)
    if not result:
        print("\n❌ 테스트 발행 실패 (위 로그 확인). 장기토큰 교환은 성공했음.")
        sys.exit(1)

    print("\n" + "=" * 60)
    print("✅ 성공")
    print(f"   thread id: {result['id']}")
    if result.get("permalink"):
        print(f"   URL:       {result['permalink']}")
    print(f"   본문:      {TEST_TEXT}")
    print("=" * 60)


def _int_arg(name: str, default: int) -> int:
    if name in sys.argv:
        try:
            return int(sys.argv[sys.argv.index(name) + 1])
        except (ValueError, IndexError):
            return default
    return default


if __name__ == "__main__":
    _dry = "--dry-run" in sys.argv
    _force = "--force" in sys.argv
    if "--once" in sys.argv:
        # 시간대 슬롯당 1개 발행 (cron 4회 분산용)
        publish_one_thread(dry_run=_dry, force=_force)
    elif "--daily" in sys.argv:
        # 1회 실행에 N개 일괄 발행 (수동/레거시)
        run_daily_threads(dry_run=_dry, force=_force)
    elif _dry:
        # 변환 품질 미리보기 (--samples N, 기본 4)
        preview_samples(_int_arg("--samples", 4))
    else:
        main()
