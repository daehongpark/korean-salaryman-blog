"""
generate_sitemap.py
───────────────────
posts/manifest.json을 읽어 sitemap.xml을 자동 생성합니다.
automation.py 실행 후 자동 호출하거나 단독 실행 가능.

실행: python generate_sitemap.py
"""

import json
from pathlib import Path
from datetime import datetime

# ── 설정 ──────────────────────────────────────────────
BASE_URL   = "https://koreansalaryman.com"
SCRIPT_DIR = Path(__file__).parent
BLOG_DIR   = SCRIPT_DIR.parent / "korean-salaryman-blog"
MANIFEST   = BLOG_DIR / "posts" / "manifest.json"
OUTPUT     = BLOG_DIR / "sitemap.xml"

# 고정 페이지 (priority, changefreq)
STATIC_PAGES = [
    ("",               "1.0",  "daily"),
    ("blog.html",      "0.95", "daily"),
    ("about.html",     "0.8",  "monthly"),
    ("income.html",    "0.9",  "weekly"),
    ("challenge.html", "0.9",  "weekly"),
    ("class.html",     "0.8",  "monthly"),
]

# 7개 카테고리 페이지 (영문 키 기반)
CATEGORY_PAGES = [
    "category-money.html",
    "category-ai.html",
    "category-startup.html",
    "category-finance.html",
    "category-realestate.html",
    "category-trending.html",
    "category-book.html",
]


def generate_sitemap():
    today = datetime.now().strftime("%Y-%m-%d")

    urls = []

    # 고정 페이지
    for path, priority, changefreq in STATIC_PAGES:
        url = f"{BASE_URL}/{path}"
        urls.append(f"""  <url>
    <loc>{url}</loc>
    <lastmod>{today}</lastmod>
    <changefreq>{changefreq}</changefreq>
    <priority>{priority}</priority>
  </url>""")

    # 카테고리 페이지 (7개)
    for path in CATEGORY_PAGES:
        url = f"{BASE_URL}/{path}"
        urls.append(f"""  <url>
    <loc>{url}</loc>
    <lastmod>{today}</lastmod>
    <changefreq>weekly</changefreq>
    <priority>0.85</priority>
  </url>""")

    # 발행된 글 페이지
    if MANIFEST.exists():
        try:
            posts = json.loads(MANIFEST.read_text(encoding="utf-8"))
            published = [p for p in posts if p.get("status") == "published"]
            print(f"  발행된 글: {len(published)}개")

            for post in published:
                filename = post.get("filename", "")
                if not filename:
                    continue
                date = (post.get("created_at") or today)[:10]
                slug = post.get("slug")
                loc  = f"{BASE_URL}/p/{slug}.html" if slug else f"{BASE_URL}/p/{filename.replace('.json', '.html')}"
                urls.append(f"""  <url>
    <loc>{loc}</loc>
    <lastmod>{date}</lastmod>
    <changefreq>monthly</changefreq>
    <priority>0.7</priority>
  </url>""")
        except Exception as e:
            print(f"  [경고] manifest 읽기 실패: {e}")
    else:
        print("  [경고] manifest.json 없음 — 정적 페이지만 포함")

    sitemap = f"""<?xml version="1.0" encoding="UTF-8"?>
<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9"
        xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
        xsi:schemaLocation="http://www.sitemaps.org/schemas/sitemap/0.9
        http://www.sitemaps.org/schemas/sitemap/0.9/sitemap.xsd">

{chr(10).join(urls)}

</urlset>"""

    OUTPUT.write_text(sitemap, encoding="utf-8")
    print(f"  sitemap.xml 생성 완료: {len(urls)}개 URL")
    print(f"  저장 위치: {OUTPUT}")
    return len(urls)


if __name__ == "__main__":
    print(f"\n{'='*48}")
    print(f"  sitemap.xml 생성 시작")
    print(f"{'='*48}")
    count = generate_sitemap()
    print(f"\n  완료! 총 {count}개 URL 포함")
    print(f"  → Google Search Console에 제출: {BASE_URL}/sitemap.xml")
    print(f"{'='*48}\n")
