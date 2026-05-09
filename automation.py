import os
import io
import json
import time
import base64
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
SCRIPT_DIR      = Path(__file__).parent
BLOG_DIR        = SCRIPT_DIR.parent / "korean-salaryman-blog"
POSTS_DIR       = BLOG_DIR / "posts"
THUMBNAILS_DIR  = POSTS_DIR / "thumbnails"
MANIFEST_PATH   = POSTS_DIR / "manifest.json"

# ── 디자인 시스템 색상 (블로그와 동일) ──────────────────
COLOR_NAVY     = (26, 38, 64)      # #1a2640 - 메인 다크
COLOR_POINT    = (193, 127, 62)    # #c17f3e - 골드
COLOR_WHITE    = (255, 255, 255)
COLOR_BG       = (248, 247, 244)   # #f8f7f4 - 배경

# ── 키워드 풀 (2026 통일 7개 카테고리 - keyword_pool_v2 모듈) ──
try:
    from keyword_pool_v2 import (
        KEYWORD_POOL_V2     as KEYWORD_POOL,
        UNSPLASH_QUERY_V2   as UNSPLASH_QUERY,
        UNSPLASH_BODY_QUERIES_V2 as UNSPLASH_BODY_QUERIES,
        CATEGORY_BALANCE,
        CATEGORY_INTENTS,
        LEGACY_CATEGORY_MAP,
    )
    print("[INFO] keyword_pool_v2 로드 완료 (7개 통일 카테고리)")
except ImportError as _e:
    print(f"[WARN] keyword_pool_v2 로드 실패 → 비상용 폴백 사용: {_e}")
    KEYWORD_POOL = {
        "finance": ["직장인 ETF 투자", "ISA 계좌 비교", "고금리 적금 추천"],
        "money":   ["청년도약계좌 가입조건", "근로장려금 신청자격"],
    }
    UNSPLASH_QUERY = {"finance": "money investment", "money": "korean government policy"}
    UNSPLASH_BODY_QUERIES = {k: [v] for k, v in UNSPLASH_QUERY.items()}
    CATEGORY_BALANCE = {k: 1.0 / len(KEYWORD_POOL) for k in KEYWORD_POOL}
    CATEGORY_INTENTS = {}
    LEGACY_CATEGORY_MAP = {}


# ── 카테고리 정규화 (한글 키 / 미지의 키 → 영문 7개 키로 매핑) ──
VALID_CATEGORIES = {"money", "ai", "startup", "finance", "realestate", "trending", "book"}
FALLBACK_CATEGORY = "trending"  # 알 수 없는 카테고리 도착 시 보낼 곳


def normalize_category(cat: str) -> str:
    """7개 영문 키 외의 값이 들어오면 LEGACY_CATEGORY_MAP으로 변환, 그래도 안 잡히면 fallback."""
    if not cat:
        return FALLBACK_CATEGORY
    if cat in VALID_CATEGORIES:
        return cat
    mapped = LEGACY_CATEGORY_MAP.get(cat)
    if mapped in VALID_CATEGORIES:
        return mapped
    print(f"[WARN] 알 수 없는 카테고리 '{cat}' → '{FALLBACK_CATEGORY}'로 fallback")
    return FALLBACK_CATEGORY


# ── 카테고리 가중 랜덤 선택 (균형 발행) ───────────────
def _pick_balanced_categories(n: int) -> list:
    """
    CATEGORY_BALANCE 비율을 가중치로 카테고리 n개 선택.
    같은 카테고리가 연속해서 너무 많이 뽑히지 않도록 후처리.
    """
    import random
    cats    = list(KEYWORD_POOL.keys())
    weights = [CATEGORY_BALANCE.get(c, 1.0 / len(cats)) for c in cats]

    picked  = []
    used_count = {c: 0 for c in cats}
    for _ in range(n):
        # 이미 많이 뽑힌 카테고리는 가중치 절감
        adjusted = [
            weights[i] * (0.4 if used_count[cats[i]] >= 2 else 1.0)
            for i in range(len(cats))
        ]
        cat = random.choices(cats, weights=adjusted, k=1)[0]
        picked.append(cat)
        used_count[cat] += 1
    return picked


# ── 오늘의 키워드 선택 (기본 - SEO 미적용 폴백) ──────────
def get_keywords_for_today():
    """가중치 기반 랜덤 카테고리 선택 + 시드 키워드 랜덤 픽 (폴백용)"""
    import random
    selected = []
    for cat in _pick_balanced_categories(POSTS_PER_DAY):
        seeds = KEYWORD_POOL.get(cat, [])
        if not seeds:
            continue
        selected.append({"category": cat, "keyword": random.choice(seeds)})
    return selected


# ── SEO 최적화 키워드 선택 (NEW) ──────────────────────
def get_seo_optimized_keywords():
    """
    각 카테고리 내에서 SEO 점수 최상위 키워드를 선택.
    
    작동 방식:
    1. POSTS_PER_DAY 수만큼 카테고리를 순환 선택
    2. 각 카테고리의 KEYWORD_POOL을 시드로 trend_crawler에 전달
    3. 시드에서 자동완성/연관 키워드로 확장 → 월 검색량 조회
    4. SEO 점수 계산 → 최상위 키워드 반환
    5. 실패 시 기존 get_keywords_for_today() 사용
    
    반환: [{"category": "...", "keyword": "...", "seo_meta": {...}}, ...]
    """
    import random
    
    try:
        from trend_crawler import get_seo_scored_keywords
    except ImportError:
        print("   [SEO] trend_crawler 모듈 로드 실패 → 기본 모드 사용")
        return get_keywords_for_today()

    # 정부지원금 카테고리는 policy_crawler 통합 함수 사용 (실시간 정책 키워드 보강)
    try:
        from trend_crawler import get_policy_seo_keywords
    except ImportError:
        get_policy_seo_keywords = None

    # 카테고리는 균형 발행 비율로 선택
    picked_cats   = _pick_balanced_categories(POSTS_PER_DAY)
    selected      = []
    used_keywords = set()  # 중복 방지

    print(f"\n   [SEO 분석] 카테고리 분배: {picked_cats}")

    for cat in picked_cats:
        seed_pool = KEYWORD_POOL.get(cat, [])
        if not seed_pool:
            continue

        # 시드는 카테고리당 3~5개 랜덤 선택 (너무 많으면 API 호출 과다)
        seeds = random.sample(seed_pool, min(4, len(seed_pool)))
        print(f"\n   ▶ [{cat}] 시드: {seeds}")

        try:
            # 정부지원금은 policy_crawler 통합 함수 사용
            if cat == "정부지원금" and get_policy_seo_keywords is not None:
                scored = get_policy_seo_keywords(
                    base_seeds=seeds,
                    top_n=10,
                    max_seeds=25,
                )
            else:
                scored = get_seo_scored_keywords(
                    seed_keywords=seeds,
                    category_hint=cat,
                    top_n=10,
                    check_competition=False,
                )
            
            # 이미 선택된 키워드는 제외
            available = [s for s in scored if s["keyword"] not in used_keywords]
            
            if available:
                top = available[0]
                used_keywords.add(top["keyword"])
                selected.append({
                    "category": cat,
                    "keyword":  top["keyword"],
                    "seo_meta": {
                        "score":         top["score"],
                        "monthly_total": top.get("monthly_total"),
                        "competition":   top.get("competition"),
                    },
                })
                print(f"   ✓ 선택: {top['keyword']} (SEO {top['score']}점)")
            else:
                # SEO 분석 결과 없음 → 랜덤 폴백
                kw = random.choice(seed_pool)
                selected.append({"category": cat, "keyword": kw})
                print(f"   ⚠ SEO 결과 없음 → 폴백: {kw}")
                
        except Exception as e:
            print(f"   ⚠ SEO 분석 오류: {e} → 폴백")
            kw = random.choice(seed_pool)
            selected.append({"category": cat, "keyword": kw})
    
    return selected


# ═══════════════════════════════════════════════════════
#  썸네일 생성 시스템 (NEW)
# ═══════════════════════════════════════════════════════

def _ensure_pillow():
    """Pillow 라이브러리가 없으면 자동 설치."""
    try:
        from PIL import Image  # noqa: F401
        return True
    except ImportError:
        print("   [Pillow] 라이브러리 설치 중...")
        try:
            subprocess.run(
                ["pip", "install", "Pillow", "--quiet"],
                check=True, capture_output=True
            )
            from PIL import Image  # noqa: F401
            return True
        except Exception as e:
            print(f"   [Pillow] 설치 실패: {e}")
            return False


def _find_korean_font():
    """시스템에서 한글 폰트를 찾아 경로를 반환."""
    # Windows, Linux, Mac 순서대로 탐색
    candidates = [
        # Windows
        "C:/Windows/Fonts/malgun.ttf",       # 맑은 고딕
        "C:/Windows/Fonts/malgunbd.ttf",     # 맑은 고딕 Bold
        "C:/Windows/Fonts/NanumGothic.ttf",  # 나눔고딕
        "C:/Windows/Fonts/NanumGothicBold.ttf",
        "C:/Windows/Fonts/gulim.ttc",        # 굴림
        # Linux
        "/usr/share/fonts/truetype/nanum/NanumGothic.ttf",
        "/usr/share/fonts/truetype/nanum/NanumGothicBold.ttf",
        "/usr/share/fonts/opentype/noto/NotoSansCJK-Bold.ttc",
        "/usr/share/fonts/opentype/noto/NotoSansCJK-Regular.ttc",
        # Mac
        "/System/Library/Fonts/AppleSDGothicNeo.ttc",
        "/Library/Fonts/AppleGothic.ttf",
    ]
    for path in candidates:
        if Path(path).exists():
            return path
    return None


def _download_unsplash_image(category: str):
    """Unsplash에서 이미지를 다운로드해 PIL Image로 반환."""
    if not UNSPLASH_KEY:
        return None, None

    query = UNSPLASH_QUERY.get(category, "work office")
    try:
        # 1단계: 이미지 메타데이터 요청
        r = requests.get(
            "https://api.unsplash.com/photos/random",
            params={"query": query, "orientation": "landscape", "content_filter": "high"},
            headers={"Authorization": f"Client-ID {UNSPLASH_KEY}"},
            timeout=10,
        )
        if r.status_code != 200:
            print(f"   [Unsplash] API 응답 실패: {r.status_code}")
            return None, None

        data = r.json()
        credit_info = {
            "credit":      data["user"]["name"],
            "credit_link": data["user"]["links"]["html"],
            "source":      "unsplash",
        }

        # 2단계: 실제 이미지 다운로드
        img_url = data["urls"]["regular"]
        img_response = requests.get(img_url, timeout=15)
        if img_response.status_code != 200:
            return None, None

        from PIL import Image
        img = Image.open(io.BytesIO(img_response.content)).convert("RGB")
        print(f"   [Unsplash] 이미지 다운로드 성공 ({img.size[0]}×{img.size[1]})")
        return img, credit_info

    except Exception as e:
        print(f"   [Unsplash] 이미지 가져오기 실패: {e}")
        return None, None


def _generate_gemini_image(category: str, keyword: str):
    """Gemini 이미지 생성 API로 이미지를 생성 (Unsplash 폴백)."""
    if not GEMINI_API_KEY:
        return None, None

    # Gemini 2.5 Flash Image Preview 모델 사용
    prompt = (
        f"A clean, modern minimalist illustration representing the concept of "
        f"'{keyword}' in the context of {category}. "
        f"Professional business/finance aesthetic, warm golden and navy blue tones, "
        f"16:9 aspect ratio, no text or letters in the image, "
        f"soft lighting, abstract composition suitable for a blog thumbnail background."
    )

    url = (
        "https://generativelanguage.googleapis.com/v1beta/models/"
        f"gemini-2.5-flash-image-preview:generateContent?key={GEMINI_API_KEY}"
    )
    payload = {
        "contents": [{"parts": [{"text": prompt}]}],
        "generationConfig": {"responseModalities": ["IMAGE"]},
    }

    try:
        r = requests.post(url, json=payload, timeout=60)
        if r.status_code != 200:
            print(f"   [Gemini 이미지] API 응답 실패: {r.status_code}")
            return None, None

        data = r.json()
        parts = data.get("candidates", [{}])[0].get("content", {}).get("parts", [])
        for part in parts:
            inline_data = part.get("inlineData") or part.get("inline_data")
            if inline_data and inline_data.get("data"):
                img_bytes = base64.b64decode(inline_data["data"])
                from PIL import Image
                img = Image.open(io.BytesIO(img_bytes)).convert("RGB")
                print(f"   [Gemini 이미지] 생성 성공 ({img.size[0]}×{img.size[1]})")
                return img, {"credit": "AI Generated", "credit_link": "", "source": "gemini"}

        print("   [Gemini 이미지] 응답에 이미지 없음")
        return None, None

    except Exception as e:
        print(f"   [Gemini 이미지] 생성 실패: {e}")
        return None, None


def _create_gradient_background(width: int, height: int):
    """이미지가 없을 때 사용할 네이비 그라데이션 배경 생성."""
    from PIL import Image
    img = Image.new("RGB", (width, height), COLOR_NAVY)
    pixels = img.load()
    # 대각선 그라데이션: 좌상단(진한 네이비) → 우하단(약간 밝은 네이비)
    for y in range(height):
        for x in range(width):
            ratio = (x + y) / (width + height)
            r = int(COLOR_NAVY[0] + (45 - COLOR_NAVY[0]) * ratio)
            g = int(COLOR_NAVY[1] + (58 - COLOR_NAVY[1]) * ratio)
            b = int(COLOR_NAVY[2] + (90 - COLOR_NAVY[2]) * ratio)
            pixels[x, y] = (r, g, b)
    return img


def _wrap_korean_text(text: str, font, max_width: int) -> list:
    """
    한글 텍스트를 이미지 폭에 맞춰 자동 줄바꿈.
    - 1차: 공백(어절) 단위로 줄바꿈 시도
    - 2차: 한 어절이 폭을 넘으면 글자 단위로 분할
    """
    from PIL import ImageDraw, Image as PILImage
    dummy = PILImage.new("RGB", (10, 10))
    draw = ImageDraw.Draw(dummy)

    def text_width(s: str) -> int:
        bbox = draw.textbbox((0, 0), s, font=font)
        return bbox[2] - bbox[0]

    words = text.split(" ")
    lines = []
    current = ""

    for word in words:
        # 단어 자체가 최대 폭을 초과하는 경우 → 글자 단위 분할
        if text_width(word) > max_width:
            if current:
                lines.append(current)
                current = ""
            # 긴 단어를 글자 단위로 쪼갬
            temp = ""
            for ch in word:
                if text_width(temp + ch) <= max_width:
                    temp += ch
                else:
                    lines.append(temp)
                    temp = ch
            current = temp
            continue

        # 기존 라인 + 새 단어가 폭에 들어가는지 확인
        candidate = word if not current else f"{current} {word}"
        if text_width(candidate) <= max_width:
            current = candidate
        else:
            lines.append(current)
            current = word

    if current:
        lines.append(current)

    return lines


def _compose_thumbnail(base_img, title: str, category: str) -> "Image.Image":
    """
    기본 이미지 위에 텍스트 오버레이를 합성해 1200×630 썸네일 생성.
    - 상단: 카테고리 뱃지 (골드)
    - 중앙: 제목 (한글 자동 줄바꿈)
    - 하단: 사이트명 (워터마크)
    """
    from PIL import Image, ImageDraw, ImageFilter

    W, H = 1200, 630

    # 기본 이미지를 1200×630에 맞춰 crop/resize (cover 방식)
    if base_img is not None:
        bw, bh = base_img.size
        scale = max(W / bw, H / bh)
        new_size = (int(bw * scale), int(bh * scale))
        base_img = base_img.resize(new_size, Image.LANCZOS)
        # 중앙 crop
        left = (new_size[0] - W) // 2
        top  = (new_size[1] - H) // 2
        base_img = base_img.crop((left, top, left + W, top + H))
        # 약간 블러로 텍스트 가독성 확보
        base_img = base_img.filter(ImageFilter.GaussianBlur(radius=2))
    else:
        base_img = _create_gradient_background(W, H)

    # 다크 오버레이 레이어 (가독성)
    overlay = Image.new("RGBA", (W, H), (COLOR_NAVY[0], COLOR_NAVY[1], COLOR_NAVY[2], 170))
    canvas = base_img.convert("RGBA")
    canvas = Image.alpha_composite(canvas, overlay)

    draw = ImageDraw.Draw(canvas)

    # 폰트 로드
    font_path = _find_korean_font()
    if not font_path:
        print("   [경고] 한글 폰트를 찾을 수 없음 → 기본 폰트 사용 (한글 깨질 수 있음)")
        from PIL import ImageFont
        title_font    = ImageFont.load_default()
        category_font = ImageFont.load_default()
        watermark_font = ImageFont.load_default()
    else:
        from PIL import ImageFont
        title_font     = ImageFont.truetype(font_path, 64)
        category_font  = ImageFont.truetype(font_path, 24)
        watermark_font = ImageFont.truetype(font_path, 22)

    # ── 1. 카테고리 뱃지 (상단 왼쪽) ──
    cat_text = f"# {category}"
    cat_bbox = draw.textbbox((0, 0), cat_text, font=category_font)
    cat_w    = cat_bbox[2] - cat_bbox[0]
    cat_h    = cat_bbox[3] - cat_bbox[1]
    padding  = 14
    badge_x, badge_y = 60, 60
    # 뱃지 배경 (골드)
    draw.rounded_rectangle(
        [badge_x, badge_y, badge_x + cat_w + padding * 2, badge_y + cat_h + padding * 2],
        radius=6,
        fill=COLOR_POINT,
    )
    draw.text(
        (badge_x + padding, badge_y + padding - 2),
        cat_text,
        font=category_font,
        fill=COLOR_WHITE,
    )

    # ── 2. 제목 (중앙) ──
    max_title_width = W - 120  # 좌우 여백 60px씩
    lines = _wrap_korean_text(title, title_font, max_title_width)

    # 최대 3줄로 제한, 초과 시 말줄임표
    if len(lines) > 3:
        lines = lines[:3]
        last = lines[-1]
        while len(last) > 1:
            bbox = draw.textbbox((0, 0), last + "...", font=title_font)
            if bbox[2] - bbox[0] <= max_title_width:
                break
            last = last[:-1]
        lines[-1] = last + "..."

    # 총 높이 계산해서 수직 중앙 정렬
    line_height = 82
    total_height = len(lines) * line_height
    start_y = (H - total_height) // 2

    for i, line in enumerate(lines):
        bbox = draw.textbbox((0, 0), line, font=title_font)
        line_w = bbox[2] - bbox[0]
        x = (W - line_w) // 2
        y = start_y + i * line_height
        # 텍스트 그림자 (가독성 강화)
        draw.text((x + 2, y + 2), line, font=title_font, fill=(0, 0, 0, 120))
        draw.text((x, y), line, font=title_font, fill=COLOR_WHITE)

    # ── 3. 하단 구분선 + 워터마크 ──
    # 골드 포인트 라인
    line_y = H - 70
    draw.line([(60, line_y), (120, line_y)], fill=COLOR_POINT, width=3)

    # 사이트명
    watermark = BLOG_TITLE
    wm_bbox = draw.textbbox((0, 0), watermark, font=watermark_font)
    draw.text(
        (60, line_y + 12),
        watermark,
        font=watermark_font,
        fill=COLOR_WHITE,
    )

    # 도메인 (오른쪽)
    domain = "koreansalaryman.com"
    dm_bbox = draw.textbbox((0, 0), domain, font=watermark_font)
    dm_w    = dm_bbox[2] - dm_bbox[0]
    draw.text(
        (W - 60 - dm_w, line_y + 12),
        domain,
        font=watermark_font,
        fill=(255, 255, 255, 180),
    )

    return canvas.convert("RGB")


def get_hero_image(category: str, keyword: str, title: str) -> dict | None:
    """
    썸네일 이미지를 생성/저장하고 메타데이터를 반환합니다.
    1) Unsplash 시도 → 2) Gemini 이미지 생성 폴백 → 3) 그라데이션 배경
    
    반환값:
    {
        "url":         "/posts/thumbnails/thumb_20260424_153000.png",
        "alt":         "글 제목",
        "credit":      "Unsplash 크레딧" 또는 "AI Generated",
        "credit_link": "크레딧 링크",
        "source":      "unsplash" | "gemini" | "gradient",
    }
    """
    if not _ensure_pillow():
        print("   [썸네일] Pillow 설치 실패 → 이미지 생성 건너뜀")
        return None

    # 저장 폴더 확보
    THUMBNAILS_DIR.mkdir(parents=True, exist_ok=True)

    # 1. Unsplash 시도
    base_img, credit_info = _download_unsplash_image(category)

    # 2. Unsplash 실패 시 Gemini 이미지 생성 폴백
    if base_img is None:
        print("   [썸네일] Unsplash 실패 → Gemini 이미지 생성 시도")
        base_img, credit_info = _generate_gemini_image(category, keyword)

    # 3. 둘 다 실패 시 그라데이션 배경
    if base_img is None:
        print("   [썸네일] 이미지 생성 실패 → 그라데이션 배경 사용")
        credit_info = {"credit": BLOG_TITLE, "credit_link": "", "source": "gradient"}

    # 텍스트 오버레이 합성
    try:
        final_img = _compose_thumbnail(base_img, title, category)
    except Exception as e:
        print(f"   [썸네일] 합성 실패: {e}")
        return None

    # 저장
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    filename  = f"thumb_{timestamp}.png"
    filepath  = THUMBNAILS_DIR / filename

    try:
        final_img.save(filepath, "PNG", optimize=True)
        print(f"   [썸네일] 저장 완료: {filename} (소스: {credit_info['source']})")
    except Exception as e:
        print(f"   [썸네일] 저장 실패: {e}")
        return None

    # 웹 경로로 반환 (절대 경로 아님)
    return {
        "url":         f"/posts/thumbnails/{filename}",
        "alt":         title,
        "credit":      credit_info.get("credit", ""),
        "credit_link": credit_info.get("credit_link", ""),
        "source":      credit_info.get("source", ""),
    }


# ═══════════════════════════════════════════════════════
#  본문 이미지 시스템 (NEW)
# ═══════════════════════════════════════════════════════

def _fetch_unsplash_url(query: str) -> dict | None:
    """
    Unsplash에서 이미지 URL만 가져옴 (다운로드 X, 오버레이 X).
    본문 이미지용 - CDN URL을 그대로 사용해서 서버 부하 0.
    """
    if not UNSPLASH_KEY:
        return None
    try:
        r = requests.get(
            "https://api.unsplash.com/photos/random",
            params={"query": query, "orientation": "landscape", "content_filter": "high"},
            headers={"Authorization": f"Client-ID {UNSPLASH_KEY}"},
            timeout=10,
        )
        if r.status_code != 200:
            return None
        data = r.json()
        return {
            "url":         data["urls"]["regular"],
            "alt":         data.get("alt_description") or query,
            "credit":      data["user"]["name"],
            "credit_link": data["user"]["links"]["html"],
            "source":      "unsplash",
        }
    except Exception as e:
        print(f"   [본문이미지] 가져오기 실패 ({query}): {e}")
        return None


def get_body_images(category: str, count: int = 3) -> list:
    """
    본문에 삽입할 이미지 URL 리스트를 반환.
    카테고리별 다양한 쿼리를 셔플해서 중복 이미지 방지.
    실패한 슬롯은 None으로 채움 → content_to_html에서 스킵.
    """
    import random

    if count <= 0 or not UNSPLASH_KEY:
        return []

    queries = UNSPLASH_BODY_QUERIES.get(category, ["work office business"])
    # 셔플해서 다양한 쿼리 사용
    shuffled = random.sample(queries, min(len(queries), count))
    # count가 쿼리 수보다 많으면 반복해서 채움
    while len(shuffled) < count:
        shuffled.append(random.choice(queries))

    results = []
    for q in shuffled:
        img = _fetch_unsplash_url(q)
        if img:
            results.append(img)
            print(f"   [본문이미지] OK: {q[:30]}")
        else:
            results.append(None)
            print(f"   [본문이미지] 실패: {q[:30]}")
    return results




# ── 프롬프트 빌더 (SEO + AEO + GEO 통합형) ─────────────
_PERSONA_TONE = """당신은 '박대홍'입니다. 7년차 직장인이고, 월급쟁이 재테크 블로거입니다.
펀드매니저나 전문가가 아닙니다. 본인도 시행착오 많았고, 손해 본 적도 있고, 모르고 시작한 것도 많습니다.
책 읽기와 자기계발을 좋아하고, 부업·사업에도 관심 많고, 항상 새로운 거 도전합니다.
유용하고 확실한 정보를 좋아하고, 두루뭉술한 거 싫어합니다.
개인적인 의견도 솔직히 말합니다. "이건 별로다", "이게 진짜 좋더라" 같이.

같은 직장인 독자한테 시행착오 덜 겪게 해주려고 글을 씁니다. 잘난 척 안 하고,
본인도 헤맸다는 걸 먼저 인정하고 시작합니다."""


def build_prompt(category: str, keyword: str, seo_meta: dict | None = None) -> str:
    """
    2026 전략 기반 SEO+AEO+GEO 통합 프롬프트.

    - SEO: 구글/네이버 검색 상위 (기존 강점 유지)
    - AEO: 답변 엔진 (Featured Snippet, AI Overview) - TL;DR + FAQ 강화
    - GEO: 생성형 엔진 (ChatGPT, Perplexity, Gemini) - 구조화/정의/출처

    카테고리별로 글 유형을 자동 판단해서 비교표/단계별/가이드 형식 결정.
    """
    # ── 카테고리 인텐트 매핑 (기본값 폴백) ─────
    try:
        from keyword_pool_v2 import CATEGORY_INTENTS
        intent = CATEGORY_INTENTS.get(category, {})
    except ImportError:
        intent = {}

    primary_format       = intent.get("primary_format", "guide")
    tone                 = intent.get("tone", "balanced")
    needs_official_link  = intent.get("needs_official_link", False)
    audience             = intent.get("audience", "20~40대 직장인")

    # ── 형식별 추가 지시 ─────
    format_directives = {
        "step_by_step": (
            "[필수 형식: 단계별 가이드]\n"
            "- 본문 후반에 '단계별 신청 방법' 또는 '진행 절차' 섹션 필수\n"
            "- steps 필드에 1~5단계로 정리 (각 단계는 한 문장 + 부연 1문장)\n"
        ),
        "comparison": (
            "[필수 형식: 비교표]\n"
            "- 본문에 비교 대상 2~3개를 표로 정리\n"
            "- comparison_table 필드에 {headers, rows} 구조로 채울 것\n"
            "- 항목 예: 가입조건, 한도, 금리, 세제혜택, 추천 대상\n"
        ),
        "how_to": (
            "[필수 형식: How-to]\n"
            "- 실전 사용 예시 1~2개 본문에 포함\n"
            "- steps 필드에 핵심 사용 흐름 정리\n"
        ),
        "guide": (
            "[필수 형식: 종합 가이드]\n"
            "- 정의 → 자격/조건 → 신청 방법 → 주의사항 흐름\n"
            "- comparison_table 또는 steps 중 하나는 반드시 채울 것\n"
        ),
        "checklist": (
            "[필수 형식: 체크리스트형]\n"
            "- steps 필드에 확인 항목 5개 정리\n"
            "- 본문은 각 항목의 배경 설명\n"
        ),
        "experience": (
            "[필수 형식: 경험담 결합]\n"
            "- 1인칭 경험 서술 일부 허용 ('제가 겪어본 바로는...')\n"
            "- 단, 최소 2개 H2는 객관 정보 (숫자/근거)\n"
        ),
        "insight": (
            "[필수 형식: 분석/인사이트]\n"
            "- '왜 그런가 → 직장인에 미치는 영향 → 대응 방법' 흐름\n"
            "- 변경 전/후 비교가 가능하면 comparison_table 활용\n"
        ),
    }
    format_block = format_directives.get(primary_format, format_directives["guide"])

    # ── 톤 지시 ─────
    tone_directives = {
        "objective": _PERSONA_TONE,
        "practical": _PERSONA_TONE,
        "data_driven": _PERSONA_TONE,
        "balanced": _PERSONA_TONE,
        "analytical": _PERSONA_TONE,
    }
    tone_directive = tone_directives.get(tone, tone_directives["balanced"])

    # ── SEO 메타 정보 처리 ─────
    seo_hint = ""
    if seo_meta:
        monthly = seo_meta.get("monthly_total")
        comp    = seo_meta.get("competition")
        if monthly or comp:
            seo_hint = "\n[키워드 SEO 데이터]\n"
            if monthly:
                seo_hint += f"- 월 검색량: {monthly}회 → 이 검색자들을 모두 만족시킬 수 있는 포괄적 내용 작성\n"
            if comp:
                seo_hint += f"- 경쟁 강도: {comp} → "
                if comp == "낮음":
                    seo_hint += "레드오션이 아니므로 정확한 정보와 깊이에 집중\n"
                elif comp == "높음":
                    seo_hint += "경쟁이 심하므로 차별화된 데이터/구조로 승부\n"
                else:
                    seo_hint += "적정 경쟁도 - 정보 + 사례 균형\n"

    # ── 공식 링크 요청 ─────
    official_link_block = ""
    if needs_official_link:
        official_link_block = (
            "\n[참고자료(references) 필수]\n"
            "- 정부 공식 사이트 1~2개 URL을 references 필드에 포함\n"
            "- 예: https://www.gov.kr , https://www.bokjiro.go.kr , "
            "https://www.youthcenter.go.kr , https://www.bizinfo.go.kr\n"
            "- 정확한 정책명·신청 페이지 URL을 모르면 도메인 루트만 명시 (가짜 URL 금지)\n"
        )

    # ── 오늘 날짜 (업데이트 표기용) ─────
    today_str = datetime.now().strftime("%Y년 %m월 %d일")

    return f"""당신은 한국 직장인을 위한 정보 큐레이션 전문가입니다.
사용자가 "더 검색할 필요 없는" 완벽한 답변을 작성합니다.
SEO(검색)·AEO(답변엔진)·GEO(생성형엔진) 3가지를 동시에 최적화합니다.

[블로그 정보]
- 블로그명: {BLOG_TITLE}
- 카테고리: {category}
- 타겟 키워드: {keyword}
- 작성 기준일: {today_str}
- 대상 독자: {audience}
{seo_hint}

═══════════════════════════════════════════════════════
[글의 목적 - 3가지 동시 달성]
1. SEO: 구글/네이버 검색 상위 (전통 검색 트래픽)
2. AEO: 검색 결과 Featured Snippet/AI Overview에 직접 인용
3. GEO: ChatGPT/Perplexity/Gemini 답변에 우리 글이 인용되도록
═══════════════════════════════════════════════════════

{format_block}

[톤 가이드 - 매우 중요, 위반 시 글 폐기]
- {tone_directive}

▷ 절대 금지 단어 (한 번도 쓰지 말 것):
극대화, 최적의, 최적화, 효과적인, 효율적인, 전략적, 지속적인, 안정적인,
핵심적인, 강력한, 매우 적합한, 매력적인, 견고한, 필수적인, 본질적인,
궁극적인, 혁신적인, 차별화된, 종합적인, 체계적인, 광범위한, 폭넓은

▷ AI 클리셰 금지:
"본 글은", "본 콘텐츠는", "~을 살펴보겠습니다", "~을 알아보겠습니다",
"~로 자리매김했습니다", "~로 주목받고 있습니다", "~을 시사합니다",
"~에 기여합니다", "~을 선도하며", "결론적으로", "요약하자면",
"이는 ~입니다" (영어 직역체), "~함을 의미합니다" (반복 금지)

▷ 광고 카피체 소제목 금지:
- "~잘 썼다고 소문날까요?", "~이것만은 꼭!", "~핵심 포인트!", "~놓치면 후회"
- "~하는 법 BEST 5", "~완벽 정리"
- 소제목은 박대홍이 친구한테 말하듯 담백하게:
  좋은 예: "그래서 정확히 뭔가요?", "어디에 써야 좋을까", "써보면서 깨달은 것", "주의할 점 몇 가지"
  나쁜 예: "이것만은 꼭 조심하세요!", "잘 썼다고 소문날까요?"

▷ 같은 단어 한 글에 3번 이상 반복 금지. 특히 "활용", "효과", "안정"

▷ 문장 길이 분산 (★★★ 가장 중요, 위반 시 글 폐기):

[강제 규칙]
1. 각 H2 섹션마다 15자 이하 짧은 단문을 최소 2개 이상 박을 것
2. 도입부에는 첫 문장을 10자 이하 단문으로 시작 (예시: "저도 그랬습니다.", "솔직히 말씀드릴게요.")
3. 단락이 바뀌는 곳마다 짧은 단문으로 리듬 끊을 것

[좋은 예 - 박대홍 본인 톤]
"저 역시 그랬습니다. 미루고 미루다 발등에 불똥이 떨어지고 나서야 밤을 새우며 일을 처리하고 스스로를 압박에 강한 사람이라고 위안하곤 했죠."
→ 첫 문장 10자, 두 번째 문장 60자+. 이렇게 차이 나야 함.

[짧은 단문 예시 풀 - 적극 사용할 것]
"저도 그랬어요." / "솔직히 그랬죠." / "근데 함정이 있어요." / "결론부터." /
"여기서 갈립니다." / "이거 진짜 중요해요." / "저는 좀 달라요." / "그게 맹점이에요." /
"진짜입니다." / "모르면 손해예요." / "쉽지 않아요." / "고민 좀 했어요." /
"답은 간단해요." / "현실은 다르죠." / "저는 후회했어요." / "그때 알았죠."

[금지]
- 모든 문장이 30자 이상이면 즉시 AI 티 납니다. 절대 금지.
- 의문문이나 "~까요?" 같은 물음표 문장으로 짧은 단문 대체하지 말 것 (그건 다른 카테고리)

▷ 종결어미 분포 (정밀):
- "~합니다" 60% (격식)
- "~죠 / ~네요 / ~거든요 / ~더라고요 / ~더라구요 / ~잖아요" 30% (구어)
- "~예요 / ~어요 / ~았어요" 10% 이하 (가벼운 톤, 너무 많으면 블로그 글 같지 않음)

▷ 박대홍 본인 종결어미 빈도:
"~습니다" > "~죠" > "~구요" > "~더라구요" > "~ㅎㅎ"(글당 1번)
"~예요/~요" 종결은 적게 씀. 너무 가벼워 보이면 신뢰감 떨어짐.

▷ 단, 본문은 격식 유지. "~함", "~다요" 같은 반말체 금지.

▷ 1인칭 경험 1개 이상 (각 H2 섹션마다):
- "저도 처음엔 ~했다가 ~"
- "동료가 ~하더라고요"
- "작년에 ~ 해봤는데"
- "책에서 봤는데" + 본인 해석
- 단, 가짜 수치(수익률 %, 금액)는 지어내지 말 것. 경험은 정성적으로만.

▷ 도입부에 자기 약점 인정 1줄 필수:
- "저도 처음엔 몰랐어요" / "한참 헤맸습니다" / "솔직히 ~는 아직도 어렵습니다"
- 잘난 척 금지. 전문가 행세 금지.

▷ 개인 의견 표시:
- "제 생각엔", "저는 ~ 쪽이 끌립니다", "이건 좀 별로였어요", "이게 진짜 좋더라구요"
- 호불호 없는 백과사전 톤 금지

▷ 할루시네이션 방어:
- 확실하지 않은 구체 수치(거래량, 점유율, 수익률 등)는 쓰지 말 것
- 정확한 숫자 모르겠으면 "대략", "~수준", "약 ~정도"로 두루뭉술하게
- 출처 없는 통계 절대 금지
- 운용보수, 한도, 세율 같은 공식 수치는 reference에 출처 있을 때만 명시

[톤 예시 - 박대홍 본인이 쓴 글 스타일, 이 리듬과 호흡을 따를 것]

예시 1 (자기 고백 → 책/정보 → 권유 흐름):
"저 역시 그랬습니다. 미루고 미루다 발등에 불똥이 떨어지고 나서야 밤을 새우며
일을 처리하고 스스로를 압박에 강한 사람이라고 위안하곤 했죠. 어떤 날은,
그렇게 압박이 다가오지 않으면 의지가 생기지 않기도 했구요. 하지만
나카지마 사토시의 책을 읽으면서 제가 얼마나 비효율적인 방식으로 인생을
낭비해왔는지 제대로 느꼈습니다. 사실 알고있었다 한들, 고치기 힘든 부분이기도
했지만요."

예시 2 (재테크 글 도입부 톤):
"솔직히 저도 처음엔 ETF가 뭔지 몰랐습니다. 적금만 5년 부었거든요.
근데 동료가 '연금저축 안 해?' 한마디 하길래 그때부터 찾아봤습니다.
결론부터 말씀드리면, 진작 시작 안 한 게 후회됩니다."

예시 3 (정보 전달 + 개인 의견):
"세 가지 중에 뭐 고를지 한참 고민했어요. 저는 결국 KODEX로 갔는데,
이유는 단순합니다. 그냥 거래량이 제일 많아서요. 운용보수 0.01% 차이는
솔직히 1년 굴려봐야 몇 천원입니다. 거기에 머리 쓰느니 그 시간에
책 한 권 더 읽는 게 낫더라구요."

위 3개 예시의 호흡, 종결어미 분포, 자기 고백 비중, 짧은 단문 사용 빈도를
본문 전체에 일관되게 적용하세요.

[제목 작성 원칙]
- 길이: 28~38자
- 타겟 키워드 '{keyword}' 포함 (앞쪽 권장)
- 숫자 포함 권장 ("5가지", "3단계", "2026년")
- 작성 기준일 또는 연도 명시 권장 (신선도 신호)
- 클릭 욕구 자극하되 과장 금지

[본문(content) 구조 - 필수 H2 4~5개]
1. 첫 단락(H2 없이): 3~4문장 도입 - 검색 의도 명시 + 결론 미리 1줄 공개
2. ## H2 1: '정의/개요' 또는 '대상자' (정답형 1문장으로 시작)
3. ## H2 2: '핵심 조건/혜택' (구체적 숫자/금액/기간)
4. ## H2 3: '신청 방법' 또는 '비교/선택 기준'
5. ## H2 4: '주의사항' 또는 '실전 팁' (놓치기 쉬운 점)
6. (선택) ## H2 5: '관련 정책/도구' (내부 링크 유도)

[각 H2 섹션 작성 원칙 - AEO 핵심]
- 첫 문장은 반드시 '정답형' (예: "{keyword}는 ~입니다.")
- 4~6문장으로 구성, 너무 길면 분리
- 구체적 숫자/금액/기간 최소 2개 (예: "월 70만원", "3년 만기")
- 정의 명시 ("X란 ~을 의미합니다") - GEO 인용 핵심
- 섹션 끝: "> 포인트: [한 줄 요약]" (블록 인용 형식)
  단, "포인트:" 한 줄 요약도 박대홍 톤으로:
  - 좋은 예: "> 포인트: 결국 자연어로 시키면 코드 짜주는 거예요. 그게 핵심."
  - 나쁜 예: "> 포인트: CLAUDE CODE는 자연어 명령으로 코드를 생성/분석하는 클로드 AI의 코딩 지원 기능입니다." (백과사전체)
  - 정의문 X, 박대홍 본인 말투로 정리. "결국 ~예요", "한마디로 ~", "정리하면 ~" 같은 도입.

[필수 JSON 필드 - AEO/GEO 최적화]
- tldr: 핵심 답변 3줄 (각 60~90자) - AEO 최우선 인용 대상
- target_audience: "이 글은 ___을 위한 글입니다" 1문장
- comparison_table 또는 steps 중 하나 이상 채울 것 (위 형식 지시 따름)
- faq: 5개 (Q&A) - FAQPage Schema, AI 답변에 직접 인용됨
- references: 2~4개 (label + url) - GEO 신뢰도

[글 분량]
- content 본문: 1,800~2,500자 (공백 제외)
- TL;DR 3줄 + 본문 + FAQ로 이어짐 (FAQ는 별도 처리되니 content엔 포함 X)

[키워드 밀도]
- 메인 키워드 '{keyword}': 본문 내 4~7회 자연스럽게
- 시맨틱 키워드(연관어): 5~10개 분포
- 키워드 스터핑(부자연 반복) 금지

[절대 금지]
- 이모티콘, 과도한 특수문자 (!!, ??, ~~~)
- 마크다운 bold(**), italic(*) - 소제목 ## 만 허용
- "여러분 파이팅" 같은 진부한 마무리
- 근거 없는 일반론
- 가짜 URL/통계 (확실하지 않으면 references에 도메인 루트만)
{official_link_block}
[응답 형식 - 반드시 아래 JSON만 출력 (코드블록/설명/인사말 금지)]
{{
  "title": "제목 (28~38자)",
  "category": "{category}",
  "keyword": "{keyword}",
  "tldr": ["3줄 요약 첫번째", "두번째", "세번째"],
  "target_audience": "이 글은 ___을 위한 글입니다",
  "content": "도입부 + ## H2 4~5개 본문 (\\n\\n으로 문단 구분, FAQ는 여기 넣지 말 것)",
  "comparison_table": {{"headers": ["항목","A","B"], "rows": [["조건","..","..."]]}} ,
  "steps": [{{"title":"1단계 제목","desc":"한 문장 부연"}}],
  "summary": "2문장 핵심 요약 (각 70자 이내)",
  "tags": ["{keyword}","{category}","직장인"],
  "faq": [
    {{"q":"질문1","a":"답변1"}},
    {{"q":"질문2","a":"답변2"}},
    {{"q":"질문3","a":"답변3"}},
    {{"q":"질문4","a":"답변4"}},
    {{"q":"질문5","a":"답변5"}}
  ],
  "references": [{{"label":"정부24","url":"https://www.gov.kr"}}]
}}

* comparison_table과 steps는 둘 다 채워도 되고, 하나만 의미 있으면 다른 하나는 빈 객체/빈 배열로 두어도 됩니다."""


# ── Gemini API 호출 ───────────────────────────────────
def generate_article(category: str, keyword: str, seo_meta: dict | None = None) -> dict | None:
    category = normalize_category(category)
    prompt = build_prompt(category, keyword, seo_meta)
    url = (
        "https://generativelanguage.googleapis.com/v1beta/models/"
        f"gemini-2.5-flash:generateContent?key={GEMINI_API_KEY}"
    )
    payload = {
        "contents": [{"parts": [{"text": prompt}]}],
        "generationConfig": {
            "temperature": 0.95,
            "topP": 0.92,
            "maxOutputTokens": 8192,
        },
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

            # JSON 파싱 시도 (3단계 복구 로직)
            article = None
            try:
                article = json.loads(text)
            except json.JSONDecodeError as e1:
                print(f"   1차 파싱 실패: {e1}. 복구 시도...")
                # 복구 1: content 필드 안의 이스케이프 안 된 따옴표 처리
                try:
                    fixed = _repair_json_content(text)
                    article = json.loads(fixed)
                    print("   복구 성공 (따옴표 이스케이프 처리)")
                except json.JSONDecodeError as e2:
                    print(f"   2차 파싱 실패: {e2}. content만 수동 추출 시도...")
                    # 복구 2: content 필드를 직접 파싱해 수동 구성
                    manual = _extract_fields_manually(text, category, keyword)
                    if manual:
                        article = manual
                        print("   복구 성공 (수동 추출)")
            
            if article:
                print(f"   글자수: {len(article.get('content',''))}자")
                return article

        except json.JSONDecodeError as e:
            print(f"   JSON 파싱 오류: {e}")
        except (KeyError, IndexError):
            print("   응답 형식 오류, 재시도...")
        except Exception as e:
            print(f"   오류: {e}")

    return None


# ── JSON 복구 헬퍼 ─────────────────────────────────────
def _repair_json_content(text: str) -> str:
    """
    Gemini가 content 필드 안에 이스케이프 안 된 따옴표를 넣었을 때 복구.
    예: "content": "이건 "진짜" 현실입니다" → "content": "이건 \"진짜\" 현실입니다"
    """
    import re
    # content 필드의 값만 찾아서 내부 따옴표 이스케이프
    # 패턴: "content": "...." (다음 필드 앞까지)
    # 주의: summary, title 같은 다른 필드도 동일 문제 가능
    
    for field in ["content", "summary", "title"]:
        # "field": " 로 시작해서 다음 ",\n"다른필드" 전까지
        pattern = rf'("{field}"\s*:\s*")((?:[^"\\]|\\.)*(?:"[^",}}]*)*)(",\s*"[a-z_]+"|"\s*[,}}])'
        
        def _escape_inner(match):
            prefix = match.group(1)
            value  = match.group(2)
            suffix = match.group(3)
            # 값 안의 이스케이프 안 된 따옴표를 이스케이프
            value = re.sub(r'(?<!\\)"', r'\\"', value)
            # 줄바꿈도 이스케이프
            value = value.replace("\n", "\\n").replace("\r", "")
            return f'{prefix}{value}{suffix}'
        
        try:
            text = re.sub(pattern, _escape_inner, text, flags=re.DOTALL)
        except Exception:
            pass
    
    return text


def _extract_fields_manually(text: str, category: str, keyword: str) -> dict | None:
    """
    JSON 파싱이 완전히 실패했을 때, 정규식으로 주요 필드만 추출.
    최후의 수단.
    """
    import re
    
    def _extract(field: str) -> str:
        # "field": "값" 형태 또는 멀티라인
        pattern = rf'"{field}"\s*:\s*"(.+?)"\s*[,}}]'
        m = re.search(pattern, text, re.DOTALL)
        if m:
            return m.group(1).replace('\\"', '"').replace('\\n', '\n')
        return ""
    
    title   = _extract("title")
    content = _extract("content")
    summary = _extract("summary")
    
    if not title or not content or len(content) < 300:
        return None  # 복구 불가
    
    return {
        "title":    title,
        "category": category,
        "keyword":  keyword,
        "content":  content,
        "summary":  summary or f"{keyword}에 대한 직장인 박대홍의 실전 경험을 공개합니다.",
        "tags":     [keyword, category, "직장인", "부업"],
        "faq":      [],  # 복구 모드에선 FAQ 없음
    }


# ── 콘텐츠 정리 ──────────────────────────────────────
def clean_content(text: str) -> str:
    import re
    text = text.replace("\\n\\n", "\n\n").replace("\\n", "\n").replace("\\t", " ")
    text = re.sub(r"\*\*(.*?)\*\*", r"\1", text)   # bold 제거
    text = re.sub(r"\*(.*?)\*",   r"\1", text)      # italic 제거
    text = re.sub(r"\n{3,}", "\n\n", text)
    return text.strip()


# ── content를 HTML로 변환 ─────────────────────────────
def content_to_html(text: str, hero_image: dict | None = None, body_images: list | None = None) -> str:
    """
    ##소제목 → <h2>, > 포인트: → <blockquote>, 빈줄 → <p> 로 변환.
    
    이미지 배치 전략:
    - hero_image: 첫 번째 <h2> 바로 위 (기존과 동일)
    - body_images[0]: 첫 번째 <h2> 섹션 끝 (두 번째 <h2> 직전)
    - body_images[1]: 두 번째 <h2> 섹션 끝 (세 번째 <h2> 직전)
    - body_images[2]: 세 번째 <h2> 섹션 끝 (네 번째 <h2> 직전 또는 글 끝)
    
    body_images 원소가 None이면 해당 위치는 스킵(이미지 없이 진행).
    """
    lines   = text.strip().split("\n")
    html    = []
    hero_inserted = False
    body_images   = body_images or []

    # 크레딧 캡션 생성
    def _build_caption(img: dict) -> str:
        src = img.get("source", "")
        if src == "unsplash" and img.get("credit") and img.get("credit_link"):
            return (
                f'<figcaption style="font-size:11px;color:#888;margin-top:6px;text-align:right;">'
                f'Photo by <a href="{img["credit_link"]}" target="_blank" '
                f'style="color:#888;">{img["credit"]}</a> on Unsplash</figcaption>'
            )
        return ""

    def _build_figure(img: dict, extra_margin: str = "32px 0 24px") -> str:
        caption = _build_caption(img)
        return (
            f'<figure style="margin:{extra_margin};">'
            f'<img src="{img["url"]}" alt="{img["alt"]}" '
            f'style="width:100%;border-radius:12px;object-fit:cover;max-height:420px;" loading="lazy">'
            f'{caption}'
            f'</figure>'
        )

    # 1단계: 라인을 섹션별로 파싱 (각 h2 앞에 이미지 삽입 가능한 위치 마킹)
    # 구조: [(type, content)] — type: 'heading' | 'quote' | 'para'
    parsed = []
    for line in lines:
        line = line.strip()
        if not line:
            continue
        if line.startswith("## "):
            parsed.append(("heading", line[3:].strip()))
        elif line.startswith("> "):
            parsed.append(("quote", line[2:].strip()))
        else:
            parsed.append(("para", line))

    # 2단계: heading 인덱스 수집
    heading_indices = [i for i, (t, _) in enumerate(parsed) if t == "heading"]

    # 3단계: HTML 조립
    # - 첫 번째 heading 직전: hero_image 삽입
    # - 각 heading 시작 직전(첫 번째 제외): 이전 섹션의 body_image 삽입
    body_img_idx = 0
    for i, (kind, content) in enumerate(parsed):
        if kind == "heading":
            # 현재 heading이 N번째(1-indexed)인지
            pos_in_headings = heading_indices.index(i)
            
            if pos_in_headings == 0:
                # 첫 heading 위 → hero 이미지
                if hero_image and not hero_inserted:
                    html.append(_build_figure(hero_image, "32px 0 24px"))
                    hero_inserted = True
            else:
                # 두 번째 이상 heading 위 → 이전 섹션 끝에 body 이미지
                if body_img_idx < len(body_images):
                    img = body_images[body_img_idx]
                    if img:
                        html.append(_build_figure(img, "28px 0 28px"))
                    body_img_idx += 1
            
            html.append(f"<h2>{content}</h2>")

        elif kind == "quote":
            html.append(f"<blockquote>{content}</blockquote>")
        else:
            html.append(f"<p>{content}</p>")

    # 4단계: 글 맨 끝에 마지막 본문 이미지 (있으면)
    if body_img_idx < len(body_images):
        img = body_images[body_img_idx]
        if img:
            html.append(_build_figure(img, "32px 0 16px"))

    # 헤더가 하나도 없는 글 → 맨 앞에 hero만 삽입
    if hero_image and not hero_inserted:
        html.insert(0, _build_figure(hero_image, "0 0 28px"))

    return "\n".join(html)


# ═══════════════════════════════════════════════════════
#  AEO/GEO 보조 섹션 HTML 빌더 (TL;DR, 비교표, 단계, 참고자료)
# ═══════════════════════════════════════════════════════

def _esc(s) -> str:
    """HTML 안전 이스케이프"""
    if s is None:
        return ""
    return (str(s)
            .replace("&", "&amp;")
            .replace("<", "&lt;")
            .replace(">", "&gt;")
            .replace('"', "&quot;"))


def _build_tldr_html(tldr) -> str:
    """TL;DR 박스 (글 최상단). AEO 핵심 - AI가 가장 자주 인용."""
    if not tldr or not isinstance(tldr, list):
        return ""
    items = [t.strip() for t in tldr if isinstance(t, str) and t.strip()]
    if not items:
        return ""
    lis = "".join(f'<li style="margin:6px 0;line-height:1.6;">{_esc(it)}</li>' for it in items[:5])
    return (
        '<aside class="post-tldr" style="'
        'background:#f8f7f4;border-left:4px solid #c17f3e;'
        'padding:18px 22px;margin:0 0 28px;border-radius:0 8px 8px 0;">'
        '<div style="font-size:13px;font-weight:700;color:#c17f3e;'
        'letter-spacing:0.05em;margin-bottom:8px;">TL;DR · 핵심 요약</div>'
        f'<ul style="margin:0;padding-left:20px;color:#1a2640;font-size:15px;">{lis}</ul>'
        '</aside>'
    )


def _build_audience_html(audience: str) -> str:
    """이 글의 대상 독자 박스."""
    if not audience or not isinstance(audience, str):
        return ""
    return (
        '<div class="post-audience" style="'
        'font-size:13px;color:#666;margin:0 0 24px;padding:10px 14px;'
        'background:#fafafa;border-radius:6px;">'
        f'👤 {_esc(audience.strip())}'
        '</div>'
    )


def _build_updated_badge(iso_date: str) -> str:
    """업데이트 배지 (글 상단 우측). 신선도 신호."""
    try:
        dt = datetime.fromisoformat(iso_date)
        date_str = dt.strftime("%Y.%m.%d")
    except Exception:
        date_str = datetime.now().strftime("%Y.%m.%d")
    return (
        '<div class="post-updated" style="'
        'text-align:right;font-size:12px;color:#999;margin:0 0 12px;">'
        f'📅 {date_str} 업데이트'
        '</div>'
    )


def _build_comparison_html(table) -> str:
    """비교표 HTML. {headers: [...], rows: [[...], [...]]} 구조."""
    if not table or not isinstance(table, dict):
        return ""
    headers = table.get("headers") or []
    rows    = table.get("rows") or []
    if not headers or not rows:
        return ""

    th_html = "".join(
        f'<th style="padding:10px 12px;background:#1a2640;color:#fff;'
        f'text-align:left;font-size:14px;font-weight:600;">{_esc(h)}</th>'
        for h in headers
    )
    tr_html = []
    for i, row in enumerate(rows):
        if not isinstance(row, list):
            continue
        bg = "#fafafa" if i % 2 else "#fff"
        td = "".join(
            f'<td style="padding:10px 12px;border-bottom:1px solid #eee;'
            f'background:{bg};font-size:14px;color:#2a2a2a;">{_esc(c)}</td>'
            for c in row
        )
        tr_html.append(f'<tr>{td}</tr>')

    return (
        '<section class="post-comparison" style="margin:36px 0 24px;overflow-x:auto;">'
        '<h2 style="margin-bottom:14px;">한눈에 비교</h2>'
        '<table style="width:100%;border-collapse:collapse;border-radius:8px;overflow:hidden;'
        'box-shadow:0 1px 3px rgba(0,0,0,0.06);">'
        f'<thead><tr>{th_html}</tr></thead>'
        f'<tbody>{"".join(tr_html)}</tbody>'
        '</table>'
        '</section>'
    )


def _build_steps_html(steps) -> str:
    """단계별 가이드 HTML. [{title, desc}, ...] 구조."""
    if not steps or not isinstance(steps, list):
        return ""
    valid = [s for s in steps if isinstance(s, dict) and s.get("title")]
    if not valid:
        return ""

    items = []
    for i, s in enumerate(valid[:7], 1):
        title = _esc(s.get("title", "").strip())
        desc  = _esc(s.get("desc", "").strip())
        items.append(
            '<li style="display:flex;gap:14px;align-items:flex-start;'
            'margin:0 0 14px;padding:14px;background:#fff;border-radius:8px;'
            'border:1px solid #eee;">'
            '<div style="flex:0 0 32px;height:32px;border-radius:50%;'
            'background:#c17f3e;color:#fff;display:flex;align-items:center;'
            f'justify-content:center;font-weight:700;font-size:14px;">{i}</div>'
            '<div style="flex:1;">'
            f'<div style="font-weight:700;color:#1a2640;margin-bottom:4px;font-size:15px;">{title}</div>'
            f'<div style="color:#444;font-size:14px;line-height:1.6;">{desc}</div>'
            '</div>'
            '</li>'
        )
    return (
        '<section class="post-steps" style="margin:36px 0 24px;">'
        '<h2 style="margin-bottom:14px;">단계별 가이드</h2>'
        f'<ol style="list-style:none;padding:0;margin:0;">{"".join(items)}</ol>'
        '</section>'
    )


def _build_references_html(refs) -> str:
    """참고자료 섹션. [{label, url}, ...] 구조. GEO 신뢰도 핵심."""
    if not refs or not isinstance(refs, list):
        return ""
    valid = [r for r in refs if isinstance(r, dict) and r.get("url")]
    if not valid:
        return ""

    items = []
    for r in valid[:6]:
        label = _esc(r.get("label", r.get("url", "")).strip())
        url   = _esc(r.get("url", "").strip())
        items.append(
            f'<li style="margin:8px 0;font-size:14px;">'
            f'<a href="{url}" target="_blank" rel="nofollow noopener" '
            f'style="color:#1a2640;text-decoration:underline;">{label}</a>'
            f'</li>'
        )
    return (
        '<section class="post-references" style="margin:36px 0 16px;'
        'padding:18px 22px;background:#fafafa;border-radius:8px;">'
        '<h2 style="margin-top:0;margin-bottom:10px;font-size:18px;">참고자료</h2>'
        f'<ul style="margin:0;padding-left:20px;">{"".join(items)}</ul>'
        '<div style="margin-top:10px;font-size:12px;color:#888;">'
        '※ 외부 링크는 별도 창에서 열립니다. 정확한 정보는 공식 사이트에서 확인하세요.'
        '</div>'
        '</section>'
    )


# ── manifest 업데이트 ─────────────────────────────────
def update_manifest():
    posts = []
    for f in sorted(POSTS_DIR.glob("post_*.json"), reverse=True):
        try:
            data = json.loads(f.read_text(encoding="utf-8"))
            seo_analysis = data.get("seo_analysis", {}) or {}
            posts.append({
                "filename":      f.name,
                "title":         data.get("title", ""),
                "category":      data.get("category", ""),
                "keyword":       data.get("keyword", ""),
                "summary":       data.get("summary", ""),
                "tags":          data.get("tags", []),
                "created_at":    data.get("created_at", ""),
                "status":        data.get("status", "draft"),
                "has_image":     bool(data.get("hero_image")),
                "thumbnail":     (data.get("hero_image") or {}).get("url", ""),
                "has_faq":       bool(data.get("faq")),
                "has_tldr":       bool(data.get("tldr")),
                "has_comparison": bool((data.get("comparison_table") or {}).get("rows")),
                "has_steps":      bool(data.get("steps")),
                "has_references": bool(data.get("references")),
                "seo_score":     seo_analysis.get("score"),
                "monthly_search":seo_analysis.get("monthly_total"),
            })
        except Exception as e:
            print(f"  [경고] {f.name} 파싱 오류: {e}")

    MANIFEST_PATH.write_text(
        json.dumps(posts, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    print(f"   manifest.json 업데이트: {len(posts)}개 글")
    return posts


# ── 글 저장 ──────────────────────────────────────────
def save_article(article: dict, hero_image: dict | None = None, body_images: list | None = None) -> str | None:
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
    article["content_raw"] = raw_content                                            # 원본 텍스트 보존
    body_html              = content_to_html(raw_content, hero_image, body_images)  # 본문 HTML
    article["summary"]     = clean_content(article.get("summary", ""))

    # ── 신규 AEO/GEO 섹션 빌드 ──────────────────────────
    tldr             = article.get("tldr") or []
    target_audience  = article.get("target_audience", "")
    comparison_table = article.get("comparison_table") or {}
    steps            = article.get("steps") or []
    references       = article.get("references") or []

    pre_html = (
        _build_updated_badge(article["created_at"])
        + _build_tldr_html(tldr)
        + _build_audience_html(target_audience)
    )
    post_html = (
        _build_comparison_html(comparison_table)
        + _build_steps_html(steps)
    )
    refs_html = _build_references_html(references)

    # 최종 content 조립: [배지+TL;DR+대상] + [본문(이미지 포함)] + [비교표+단계] + [FAQ는 아래에서 추가] + [참고자료]
    article["content"] = pre_html + body_html + post_html
    # references는 FAQ 뒤로 보낼 예정 → 잠시 보관
    article["_references_html"] = refs_html

    if hero_image:
        article["hero_image"] = hero_image

    # 본문 이미지 메타데이터 저장 (None 제외)
    if body_images:
        valid_body = [img for img in body_images if img]
        if valid_body:
            article["body_images"] = valid_body

    # ── SEO 필드 자동 생성 ──────────────────────────────
    title    = article.get("title", "")
    keyword  = article.get("keyword", "")
    category = article.get("category", "")
    summary  = article.get("summary", "")
    tags     = article.get("tags", [])
    faq      = article.get("faq", [])

    # SEO 제목: 키워드 앞에, 브랜드 뒤에 (60자 제한 - 구글 스니펫 최적)
    article["seo_title"] = f"{title} | 직장인 수익일기"[:60]

    # SEO 설명: 150~160자가 구글 스니펫 최적
    base_desc = summary[:140] if summary else f"{keyword}에 대한 직장인 박대홍의 실전 경험과 구체적 수치를 공개합니다."
    article["seo_description"] = (base_desc + " | 직장인 수익일기")[:160]

    # SEO 키워드 (메인 키워드 앞쪽 배치)
    seo_keywords = list(dict.fromkeys(
        [keyword, category, f"{category} 추천", f"{keyword} 방법", "직장인 부업", "직장인 수익일기"] + tags
    ))
    article["seo_keywords"] = ", ".join(seo_keywords[:12])

    # FAQ 처리 — JSON-LD FAQPage Schema용
    if faq and isinstance(faq, list):
        clean_faq = []
        for item in faq:
            if isinstance(item, dict) and item.get("q") and item.get("a"):
                clean_faq.append({
                    "q": str(item["q"]).strip()[:200],
                    "a": str(item["a"]).strip()[:500],
                })
        if clean_faq:
            article["faq"] = clean_faq
            # FAQ HTML을 content 뒤에 추가
            faq_html = ['\n<section class="faq-section" style="margin-top:48px;padding:24px;background:#f8f7f4;border-radius:12px;border-left:4px solid #c17f3e;">']
            faq_html.append('<h2 style="margin-top:0;">자주 묻는 질문</h2>')
            for q_item in clean_faq:
                faq_html.append(
                    f'<div style="margin:20px 0;">'
                    f'<p style="font-weight:700;color:#1a2640;margin:0 0 8px 0;">Q. {q_item["q"]}</p>'
                    f'<p style="margin:0;color:#2a2a2a;">A. {q_item["a"]}</p>'
                    f'</div>'
                )
            faq_html.append('</section>')
            article["content"] += "\n" + "\n".join(faq_html)

    # 참고자료(references) - FAQ 뒤에 배치하여 글 마무리 신뢰도 강화
    refs_html = article.pop("_references_html", "")
    if refs_html:
        article["content"] += "\n" + refs_html

    # JSON-LD 구조화 데이터 (Article + FAQPage)
    # post.html에서 활용 가능하도록 저장
    article["jsonld"] = {
        "article": {
            "@context":       "https://schema.org",
            "@type":          "BlogPosting",
            "headline":       title,
            "description":    base_desc,
            "keywords":       article["seo_keywords"],
            "articleSection": category,
            "author":         {"@type": "Person", "name": "박대홍"},
            "publisher":      {
                "@type": "Organization",
                "name":  "직장인 수익일기",
                "logo":  {"@type": "ImageObject", "url": "https://koreansalaryman.com/og-image.png"}
            },
            "datePublished":  article.get("created_at", ""),
        },
    }
    if hero_image:
        article["jsonld"]["article"]["image"] = (
            hero_image["url"] if hero_image["url"].startswith("http")
            else f"https://koreansalaryman.com{hero_image['url']}"
        )
    
    if article.get("faq"):
        article["jsonld"]["faq"] = {
            "@context":  "https://schema.org",
            "@type":     "FAQPage",
            "mainEntity": [
                {
                    "@type":          "Question",
                    "name":           q["q"],
                    "acceptedAnswer": {"@type": "Answer", "text": q["a"]},
                } for q in article["faq"]
            ],
        }

    # HowTo Schema (단계별 가이드가 있을 때) - GEO 핵심
    if isinstance(steps, list):
        valid_steps = [s for s in steps if isinstance(s, dict) and s.get("title")]
        if valid_steps:
            article["jsonld"]["howto"] = {
                "@context": "https://schema.org",
                "@type":    "HowTo",
                "name":     title,
                "step": [
                    {
                        "@type":    "HowToStep",
                        "position": i,
                        "name":     s.get("title", ""),
                        "text":     s.get("desc", "") or s.get("title", ""),
                    }
                    for i, s in enumerate(valid_steps[:7], 1)
                ],
            }

    filepath.write_text(
        json.dumps(article, ensure_ascii=False, indent=2), encoding="utf-8"
    )

    status_label = "발행" if AUTO_PUBLISH else "임시저장"
    print(f"   [{status_label}] {filename}")
    print(f"   제목: {article['title']}")
    print(f"   카테고리: {article['category']}")
    if hero_image:
        print(f"   썸네일: {hero_image['url']} (소스: {hero_image.get('source','?')})")
    else:
        print(f"   썸네일: 없음")
    if body_images:
        ok_count = sum(1 for img in body_images if img)
        print(f"   본문이미지: {ok_count}/{len(body_images)}장")
    if article.get("faq"):
        print(f"   FAQ: {len(article['faq'])}개")
    if article.get("seo_analysis"):
        sa = article["seo_analysis"]
        print(f"   SEO: {sa['score']}점 / 월검색 {sa.get('monthly_total','?')} / 경쟁 {sa.get('competition','?')}")
    print(f"   SEO제목: {article['seo_title'][:50]}...")

    update_manifest()

    # ── sitemap.xml 자동 갱신 ──────────────────────────
    _try_update_sitemap()

    return str(filepath)


def _try_update_sitemap():
    """sitemap.xml을 자동으로 갱신합니다."""
    try:
        sitemap_script = SCRIPT_DIR / "generate_sitemap.py"
        if sitemap_script.exists():
            subprocess.run(["python", str(sitemap_script)], capture_output=True)
            print("   sitemap.xml 갱신 완료")
    except Exception as e:
        print(f"   [경고] sitemap 갱신 실패: {e}")


# ── GitHub push ───────────────────────────────────────
def git_push(success_count: int):
    print(f"\n   GitHub 업로드 중...")
    try:
        git_dir = str(BLOG_DIR)
        # posts/ 폴더 전체 (썸네일 포함) 커밋
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
BLOCKED_KEYWORDS = [
    "아이돌","배우","가수","드라마","영화","예능",
    "야구","축구","농구","배구","스포츠",
    "롯데","삼성라이온즈","두산","한화","기아","NC","KT구단","SSG",
    "선거","정치","대통령","국회","여당","야당",
    "사망","부고","사건","사고","범죄","경찰","검찰",
    "날씨","기온","강수","태풍",
]

ALLOWED_KEYWORDS = [
    # 정부지원금/정책
    "지원금","정책","장려금","보조금","바우처","수당","청년","신혼","소상공인",
    "도약계좌","내일채움","디딤돌","버팀목","행복주택","복지","공제","감면","환급",
    # AI 도구
    "Claude","ChatGPT","Gemini","Perplexity","Cursor","AI","GPT",
    "프롬프트","자동화","챗봇","n8n","Zapier","Make",
    # 직장인 커리어
    "직장인","회사원","이직","취업","연봉","승진","면접","이력서",
    "업무","퇴근","연말정산","재택근무","유연근무","자격증",
    # 재테크
    "재테크","투자","주식","ETF","ISA","IRP","연금저축","적금","예금",
    "월배당","S&P500","나스닥","TIGER","KODEX","환율","금리",
    # 부동산/주거
    "부동산","청약","전세","월세","임차","임대","DSR","LTV","취득세","양도세",
    "주택","분양","보증금",
    # 일반
    "노후","보험","절약","파이어족","경제적자유",
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
    unsplash_status = "ON" if UNSPLASH_KEY else "OFF"
    gemini_status   = "ON" if GEMINI_API_KEY else "OFF"
    ad_api_status   = "ON" if os.getenv("NAVER_AD_API_KEY") else "OFF"
    print(f"  이미지 소스  : Unsplash={unsplash_status}, Gemini폴백={gemini_status}")
    print(f"  SEO 분석     : 검색광고API={ad_api_status}")
    print(f"{'='*52}")

    # SEO 최적화 키워드 선택 (검색광고 API 있으면 사용, 없으면 기본 방식)
    if os.getenv("NAVER_AD_API_KEY"):
        try:
            keywords = get_seo_optimized_keywords()
        except Exception as e:
            print(f"   [SEO] 분석 오류 → 기본 모드 사용: {e}")
            keywords = get_keywords_for_today_with_trends()
    else:
        keywords = get_keywords_for_today_with_trends()

    success_count = 0
    for i, item in enumerate(keywords, 1):
        seo_meta = item.get("seo_meta")
        seo_info = f" [SEO {seo_meta['score']}점]" if seo_meta else ""
        print(f"\n[{i}/{len(keywords)}] {item['category']} — {item['keyword']}{seo_info}")

        # 글 생성 (SEO 메타 전달)
        article = generate_article(item["category"], item["keyword"], seo_meta)
        if not article:
            print("   글 생성 실패")
            continue

        # SEO 메타 정보를 article에 보존
        if seo_meta:
            article["seo_analysis"] = seo_meta

        # 썸네일 생성 (글 제목 사용)
        title = article.get("title", item["keyword"])
        hero_image = get_hero_image(item["category"], item["keyword"], title)

        # ── 본문 이미지 개수 결정 ──
        raw_text = article.get("content", "")
        heading_count = sum(
            1 for line in raw_text.split("\n")
            if line.strip().startswith("## ")
        )
        
        # FAQ 섹션도 있으니 이미지는 섹션 수에 맞춰 조금 더 여유 있게
        if heading_count <= 1:
            target_count = 0
        elif heading_count == 2:
            target_count = 1
        elif heading_count == 3:
            target_count = 2
        else:
            target_count = 3

        body_images = []
        if target_count > 0:
            print(f"   본문 이미지 {target_count}장 가져오는 중... (소제목 {heading_count}개 감지)")
            body_images = get_body_images(item["category"], target_count)

        # 저장
        if save_article(article, hero_image, body_images):
            success_count += 1

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
