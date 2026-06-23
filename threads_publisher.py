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
def publish_text(user_id: str, token: str, text: str, reply_to_id: str | None = None) -> dict | None:
    """텍스트 글을 발행. reply_to_id 주면 해당 글의 답글로 발행.
    성공 시 {'id': thread_id, 'permalink': url} 반환, 실패 시 None."""
    # 1단계: 컨테이너 생성
    create_url = f"{GRAPH}/{API_VERSION}/{user_id}/threads"
    create_params = {
        "media_type": "TEXT",
        "text": text,
        "access_token": token,
    }
    if reply_to_id:
        create_params["reply_to_id"] = reply_to_id
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
P_DIR         = ROOT / "p"                          # 정적 글 페이지(/p/{slug}.html)
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


def _encode_post_url(slug_html: str) -> str:
    """글 파일명(.html 포함) → 퍼센트 인코딩된 절대 URL.
    한글 경로가 쓰레드 인앱브라우저에서 인코딩 안 돼 404나는 문제 해결.
    NFC 정규화(iOS NFD 대응) 후 quote(슬래시/하이픈/점은 유지)."""
    import unicodedata
    import urllib.parse
    fn = unicodedata.normalize("NFC", slug_html)
    encoded_path = urllib.parse.quote("/p/" + fn, safe="/")  # 한글→%XX, '/'.'-' 등 유지
    return f"{SITE}{encoded_path}"


def _resolve_post_url(post: dict) -> str | None:
    """실제 존재하는 정적 파일을 가리키는 글 URL(퍼센트 인코딩)을 반환 (404 방지).
    우선순위: ① manifest slug  ② title→make_slug(정적생성과 동일 규칙)  ③ 파일명 스텁.
    파일 존재 확인은 raw 한글 파일명으로, 내보내는 URL만 인코딩.
    셋 다 p/ 디렉토리에 실파일이 없으면 None(→ 발행 스킵)."""
    candidates = []
    slug = (post.get("slug") or "").strip()
    if slug:
        candidates.append(slug)
    title = post.get("title") or ""
    if title:
        try:
            from generate_static_posts import make_slug  # 정적 생성과 동일 규칙 재사용
            ms = make_slug(title, set())
            if ms and ms not in candidates:
                candidates.append(ms)
        except Exception as e:
            print(f"   [url] make_slug 재사용 실패(무시): {e}")
    fn = (post.get("filename") or "").strip()
    if fn.endswith(".json"):
        candidates.append(fn[:-5])   # /p/post_xxx.html 리다이렉트 스텁
    for c in candidates:
        if c and (P_DIR / f"{c}.html").exists():   # 존재 확인은 raw 파일명
            return _encode_post_url(f"{c}.html")    # 내보내는 URL만 인코딩
    return None


def _post_url(post: dict) -> str | None:
    """이미 select 단계에서 해결된 url이 있으면 그대로, 없으면 재해결."""
    return post.get("url") or _resolve_post_url(post)


def _is_book_post(post: dict) -> bool:
    """독서글 여부. select가 넣어준 _is_book 우선, 없으면 즉석 판정."""
    if "_is_book" in post:
        return bool(post["_is_book"])
    return _looks_like_book(post.get("category", ""), post.get("keyword", ""), post.get("title", ""))


# ── 글 변환: 블로그 글 JSON → 쓰레드 포스트 텍스트 ───────────
def _build_thread_prompt(post: dict) -> str:
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

    if _is_book_post(post):
        # 독서글 — '직장인 성공 독서' 각도
        intro = (
            "너는 '직장인 수익일기'(njob_blogosu) 운영자다. 아래는 네가 읽은 책에 대한 블로그 글이다. "
            "이걸 '직장인이 성공하려고 읽는 책' 관점의 Threads 포스트 1개로 변환하라.\n\n"
            f"[입력 재료]\n{material_block}\n\n"
            "[독서글 변환 각도 — '직장인 성공 독서']\n"
            "- 프레임: '직장인이 성공하기 위해 읽는 책' 관점. 이 책이 직장인/부업/성장에 왜 도움되는지.\n"
            "- 책 제목·저자가 재료에 있으면 자연스럽게 살려라(없으면 억지로 지어내지 마라).\n"
            "- 첫 줄 훅: 책 제목을 들이대지 말고, 그 책이 준 핵심 통찰/문제의식으로 시작해 궁금하게.\n"
            "  · (X) 'OO이라는 책을 읽었다'\n"
            "  · (O) '퇴근하고 1시간, 뭘 해야 하나 막막했는데 이 책이 답을 줬어'\n"
            "- 80% 법칙(책 버전): 책 핵심 메시지 1개만 살짝 풀고, 구체적 방법·사례는 블로그로 넘겨라.\n"
            "- ★ 자기계발 설교조 절대 금지. '이 책 이래서 쓸모 있더라' 식 발견자·분석가 톤.\n\n"
        )
    else:
        intro = (
            "너는 '직장인 수익일기'(njob_blogosu) 운영자다. 아래 블로그 글을 Threads(쓰레드) "
            "포스트 1개로 변환하라.\n\n"
            f"[입력 재료]\n{material_block}\n\n"
        )

    return (
        intro +
        "[말투 — 가장 중요]\n"
        "- ★ 반드시 반말 구어체로 써라. 존댓말('~습니다/~합니다/~하세요/~예요/~해요/~하죠/~죠/~네요') 절대 금지.\n"
        "- 친한 친구한테 정보 공유하듯이. 혼잣말하듯 툭 던지는 느낌도 좋다.\n"
        "- 종결어미는 반말로: ~야, ~어, ~지, ~대, ~더라, ~잖아, ~네, ~거든, ~줘, ~봐 등.\n"
        "- 질문도 반말로: '이거 알아?', '지금 들어가도 되나?', '너도 그래?'\n"
        "- 예시 톤:\n"
        "  · (X 존댓말) '가계대출이 6조원 늘었습니다. 관리하는 게 중요해요.'\n"
        "  · (O 반말) '가계대출 6조원 늘었대. 이거 남 일 아니야 진짜.'\n"
        "  · (O) '동탄 9.5% 올랐다는데... 지금 들어가도 되나?'\n"
        "  · (O) '아침에 달걀 먹는 거, 콜레스테롤 걱정했었는데 아니더라고.'\n"
        "- 너무 가볍게 까불지는 말고. 정보는 진지하게, 말투만 편하게 (발견자 톤은 유지하되 반말로).\n\n"
        "[나머지 규칙 — njob_blogosu 훅 시스템]\n"
        "- 발견자/분석가 톤. 자기계발 설교조 절대 금지.\n"
        "- 훅 4요소 중 가능한 것 적용: 숫자(구체적 수치), 권위(출처/기관), 두려움(놓치면 손해), 출처(근거).\n"
        "- 80% 정보 법칙: 핵심을 다 말하지 말고 궁금하게 남겨 링크 클릭을 유도.\n"
        "- 첫 줄(훅)이 생명: 스크롤을 멈추게. 첫 문장에서 '어?' 하게 만들어라.\n"
        "- ★ 첫 줄 '야,'로 시작 금지(무례하고 패턴 뻔함). 부르는 말 없이 바로 본론·훅으로 시작해라.\n"
        "  · (X) '야, 5대 은행 가계대출 6조 늘었대'\n"
        "  · (O) '5대 은행 가계대출, 두 달 새 6조 늘었대'\n"
        "  · (O) '동탄 9.5% 올랐대. 지금 들어가도 되나?'\n"
        "  · 굳이 부르려면 '직장인이라면', '월급쟁이들' 정도만 가끔.\n"
        "- ★ 이모지·이모티콘 절대 쓰지 말 것(🙄🤯🥚😮 등 전부 금지). 깔끔한 텍스트로만.\n"
        "- ★ 해시태그(#...) 절대 쓰지 말 것.\n"
        "- ★ 링크/URL 넣지 마라. 링크는 별도 답글로 따로 단다.\n"
        "- 직장인 1인칭 공감 ('나도', '우리 직장인'). 단 반말로.\n"
        "- 길이: 350자 이내(짧을수록 좋음).\n\n"
        "[출력] 쓰레드 포스트 텍스트만 출력. 설명·머리말 금지. "
        "재료의 라벨('제목:', 'TLDR:', '핵심요약:', '요약:', '키워드:' 등)을 그대로 쓰지 마라. "
        "전체를 따옴표로 감싸지 말고, 첫 줄 맨 앞에 따옴표(\"나 ')도 붙이지 마라."
    )


def _gemini_convert(post: dict) -> str | None:
    """Gemini로 쓰레드 본문 생성(링크/해시태그 없음). 키 없거나 실패 시 None."""
    key = os.getenv("GEMINI_API_KEY", "").strip()
    if not key:
        return None
    api = (
        "https://generativelanguage.googleapis.com/v1beta/models/"
        f"gemini-2.5-flash:generateContent?key={key}"
    )
    payload = {
        "contents": [{"parts": [{"text": _build_thread_prompt(post)}]}],
        "generationConfig": {
            "temperature": 0.85,
            "topP": 0.95,
            "maxOutputTokens": 1000,
            "thinkingConfig": {"thinkingBudget": 0},
        },
    }
    # 503(high demand)/429는 일시적 → 짧게 재시도, 그래도 실패면 템플릿 폴백
    for attempt in range(3):
        try:
            r = requests.post(api, headers={"Content-Type": "application/json"},
                              json=payload, timeout=45)
            if r.status_code == 200:
                data = r.json()
                text = data["candidates"][0]["content"]["parts"][0]["text"].strip()
                return text or None
            if r.status_code in (429, 503) and attempt < 2:
                print(f"   [convert] Gemini {r.status_code} 일시적 → 재시도 {attempt + 1}/2")
                time.sleep(4)
                continue
            print(f"   [convert] Gemini {r.status_code}: {r.text[:150]}")
            return None
        except Exception as e:
            print(f"   [convert] Gemini 예외: {e}")
            if attempt < 2:
                time.sleep(4)
                continue
            return None
    return None


def _fallback_thread_text(post: dict) -> str:
    """Gemini 미사용/실패 시 템플릿 기반 본문 (링크/해시태그 없음 — 링크는 답글로)."""
    title = _as_text(post.get("title"))
    hook = _first_sentence(post.get("tldr") or post.get("summary")) or title
    body = ""
    summ = _first_sentence(post.get("summary") or post.get("tldr"), 100)
    # 훅과 앞부분이 거의 같으면(중복 느낌) 본문 생략
    if summ and summ[:12] != hook[:12]:
        body = summ
    parts = [p for p in [hook, body] if p]
    return "\n\n".join(parts)


_QUOTES = "\"'`“”‘’"


def _strip_quotes(text: str) -> str:
    """전체 감싼 따옴표 제거 + 첫 줄 맨 앞 군더더기 따옴표 제거 (변환 따옴표 버그)."""
    t = (text or "").strip()
    # 전체가 따옴표로 감싸졌으면 한 겹 벗기기
    while len(t) >= 2 and t[0] in _QUOTES and t[-1] in _QUOTES:
        t = t[1:-1].strip()
    # 첫 줄 맨 앞에 남은 따옴표 제거
    t = t.lstrip("".join(set(_QUOTES))).lstrip()
    return t


import re as _re

# 이모지/이모티콘 유니코드 범위 (해시태그 '#'는 ASCII라 영향 없음)
_EMOJI_RE = _re.compile(
    "["
    "\U0001F000-\U0001FAFF"   # 이모티콘/기호/그림/보충 심볼 (대부분의 이모지)
    "\U00002600-\U000027BF"   # 기타 기호 + 딩뱃
    "\U00002B00-\U00002BFF"   # 기타 기호/별/화살표
    "\U00002300-\U000023FF"   # 기술 기호 (⌚⏰⏳ 등)
    "\U0000FE00-\U0000FE0F"   # 변이 선택자 (emoji presentation)
    "\U0000200D"              # ZWJ (이모지 결합용)
    "\U000024C2"              # Ⓜ
    "\U00002122\U00002139"    # ™ ℹ
    "]+",
    flags=_re.UNICODE,
)


def _strip_emoji(text: str) -> str:
    """변환 결과에서 이모지/이모티콘 제거 (분석가 톤 유지). 해시태그 '#'는 유지."""
    if not text:
        return text
    t = _EMOJI_RE.sub("", text)
    # 이모지 제거로 생긴 잉여 공백 정리 (줄 단위)
    cleaned = []
    for ln in t.split("\n"):
        ln = _re.sub(r"[ \t]{2,}", " ", ln)
        ln = _re.sub(r" +([.,!?…])", r"\1", ln)   # 이모지 제거로 생긴 '문장 .' → '문장.'
        cleaned.append(ln.rstrip())
    return "\n".join(cleaned).strip()


def _strip_hashtags(text: str) -> str:
    """결과에서 해시태그 제거 (해시태그-only 줄 통째 제거 + 인라인 #태그 제거)."""
    if not text:
        return text
    out = []
    for ln in text.split("\n"):
        stripped = ln.strip()
        # 해시태그만 있는 줄은 통째 제거
        if stripped and all(tok.startswith("#") for tok in stripped.split()):
            continue
        ln = _re.sub(r"#\S+", "", ln)               # 인라인 해시태그 제거
        ln = _re.sub(r"[ \t]{2,}", " ", ln).rstrip()
        out.append(ln)
    res = "\n".join(out)
    return _re.sub(r"\n{3,}", "\n\n", res).strip()


def _finalize_body(text: str) -> str:
    """본문 정리: 따옴표/이모지/해시태그 제거 + 길이 안전화 (링크는 본문에 없음)."""
    t = _strip_hashtags(_strip_emoji(_strip_quotes(text)))
    t = _re.sub(r"\n{3,}", "\n\n", t).strip()
    if len(t) > THREAD_MAX_LEN:
        t = t[:THREAD_MAX_LEN].rstrip()
    return t


def convert_post_to_thread(post: dict) -> str:
    """블로그 글(dict) → 쓰레드 본문(링크/해시태그 없음). Gemini 우선, 실패 시 템플릿 폴백."""
    text = _gemini_convert(post)
    used = "Gemini"
    if not text:
        text = _fallback_thread_text(post)
        used = "템플릿폴백"
    final = _finalize_body(text)
    post["_convert_via"] = used
    return final


# 독서/책 글 식별. category=='book'이 1차 신호.
# (주의: '책' 단독 매칭은 '정책'을, '읽' 단독은 '읽기'를 오탐 → 정밀 구절만 사용)
_BOOK_HINTS = (
    "독서", "서평", "독후감", "완독", "북리뷰", "북 리뷰",
    "책추천", "책 추천", "책 리뷰", "도서 리뷰", "읽은 책", "이 책", "book review",
)


def _looks_like_book(category: str, keyword: str, title: str) -> bool:
    if (category or "").strip().lower() == "book":
        return True
    blob = f"{keyword} {title}".lower()
    return any(h.lower() in blob for h in _BOOK_HINTS)


# ── 발행 대상 글 선정 ────────────────────────────────────────
def select_posts_for_threads(count: int = THREADS_PER_DAY) -> list:
    """쓰레드 발행용 글 선정.
       조건: status=published, thread_published 아님, 정적파일 존재.
       풀: 트렌드 글 + 직접 쓴 글(독서/주제, trend_source 없음) 동등 포함.
       우선순위: ① 오늘(KST) 발행 글  ② 그 외 — 트렌드/직접글 번갈아(쏠림 방지) 최신순."""
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
        category = jp.get("category") or entry.get("category", "")
        keyword = jp.get("keyword") or entry.get("keyword", "")
        title = entry.get("title") or jp.get("title", "")
        candidates.append({
            "filename":     fn,
            "title":        title,
            "slug":         entry.get("slug") or "",
            "tldr":         jp.get("tldr"),
            "summary":      jp.get("summary") or entry.get("summary", ""),
            "keyword":      keyword,
            "category":     category,
            "trend_source": trend,
            "created_at":   created,
            "_is_today":    created[:10] == today,
            "_is_trend":    bool(trend),
            "_is_book":     _looks_like_book(category, keyword, title),
            "_force":       bool(jp.get("force_thread")),
            "_force_at":    jp.get("force_thread_at") or "",
        })

    # ── 우선순위 정렬 ──
    # ★ force_thread(관리자 '쓰레드로 발행')가 최우선. 여럿이면 찍은 시각 오래된 순.
    forced = sorted(
        [c for c in candidates if c["_force"]],
        key=lambda c: c["_force_at"] or c["created_at"],
    )
    # 오늘 글은 그 다음(최신순). 나머지는 트렌드/직접글 번갈아(쏠림 방지) 최신순.
    non_forced = [c for c in candidates if not c["_force"]]
    today_posts = sorted(
        [c for c in non_forced if c["_is_today"]],
        key=lambda c: c["created_at"], reverse=True,
    )
    rest = [c for c in non_forced if not c["_is_today"]]
    trend_pool  = sorted([c for c in rest if c["_is_trend"]],     key=lambda c: c["created_at"], reverse=True)
    direct_pool = sorted([c for c in rest if not c["_is_trend"]], key=lambda c: c["created_at"], reverse=True)
    interleaved = []
    i = 0
    while i < len(trend_pool) or i < len(direct_pool):
        # 직접글 먼저 끼워넣어 트렌드 쏠림을 적극 방지
        if i < len(direct_pool):
            interleaved.append(direct_pool[i])
        if i < len(trend_pool):
            interleaved.append(trend_pool[i])
        i += 1
    ordered = forced + today_posts + interleaved

    # URL 해결(실파일 존재) — 404 가리키는 글은 스킵하고 다음 후보로
    selected = []
    for c in ordered:
        url = _resolve_post_url(c)
        if not url:
            print(f"   [select] {c['filename']} 정적파일 없음(404 위험) → 스킵")
            continue
        c["url"] = url
        selected.append(c)
        if len(selected) >= count:
            break
    return selected


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
    """post JSON에 thread_published 플래그/URL 기록 (재발행 차단).
    force_thread(관리자 예약)가 있었으면 소비 처리(제거)해 재발행 방지."""
    path = POSTS_DIR / filename
    try:
        jp = json.loads(path.read_text(encoding="utf-8"))
        jp["thread_published"] = True
        jp["thread_url"] = url
        jp["thread_published_at"] = _now_kst().strftime("%Y-%m-%dT%H:%M:%S+09:00")
        if jp.get("force_thread"):
            jp["force_thread"] = False
            jp["force_thread_done"] = True
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


REPLY_GAP_SEC = 5  # 본문 발행 후 답글(링크) 발행 전 대기


def _reply_link_text(url: str) -> str:
    """본문에 달 답글(링크) 텍스트 — 반말, 이모지 없이."""
    return f"전체 글은 여기. {url}"


def _publish_thread_with_link(user_id: str, token: str, text: str, url: str) -> dict | None:
    """본문 발행 → (5초 후) 같은 글에 링크 답글(self-reply) 발행.
    본문 성공 시 result 반환(reply 실패해도 본문은 유효). 본문 실패 시 None."""
    res = publish_text(user_id, token, text)
    if not res:
        return None
    if url:
        print(f"   [reply] {REPLY_GAP_SEC}초 후 링크 답글 발행...")
        time.sleep(REPLY_GAP_SEC)
        rep = publish_text(user_id, token, _reply_link_text(url), reply_to_id=res["id"])
        if rep:
            res["reply_id"] = rep["id"]
            print(f"   [reply] ✓ 링크 답글 발행 reply_id={rep['id']}")
        else:
            print("   [reply] ⚠ 링크 답글 실패 (본문은 정상 발행됨)")
    return res


def _print_thread_preview(idx: int, total: int, p: dict, text: str, url: str):
    import urllib.parse
    exists = False
    if url:
        raw_fn = urllib.parse.unquote(url.rsplit("/p/", 1)[-1])  # 인코딩 해제 후 raw로 확인
        exists = (P_DIR / raw_fn).exists()
    print("-" * 60)
    print(f"[{idx}/{total}] {p['filename']}  (today={p['_is_today']}, trend={p['_is_trend']}, book={p.get('_is_book')}, via={p.get('_convert_via')})")
    print(f"   제목: {p['title'][:50]}")
    print(f"   ── 본문 (링크/해시태그 없음, {len(text)}자) ──")
    for line in text.split("\n"):
        print(f"   | {line}")
    print(f"   ── 답글(링크) ──")
    print(f"   | {_reply_link_text(url) if url else '(URL 미해결 → 발행 스킵)'}")
    print(f"   링크 파일 실제 존재: {exists}  ({url})")


def select_one_post_for_thread() -> dict | None:
    """쓰레드 발행용 글 1개 (최우선순위) 선정.
    select_posts_for_threads가 force_thread(관리자 '쓰레드로 발행') 글을 최우선 정렬해
    반환하므로, 예약된 글이 있으면 그 글이 1순위로 뽑힌다."""
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

    res = _publish_thread_with_link(user_id, token, text, url)
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

        res = _publish_thread_with_link(user_id, token, text, url)
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
