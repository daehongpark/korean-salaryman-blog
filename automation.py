import os
import json
import time
import subprocess
import requests
from datetime import datetime
from pathlib import Path
from dotenv import load_dotenv

load_dotenv()

# ── 설정 ─────────────────────────────────────────────
GEMINI_API_KEY  = os.getenv("GEMINI_API_KEY")
BLOG_TITLE      = os.getenv("BLOG_TITLE", "직장인 수익일기")
AUTO_PUBLISH    = os.getenv("AUTO_PUBLISH", "false").lower() == "true"
POSTS_PER_DAY   = int(os.getenv("POSTS_PER_DAY", "3"))
UNSPLASH_KEY    = os.getenv("UNSPLASH_ACCESS_KEY", "")   # 선택사항

# ── 경로 설정 ─────────────────────────────────────────
SCRIPT_DIR    = Path(__file__).parent
BLOG_DIR      = SCRIPT_DIR.parent / "korean-salaryman-blog"
POSTS_DIR     = BLOG_DIR / "posts"
MANIFEST_PATH = POSTS_DIR / "manifest.json"

# ── 키워드 풀 ─────────────────────────────────────────
KEYWORD_POOL = {
    "부업 방법": [
        "직장인 부업 추천", "퇴근 후 할 수 있는 부업", "재택 부업 방법",
        "월급 외 수입 만들기", "직장인 N잡 방법", "부업으로 월 100만원 버는 법",
        "스마트스토어 부업", "쿠팡파트너스 부업", "직장인 온라인 부업",
        "부업 시작하는 법 초보", "투잡 추천 직장인", "부업 종류 비교",
        "블로그 대행 부업", "크몽 재능마켓 부업", "배달 부업 현실",
    ],
    "블로그": [
        "에드센스 수익 공개", "블로그로 돈 버는 법", "구글 에드센스 승인 방법",
        "블로그 SEO 최적화", "블로그 글쓰기 팁", "에드센스 클릭단가 높이는 법",
        "블로그 방문자 늘리는 법", "키워드 찾는 방법", "블로그 수익화 방법",
        "구글 검색 상위노출", "블로그 대행 시작하는 법", "블로그 글쓰기 루틴",
    ],
    "자기계발": [
        "직장인 자기계발 방법", "아침 루틴 만들기", "독서 습관 기르는 법",
        "시간 관리 방법 직장인", "목표 설정하는 법", "생산성 높이는 방법",
        "직장인 영어공부 방법", "퇴근 후 자기계발", "번아웃 극복하는 법",
        "직장인 사이드 프로젝트", "성장하는 직장인 습관",
    ],
    "재테크": [
        "직장인 재테크 방법", "월급 관리하는 법", "적금 vs 주식",
        "직장인 투자 시작하기", "ETF 투자 방법", "청약저축 활용법",
        "월급 300만원 재테크", "비상금 만들기", "소비 줄이는 방법",
        "경제적 자유 달성 방법", "파이어족 되는 법", "직장인 절약 방법",
    ],
    "책 추천": [
        "직장인 추천 도서", "재테크 책 추천", "자기계발 책 추천",
        "부업 관련 책 추천", "경제적 자유 책 추천", "투자 책 초보",
        "동기부여 책 추천", "성공한 사람들이 읽은 책", "직장인 필독서",
        "돈 공부 책 추천", "블로그 마케팅 책 추천",
    ],
    "수익 공개": [
        "블로그 수익 공개", "에드센스 월수익", "부업 수익 후기",
        "직장인 N잡 수익", "블로그 대행 수익 공개",
        "부업 6개월 후기", "블로그 1년 수익", "스마트스토어 수익 현실",
    ],
}

# ── 카테고리별 Unsplash 검색어 매핑 ─────────────────────
UNSPLASH_QUERY = {
    "부업 방법":  "side hustle work laptop",
    "블로그":     "blogging writing desk",
    "자기계발":   "personal growth success book",
    "재테크":     "money finance investment",
    "책 추천":    "books reading library",
    "수익 공개":  "income money chart success",
}


# ── 오늘의 키워드 선택 ────────────────────────────────
def get_keywords_for_today():
    import random
    selected = []
    categories = list(KEYWORD_POOL.keys())
    for i in range(POSTS_PER_DAY):
        cat = categories[i % len(categories)]
        kw  = random.choice(KEYWORD_POOL[cat])
        selected.append({"category": cat, "keyword": kw})
    return selected


# ── Unsplash 이미지 가져오기 ─────────────────────────
def fetch_unsplash_image(category: str) -> dict | None:
    """카테고리에 맞는 Unsplash 이미지를 가져옵니다. KEY 없으면 None 반환."""
    if not UNSPLASH_KEY:
        return None
    query = UNSPLASH_QUERY.get(category, "work office")
    try:
        r = requests.get(
            "https://api.unsplash.com/photos/random",
            params={"query": query, "orientation": "landscape", "content_filter": "high"},
            headers={"Authorization": f"Client-ID {UNSPLASH_KEY}"},
            timeout=10,
        )
        if r.status_code == 200:
            data = r.json()
            return {
                "url":  data["urls"]["regular"],
                "alt":  data["alt_description"] or query,
                "credit": data["user"]["name"],
                "credit_link": data["user"]["links"]["html"],
            }
    except Exception as e:
        print(f"   [Unsplash] 이미지 가져오기 실패: {e}")
    return None


# ── 프롬프트 빌더 ─────────────────────────────────────
def build_prompt(category: str, keyword: str) -> str:
    return f"""당신은 대한민국 직장인 블로그 전문 작가입니다.
블로그명: {BLOG_TITLE}
독자: 20~40대 직장인 (월급쟁이, 부업에 관심 있음)
카테고리: {category}
핵심 키워드: {keyword}

[글쓰기 원칙]
1. 첫 문단(2~3문장): 독자가 공감할 현실적인 상황으로 시작 → 이 글을 읽어야 하는 이유 제시
2. 본문은 반드시 소제목(##)으로 3~4개 섹션 구분
3. 각 섹션 끝에는 핵심 포인트 1줄 요약 ("> 포인트:" 형식)
4. 구체적 수치/사례 반드시 포함 (예: "월 23만원", "3개월 만에", "하루 1시간")
5. 나열 금지 — 각 항목마다 이유/근거/경험 포함
6. 마지막 문단: 독자를 응원하는 따뜻한 마무리 + 댓글/공유 유도
7. 전체 분량: 1,500~2,000자

[형식 선택 기준]
- 후기/공개/달성/해봤더니 → 스토리텔링 (1인칭 경험 서술)
- 방법/하는법/시작하기 → 실용 가이드 (단계별)
- 추천/비교/vs → 비교분석 (표 또는 항목별 장단점)
- 이유/왜/진실/현실 → 에세이/칼럼

[금지사항]
- 이모티콘, 특수문자 사용 금지
- 근거 없는 나열형 문장 금지
- 마크다운 bold(**), italic(*) 금지 (소제목 ## 만 허용)
- "안녕하세요" 같은 의례적 인사 금지

[응답 형식] 반드시 아래 JSON만 출력 (코드블록 없이):
{{"title":"제목","category":"{category}","keyword":"{keyword}","content":"본문 전체 (\\n\\n으로 문단 구분, ##소제목 포함)","summary":"2문장 핵심 요약","tags":["{keyword}","{category}","직장인","부업","경제적자유"]}}"""


# ── Gemini API 호출 ───────────────────────────────────
def generate_article(category: str, keyword: str) -> dict | None:
    prompt = build_prompt(category, keyword)
    url = (
        "https://generativelanguage.googleapis.com/v1beta/models/"
        f"gemini-2.5-flash:generateContent?key={GEMINI_API_KEY}"
    )
    payload = {
        "contents": [{"parts": [{"text": prompt}]}],
        "generationConfig": {"temperature": 0.85, "maxOutputTokens": 4096},
    }

    for attempt in range(5):
        try:
            if attempt > 0:
                wait = (attempt + 1) * 15
                print(f"   {attempt+1}번째 재시도... ({wait}초 대기)")
                time.sleep(wait)

            r = requests.post(url, headers={"Content-Type": "application/json"},
                              json=payload, timeout=60)
            data = r.json()

            if r.status_code == 503:
                print("   서버 과부하, 재시도...")
                continue
            if r.status_code != 200:
                msg = data.get("error", {}).get("message", "")
                print(f"   API 오류 ({r.status_code}): {msg}")
                continue

            text = data["candidates"][0]["content"]["parts"][0]["text"].strip()
            if not text:
                print("   빈 응답, 재시도...")
                continue

            # JSON 추출
            for marker in ["```json", "```"]:
                if marker in text:
                    text = text.split(marker)[1].split("```")[0].strip()
                    break
            start, end = text.find("{"), text.rfind("}") + 1
            if start != -1 and end > start:
                text = text[start:end]

            article = json.loads(text)
            print(f"   글자수: {len(article.get('content',''))}자")
            return article

        except json.JSONDecodeError as e:
            print(f"   JSON 파싱 오류: {e}")
        except (KeyError, IndexError):
            print("   응답 형식 오류, 재시도...")
        except Exception as e:
            print(f"   오류: {e}")

    return None


# ── 콘텐츠 정리 ──────────────────────────────────────
def clean_content(text: str) -> str:
    import re
    text = text.replace("\\n\\n", "\n\n").replace("\\n", "\n").replace("\\t", " ")
    text = re.sub(r"\*\*(.*?)\*\*", r"\1", text)   # bold 제거
    text = re.sub(r"\*(.*?)\*",   r"\1", text)      # italic 제거
    text = re.sub(r"\n{3,}", "\n\n", text)
    return text.strip()


# ── content를 HTML로 변환 ─────────────────────────────
def content_to_html(text: str, hero_image: dict | None = None) -> str:
    """
    ##소제목 → <h2>, > 포인트: → <blockquote>, 빈줄 → <p> 로 변환.
    hero_image가 있으면 첫 번째 소제목 위에 삽입.
    """
    import re
    lines   = text.strip().split("\n")
    html    = []
    img_inserted = False

    for line in lines:
        line = line.strip()
        if not line:
            continue

        # 소제목
        if line.startswith("## "):
            heading_text = line[3:].strip()
            # 이미지 삽입 (첫 번째 소제목 위)
            if hero_image and not img_inserted:
                html.append(
                    f'<figure style="margin:32px 0 24px;">'
                    f'<img src="{hero_image["url"]}" alt="{hero_image["alt"]}" '
                    f'style="width:100%;border-radius:12px;object-fit:cover;max-height:420px;">'
                    f'<figcaption style="font-size:11px;color:#888;margin-top:6px;text-align:right;">'
                    f'Photo by <a href="{hero_image["credit_link"]}" target="_blank" '
                    f'style="color:#888;">{hero_image["credit"]}</a> on Unsplash</figcaption>'
                    f'</figure>'
                )
                img_inserted = True
            html.append(f"<h2>{heading_text}</h2>")

        # 포인트 인용구
        elif line.startswith("> "):
            quote_text = line[2:].strip()
            html.append(f"<blockquote>{quote_text}</blockquote>")

        # 일반 문단
        else:
            html.append(f"<p>{line}</p>")

    # 이미지가 삽입 안 됐으면 (소제목이 없는 글) 맨 앞에 삽입
    if hero_image and not img_inserted:
        img_tag = (
            f'<figure style="margin:0 0 28px;">'
            f'<img src="{hero_image["url"]}" alt="{hero_image["alt"]}" '
            f'style="width:100%;border-radius:12px;object-fit:cover;max-height:420px;">'
            f'<figcaption style="font-size:11px;color:#888;margin-top:6px;text-align:right;">'
            f'Photo by <a href="{hero_image["credit_link"]}" target="_blank" '
            f'style="color:#888;">{hero_image["credit"]}</a> on Unsplash</figcaption>'
            f'</figure>'
        )
        html.insert(0, img_tag)

    return "\n".join(html)


# ── manifest 업데이트 ─────────────────────────────────
def update_manifest():
    posts = []
    for f in sorted(POSTS_DIR.glob("post_*.json"), reverse=True):
        try:
            data = json.loads(f.read_text(encoding="utf-8"))
            posts.append({
                "filename":   f.name,
                "title":      data.get("title", ""),
                "category":   data.get("category", ""),
                "keyword":    data.get("keyword", ""),
                "summary":    data.get("summary", ""),
                "tags":       data.get("tags", []),
                "created_at": data.get("created_at", ""),
                "status":     data.get("status", "draft"),
                "has_image":  bool(data.get("hero_image")),
            })
        except Exception as e:
            print(f"  [경고] {f.name} 파싱 오류: {e}")

    MANIFEST_PATH.write_text(
        json.dumps(posts, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    print(f"   manifest.json 업데이트: {len(posts)}개 글")
    return posts


# ── 글 저장 ──────────────────────────────────────────
def save_article(article: dict, hero_image: dict | None = None) -> str | None:
    if not article:
        return None

    POSTS_DIR.mkdir(parents=True, exist_ok=True)
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    filename  = f"post_{timestamp}.json"
    filepath  = POSTS_DIR / filename

    article["created_at"] = datetime.now().isoformat()
    article["status"]     = "published" if AUTO_PUBLISH else "draft"

    # 텍스트 정리
    raw_content = clean_content(article.get("content", ""))
    article["content_raw"] = raw_content                              # 원본 텍스트 보존
    article["content"]     = content_to_html(raw_content, hero_image) # HTML 변환
    article["summary"]     = clean_content(article.get("summary", ""))

    if hero_image:
        article["hero_image"] = hero_image

    filepath.write_text(
        json.dumps(article, ensure_ascii=False, indent=2), encoding="utf-8"
    )

    status_label = "발행" if AUTO_PUBLISH else "임시저장"
    print(f"   [{status_label}] {filename}")
    print(f"   제목: {article['title']}")
    print(f"   카테고리: {article['category']}")
    print(f"   이미지: {'있음' if hero_image else '없음 (Unsplash KEY 미설정)'}")

    update_manifest()
    return str(filepath)


# ── GitHub push ───────────────────────────────────────
def git_push(success_count: int):
    print(f"\n   GitHub 업로드 중...")
    try:
        git_dir = str(BLOG_DIR)
        subprocess.run(["git", "add", "posts/"], cwd=git_dir, check=True, capture_output=True)
        today = datetime.now().strftime("%Y-%m-%d %H:%M")
        msg   = f"자동 글 생성: {today} ({success_count}개)"
        subprocess.run(["git", "commit", "-m", msg], cwd=git_dir, check=True, capture_output=True)
        subprocess.run(["git", "push", "origin", "main"], cwd=git_dir, check=True, capture_output=True)
        print(f"   GitHub 업로드 완료! Vercel 배포 시작 (1~2분 후 반영)")
    except subprocess.CalledProcessError as e:
        stderr = e.stderr.decode("utf-8", errors="ignore") if e.stderr else ""
        if "nothing to commit" in stderr:
            print("   업로드할 새 글 없음.")
        else:
            print(f"   GitHub 업로드 실패: {stderr}")
    except Exception as e:
        print(f"   GitHub 업로드 오류: {e}")


# ── 트렌드 크롤러 (블로그 주제 필터링 적용) ──────────────
# 네이버/구글 트렌드 키워드 중 블로그 주제와 관련된 것만 사용.
# "롯데", "현도훈" 같은 연예/스포츠 키워드는 자동 차단.

BLOCKED_KEYWORDS = [
    "아이돌","배우","가수","드라마","영화","예능",
    "야구","축구","농구","배구","스포츠",
    "롯데","삼성라이온즈","두산","한화","기아","NC","KT구단","SSG",
    "선거","정치","대통령","국회","여당","야당",
    "사망","부고","사건","사고","범죄","경찰","검찰",
    "날씨","기온","강수","태풍",
]

ALLOWED_KEYWORDS = [
    "부업","수익","돈","재테크","투자","ETF","주식","적금","저축","월급","통장","절약",
    "직장인","회사원","이직","취업","연봉","승진","업무","퇴근","야근",
    "자기계발","독서","공부","자격증","어학","영어","생산성","루틴","습관",
    "블로그","유튜브","인스타","SNS","마케팅","프리랜서","온라인","디지털노마드",
    "사이드잡","N잡","부수입","파이어족","경제적자유","노후","연금","보험",
    "스마트스토어","쿠팡","위탁판매","드롭쉬핑","전자책","강의","코칭",
]

def is_relevant_keyword(keyword):
    for blocked in BLOCKED_KEYWORDS:
        if blocked in keyword:
            return False
    for allowed in ALLOWED_KEYWORDS:
        if allowed in keyword:
            return True
    return False

try:
    from trend_crawler import get_keywords_with_trends
    TREND_CRAWLER_AVAILABLE = True
    print("[INFO] 트렌드 크롤러 연동 (블로그 주제 필터 적용)")
except Exception as _e:
    TREND_CRAWLER_AVAILABLE = False

def get_keywords_for_today_with_trends():
    import random
    base = get_keywords_for_today()
    if not TREND_CRAWLER_AVAILABLE:
        return base
    try:
        base_keywords = [item["keyword"] for item in base]
        raw_trends = get_keywords_with_trends(
            base_pool=base_keywords, top_n_trend=50, max_total=100, trending_ratio=0.6,
        )
        filtered = [kw for kw in raw_trends if is_relevant_keyword(kw)]
        print(f"   [트렌드] 원본 {len(raw_trends)}개 → 필터 후 {len(filtered)}개")
        if not filtered:
            print("   [트렌드] 관련 키워드 없음 → KEYWORD_POOL 사용")
            return base
        cats = list(KEYWORD_POOL.keys())
        kw2cat = {item["keyword"]: item["category"] for item in base}
        result = []
        for kw in filtered[:POSTS_PER_DAY]:
            cat = kw2cat.get(kw, random.choice(cats))
            result.append({"category": cat, "keyword": kw})
        return result if result else base
    except Exception as _e:
        print(f"[WARN] 트렌드 병합 실패 → KEYWORD_POOL 사용: {_e}")
        return base



# ── 메인 실행 ─────────────────────────────────────────
def run_daily():
    print(f"\n{'='*52}")
    print(f"  자동 글 생성 시작: {datetime.now().strftime('%Y-%m-%d %H:%M')}")
    print(f"  AUTO_PUBLISH : {AUTO_PUBLISH}  (true=자동발행 / false=임시저장)")
    print(f"  POSTS_PER_DAY: {POSTS_PER_DAY}")
    print(f"  이미지 지원  : {'ON (Unsplash)' if UNSPLASH_KEY else 'OFF (KEY 없음)'}")
    print(f"{'='*52}")

    keywords = get_keywords_for_today_with_trends()

    success_count = 0
    for i, item in enumerate(keywords, 1):
        print(f"\n[{i}/{len(keywords)}] {item['category']} — {item['keyword']}")

        # 이미지 가져오기
        hero_image = fetch_unsplash_image(item["category"])

        # 글 생성
        article = generate_article(item["category"], item["keyword"])
        if article:
            if save_article(article, hero_image):
                success_count += 1
        else:
            print("   글 생성 실패")

        if i < len(keywords):
            print("   30초 대기...")
            time.sleep(30)

    print(f"\n{'='*52}")
    print(f"  완료: {success_count}/{len(keywords)}개 성공")
    print(f"  상태: {'자동 발행됨' if AUTO_PUBLISH else '임시저장 — 어드민에서 검토 후 발행하세요'}")
    print(f"{'='*52}")

    if success_count > 0:
        git_push(success_count)
    else:
        print("  생성된 글 없음 — GitHub 업로드 건너뜀.")

    if not AUTO_PUBLISH:
        print(f"\n  → 어드민 확인: https://koreansalaryman.com/admin.html")
    print()


def run_scheduler():
    try:
        import schedule
    except ImportError:
        subprocess.run(["pip", "install", "schedule"], check=True)
        import schedule

    print(f"  스케줄러 시작 — 매일 09:00 KST 자동 실행")
    schedule.every().day.at("09:00").do(run_daily)
    print(f"  다음 실행: {schedule.next_run()}\n")
    while True:
        schedule.run_pending()
        time.sleep(30)


if __name__ == "__main__":
    import sys
    if len(sys.argv) > 1 and sys.argv[1] == "--schedule":
        run_scheduler()
    else:
        run_daily()
