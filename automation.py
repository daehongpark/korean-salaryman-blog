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
GEMINI_API_KEY = os.getenv("GEMINI_API_KEY")
BLOG_TITLE = os.getenv("BLOG_TITLE", "직장인 수익일기")
AUTO_PUBLISH = os.getenv("AUTO_PUBLISH", "false").lower() == "true"
POSTS_PER_DAY = int(os.getenv("POSTS_PER_DAY", "3"))

# ── 경로 설정 ─────────────────────────────────────────
SCRIPT_DIR = Path(__file__).parent
BLOG_DIR = SCRIPT_DIR.parent / "korean-salaryman-blog"
POSTS_DIR = BLOG_DIR / "posts"
MANIFEST_PATH = POSTS_DIR / "manifest.json"

KEYWORD_POOL = {
    "부업 방법": [
        "직장인 부업 추천", "퇴근 후 할 수 있는 부업", "재택 부업 방법",
        "월급 외 수입 만들기", "직장인 N잡 방법", "부업으로 월 100만원 버는 법",
        "스마트스토어 부업", "쿠팡파트너스 부업", "직장인 온라인 부업",
        "부업 시작하는 법 초보", "투잡 추천 직장인", "부업 종류 비교"
    ],
    "블로그": [
        "에드센스 수익 공개", "블로그로 돈 버는 법", "구글 에드센스 승인 방법",
        "티스토리 vs 워드프레스", "블로그 SEO 최적화", "블로그 글쓰기 팁",
        "에드센스 클릭단가 높이는 법", "블로그 방문자 늘리는 법",
        "키워드 찾는 방법", "블로그 수익화 방법", "구글 검색 상위노출"
    ],
    "자기계발": [
        "직장인 자기계발 방법", "아침 루틴 만들기", "독서 습관 기르는 법",
        "시간 관리 방법 직장인", "목표 설정하는 법", "생산성 높이는 방법",
        "직장인 스터디 방법", "자기계발 앱 추천", "성공하는 사람들의 습관",
        "직장인 영어공부 방법", "퇴근 후 자기계발"
    ],
    "재테크": [
        "직장인 재테크 방법", "월급 관리하는 법", "적금 vs 주식",
        "직장인 투자 시작하기", "ETF 투자 방법", "청약저축 활용법",
        "월급 300만원 재테크", "비상금 만들기", "소비 줄이는 방법",
        "경제적 자유 달성 방법", "파이어족 되는 법"
    ],
    "책 추천": [
        "직장인 추천 도서", "재테크 책 추천", "자기계발 책 추천",
        "부업 관련 책 추천", "경제적 자유 책 추천", "투자 책 초보",
        "동기부여 책 추천", "성공한 사람들이 읽은 책", "직장인 필독서"
    ],
    "수익 공개": [
        "블로그 수익 공개", "에드센스 월수익", "부업 수익 후기",
        "직장인 N잡 수익", "스마트스토어 수익 공개",
        "부업 6개월 후기", "블로그 1년 수익"
    ]
}


def get_keywords_for_today():
    import random
    selected = []
    categories = list(KEYWORD_POOL.keys())
    for i in range(POSTS_PER_DAY):
        category = categories[i % len(categories)]
        keyword = random.choice(KEYWORD_POOL[category])
        selected.append({"category": category, "keyword": keyword})
    return selected


def build_prompt(category, keyword):
    return (
        "당신은 직장인 블로그 전문 작가입니다.\n"
        f"블로그명: {BLOG_TITLE}\n"
        f"독자: 20-40대 대한민국 직장인\n"
        f"카테고리: {category}\n"
        f"핵심 키워드: {keyword}\n\n"
        "[가장 중요한 원칙]\n"
        "키워드와 주제를 먼저 분석하고, 그 주제에 가장 어울리는 글 형식을 스스로 선택하세요.\n"
        "모든 글이 같은 구조일 필요 없습니다. 주제에 따라 형식이 달라야 합니다.\n\n"
        "[글 형식 선택 기준]\n"
        "- 후기/경험 키워드 (후기, 공개, 달성, 해봤더니) -> 스토리텔링 형식\n"
        "- 방법/가이드 키워드 (방법, 하는법, 시작하기, 단계) -> 실용 가이드 형식\n"
        "- 비교/추천 키워드 (추천, 비교, vs) -> 비교분석 형식\n"
        "- 정보/칼럼 키워드 (이유, 왜, 알아야, 진실) -> 에세이/칼럼 형식\n"
        "- 수익/결과 키워드 (수익, 월급, 만원, 얼마) -> 데이터 중심 형식\n\n"
        "[모든 글에 반드시 포함할 요소]\n"
        "1. 첫 문장: 독자가 끝까지 읽어야 하는 이유를 담은 강력한 후킹\n"
        "2. 직장인이라면 공감할 현실적인 상황이나 고민\n"
        "3. 정보 제시 시 반드시 근거나 이유 포함 (나열 금지)\n"
        "4. 친근하지만 전문성 있는 말투\n"
        "5. 따뜻하고 힘이 되는 마무리\n\n"
        "[글쓰기 규칙]\n"
        "- 1800자 내외\n"
        "- 절대 금지: 특수문자, 이모티콘\n"
        "- 절대 금지: 근거 없는 나열형 문장\n"
        "- 가독성을 위해 문단 구분 명확히\n\n"
        "[응답 형식]\n"
        "반드시 아래 JSON 형식으로만 응답하세요:\n"
        '{"title": "제목", '
        f'"category": "{category}", '
        f'"keyword": "{keyword}", '
        '"content": "본문 전체", '
        '"summary": "핵심 요약 2문장", '
        f'"tags": ["{keyword}", "{category}", "직장인", "부업", "경제적자유"]}}'
    )


def generate_article(category, keyword):
    prompt = build_prompt(category, keyword)
    url = (
        "https://generativelanguage.googleapis.com/v1beta/models/"
        f"gemini-2.5-flash:generateContent?key={GEMINI_API_KEY}"
    )
    headers = {"Content-Type": "application/json"}
    data = {
        "contents": [{"parts": [{"text": prompt}]}],
        "generationConfig": {
            "temperature": 0.9,
            "maxOutputTokens": 4000
        }
    }

    for attempt in range(5):
        try:
            if attempt > 0:
                wait = (attempt + 1) * 15
                print(f"   {attempt+1}번째 재시도 중... ({wait}초 대기)")
                time.sleep(wait)

            response = requests.post(url, headers=headers, json=data)
            result = response.json()

            if response.status_code == 503:
                print("   서버 과부하, 잠시 후 재시도...")
                continue

            if response.status_code != 200:
                msg = result.get("error", {}).get("message", "")
                print(f"   API 오류 ({response.status_code}): {msg}")
                continue

            text = result["candidates"][0]["content"]["parts"][0]["text"].strip()

            if not text:
                print("   빈 응답, 재시도...")
                continue

            if "```json" in text:
                text = text.split("```json")[1].split("```")[0].strip()
            elif "```" in text:
                text = text.split("```")[1].split("```")[0].strip()

            start = text.find("{")
            end = text.rfind("}") + 1
            if start != -1 and end > start:
                text = text[start:end]

            article = json.loads(text)
            print(f"   글자수: {len(article.get('content', ''))}자")
            return article

        except json.JSONDecodeError as e:
            print(f"   JSON 파싱 오류: {e}")
        except KeyError:
            print("   응답 형식 오류, 재시도...")
        except Exception as e:
            print(f"   오류: {e}")

    return None


def clean_content(text):
    """특수문자 정리"""
    import re
    text = text.replace('\\n\\n', '\n\n')
    text = text.replace('\\n', '\n')
    text = text.replace('\\t', ' ')
    text = re.sub(r'#{1,6}\s*', '', text)
    text = re.sub(r'\*\*(.*?)\*\*', r'\1', text)
    text = re.sub(r'\*(.*?)\*', r'\1', text)
    text = re.sub(r'\n{3,}', '\n\n', text)
    text = text.strip()
    return text


def update_manifest():
    """manifest.json 업데이트"""
    posts = []
    for f in sorted(POSTS_DIR.glob("post_*.json"), reverse=True):
        try:
            data = json.loads(f.read_text(encoding="utf-8"))
            posts.append({
                "filename": f.name,
                "title": data.get("title", ""),
                "category": data.get("category", ""),
                "keyword": data.get("keyword", ""),
                "summary": data.get("summary", ""),
                "tags": data.get("tags", []),
                "created_at": data.get("created_at", ""),
                "status": data.get("status", "draft"),
            })
        except Exception as e:
            print(f"  [경고] {f.name} 파싱 오류: {e}")

    MANIFEST_PATH.write_text(
        json.dumps(posts, ensure_ascii=False, indent=2),
        encoding="utf-8"
    )
    print(f"   manifest.json 업데이트: {len(posts)}개 글")
    return posts


def save_article(article):
    if not article:
        return None

    POSTS_DIR.mkdir(parents=True, exist_ok=True)
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    filename = f"post_{timestamp}.json"
    filepath = POSTS_DIR / filename

    article["created_at"] = datetime.now().isoformat()

    if AUTO_PUBLISH:
        article["status"] = "published"
        print(f"   상태: 자동 발행 (AUTO_PUBLISH=true)")
    else:
        article["status"] = "draft"
        print(f"   상태: 임시저장 (AUTO_PUBLISH=false)")

    if "content" in article:
        article["content"] = clean_content(article["content"])
    if "summary" in article:
        article["summary"] = clean_content(article["summary"])

    filepath.write_text(
        json.dumps(article, ensure_ascii=False, indent=2),
        encoding="utf-8"
    )
    print(f"   저장완료: posts/{filename}")
    print(f"   제목: {article['title']}")
    print(f"   카테고리: {article['category']}")

    update_manifest()

    return str(filepath)


# ── GitHub 자동 push ──────────────────────────────────
def git_push(success_count):
    """생성된 글을 GitHub에 자동으로 업로드"""
    print(f"\n   GitHub 업로드 중...")
    try:
        # blog 폴더에서 git 명령어 실행
        git_dir = str(BLOG_DIR)

        # 변경사항 추가
        subprocess.run(
            ["git", "add", "posts/"],
            cwd=git_dir, check=True, capture_output=True
        )

        # 커밋
        today = datetime.now().strftime("%Y-%m-%d %H:%M")
        msg = f"자동 글 생성: {today} ({success_count}개)"
        subprocess.run(
            ["git", "commit", "-m", msg],
            cwd=git_dir, check=True, capture_output=True
        )

        # push
        subprocess.run(
            ["git", "push", "origin", "main"],
            cwd=git_dir, check=True, capture_output=True
        )

        print(f"   GitHub 업로드 완료!")
        print(f"   Vercel 자동 배포 시작 (1~2분 후 반영)")

    except subprocess.CalledProcessError as e:
        stderr = e.stderr.decode("utf-8", errors="ignore") if e.stderr else ""
        if "nothing to commit" in stderr or "nothing added" in stderr:
            print(f"   업로드할 새 글이 없습니다.")
        else:
            print(f"   GitHub 업로드 실패: {stderr}")
    except Exception as e:
        print(f"   GitHub 업로드 오류: {e}")


def run_daily():
    print(f"\n{'='*52}")
    print(f"  자동 글 생성 시작: {datetime.now().strftime('%Y-%m-%d %H:%M')}")
    print(f"  AUTO_PUBLISH: {AUTO_PUBLISH}")
    print(f"  글 저장 위치: {POSTS_DIR}")
    print(f"{'='*52}")

    keywords = get_keywords_for_today()

    success_count = 0
    for i, item in enumerate(keywords, 1):
        print(f"\n[{i}/{len(keywords)}] 글 생성 중...")
        print(f"   카테고리: {item['category']}")
        print(f"   키워드: {item['keyword']}")
        article = generate_article(item["category"], item["keyword"])
        if article:
            result = save_article(article)
            if result:
                success_count += 1
        else:
            print("   글 생성 실패")

        if i < len(keywords):
            print("   다음 글 생성까지 30초 대기...")
            time.sleep(30)

    print(f"\n{'='*52}")
    print(f"  글 생성 완료! ({success_count}/{len(keywords)}개 성공)")
    print(f"{'='*52}")

    # 글이 1개 이상 성공하면 GitHub에 자동 업로드
    if success_count > 0:
        git_push(success_count)
    else:
        print(f"\n  생성된 글이 없어 GitHub 업로드를 건너뜁니다.")

    print(f"\n{'='*52}")
    if not AUTO_PUBLISH:
        print(f"  어드민 페이지에서 글을 검토 후 발행해주세요.")
        print(f"  → https://koreansalaryman.com/admin.html")
    print(f"{'='*52}\n")


def run_scheduler():
    """매일 오전 9시에 자동 실행하는 스케줄러"""
    try:
        import schedule
    except ImportError:
        print("schedule 패키지 설치 중...")
        subprocess.run(["pip", "install", "schedule"], check=True)
        import schedule

    print(f"\n{'='*52}")
    print(f"  스케줄러 시작 — 매일 오전 09:00 자동 실행")
    print(f"  현재 시각: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print(f"  Ctrl+C 로 종료")
    print(f"{'='*52}\n")

    schedule.every().day.at("09:00").do(run_daily)

    # 시작하자마자 한 번 실행할지 여부
    next_run = schedule.next_run()
    print(f"  다음 실행 예정: {next_run.strftime('%Y-%m-%d %H:%M:%S')}\n")

    while True:
        schedule.run_pending()
        time.sleep(30)


if __name__ == "__main__":
    import sys

    if len(sys.argv) > 1 and sys.argv[1] == "--schedule":
        # 스케줄러 모드: python automation.py --schedule
        run_scheduler()
    else:
        # 즉시 실행 모드: python automation.py
        run_daily()
