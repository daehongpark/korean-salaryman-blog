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
import time

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


# ── 메인: 테스트 모드 (토큰 교환 → 테스트 발행) ──────────────
TEST_TEXT = "직장인 수익일기 자동발행 테스트입니다 🤖 https://koreansalaryman.com"


def main():
    show_token = "--show-token" in sys.argv  # 마스킹 해제 옵션 (Secret 갱신용)

    short_token = os.getenv("THREADS_ACCESS_TOKEN", "").strip()
    user_id = os.getenv("THREADS_USER_ID", "").strip()
    app_secret = os.getenv("THREADS_APP_SECRET", "").strip()

    print("═" * 60)
    print(" Threads 발행 모듈 — 테스트 모드")
    print("═" * 60)
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

    print("\n" + "═" * 60)
    print("✅ 성공")
    print(f"   thread id: {result['id']}")
    if result.get("permalink"):
        print(f"   URL:       {result['permalink']}")
    print(f"   본문:      {TEST_TEXT}")
    print("═" * 60)


if __name__ == "__main__":
    main()
