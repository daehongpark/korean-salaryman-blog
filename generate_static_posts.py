# -*- coding: utf-8 -*-
"""
글 정적화 A단계 — 정적 HTML 생성기.

post.html 을 템플릿으로 읽어, posts/manifest.json 의 status=published 글마다
/p/{id}.html 정적 페이지를 생성한다. (CSR fetch 렌더링 → 크롤러가 완성본을 바로 봄)

- 메타태그(title/description/og/twitter/canonical) 정적 치환
- JSON-LD BlogPosting 정적 삽입
- 본문 콘텐츠(hero/summary/body) 정적 삽입
- post.html 의 fetch 렌더링 블록 제거, 인터랙션 JS(조회수/공유/댓글/네비) 유지

의존성 추가 없음 (표준 라이브러리 + 정규식 문자열 치환만).
사이트 링크 교체/sitemap/리다이렉트/자동화 연결은 B단계.
"""
import json
import re
import math
import html
import os
from datetime import datetime

ROOT = os.path.dirname(os.path.abspath(__file__))
TEMPLATE_PATH = os.path.join(ROOT, "post.html")
MANIFEST_PATH = os.path.join(ROOT, "posts", "manifest.json")
POSTS_DIR = os.path.join(ROOT, "posts")
OUT_DIR = os.path.join(ROOT, "p")
SITE = "https://koreansalaryman.com"


def esc_attr(s):
    """HTML 속성값용 이스케이프."""
    return html.escape(str(s or ""), quote=True)


def esc_text(s):
    """HTML 텍스트 노드용 이스케이프."""
    return html.escape(str(s or ""), quote=False)


def set_attr_by_id(doc, elem_id, attr, value):
    """id 로 태그를 찾아 attr="..." 를 value 로 치환 (정규식, 1회)."""
    tag_re = re.compile(r'<[^>]*\bid="' + re.escape(elem_id) + r'"[^>]*>')

    def repl_tag(m):
        tag = m.group(0)
        attr_re = re.compile(r'\b' + re.escape(attr) + r'="[^"]*"')
        if attr_re.search(tag):
            return attr_re.sub(lambda _: attr + '="' + value + '"', tag, count=1)
        # 속성이 없으면 닫는 > 앞에 삽입
        return tag[:-1] + ' ' + attr + '="' + value + '">'

    return tag_re.sub(repl_tag, doc, count=1)


def format_date_kr(iso):
    """JS formatDate 와 동일: YYYY년 M월 D일."""
    if not iso:
        return ""
    try:
        d = datetime.fromisoformat(iso)
    except ValueError:
        try:
            d = datetime.fromisoformat(iso.split(".")[0])
        except Exception:
            return ""
    return "%d년 %d월 %d일" % (d.year, d.month, d.day)


def read_time(content):
    """JS readTime 와 동일: max(1, ceil(len/500)) + '분'."""
    return "%d분" % max(1, math.ceil(len(content or "") / 500))


def text_to_html(text):
    """JS textToHtml 폴백: 빈 줄 기준 단락 분리."""
    parts = re.split(r"\n\n+", text or "")
    out = []
    for p in parts:
        p = p.strip()
        if p:
            out.append("<p>" + p.replace("\n", "<br>") + "</p>")
    return "".join(out)


# ── 정적 인터랙션 init (fetch 렌더링 블록 대체) ──────────────────
# 조회수/댓글/이전다음/관련글만 manifest 기반으로 동작. 본문은 이미 정적 렌더됨.
# 주의: manifest fetch 는 작은따옴표 사용 (백틱 fetch 제거 검증과 무관).
STATIC_INIT = """// ── 정적 프리렌더 페이지: 인터랙션만 초기화 (fetch 렌더링 제거됨) ──
const postId = "%(filename)s";
updateViewCount(postId);
renderComments(postId);

fetch('./posts/manifest.json')
  .then(r => r.json())
  .then(manifest => {
    renderPostNav(manifest, postId);
    const currentCat = "%(category)s";
    const related = manifest
      .filter(p => p.status === 'published' && p.filename !== postId && p.category === currentCat)
      .slice(0, 4);
    const relBox = document.getElementById('relatedPosts');
    if (relBox) {
      if (related.length === 0) {
        relBox.innerHTML = '<p style="font-size:13px;color:var(--text3);">관련 글이 없습니다.</p>';
      } else {
        relBox.innerHTML = related.map(p => `
          <a class="rel-item" href="post.html?id=${encodeURIComponent(p.filename)}">
            <div class="rel-dot"></div>
            <div>
              <div class="rel-title">${p.title}</div>
              <div class="rel-cat">${formatDate(p.created_at)}</div>
            </div>
          </a>`).join('');
      }
    }
  })
  .catch(err => console.error(err));
"""


def build_page(template, post, filename, manifest_entry):
    pid = filename[:-5] if filename.endswith(".json") else filename  # .json 제거
    title = post.get("title") or ""
    category = post.get("category") or ""
    created = post.get("created_at") or ""
    summary = post.get("summary") or ""
    tags = post.get("tags") or []
    content = post.get("content") or ""

    page_url = "%s/p/%s.html" % (SITE, pid)

    # ── pageTitle / pageDesc (post.html JS 로직과 동일) ──
    page_title = post.get("seo_title") or ("%s | 직장인 수익일기" % title)
    if post.get("seo_description"):
        page_desc = post["seo_description"]
    elif summary:
        page_desc = summary[:150].replace("\n", " ") + " | 직장인 수익일기"
    else:
        page_desc = "직장인 박대홍의 %s 현실 이야기. 직장인 수익일기에서 읽어보세요." % (category or "부업")

    # ── og:image (manifest thumbnail → hero_image.url) ──
    thumb = (manifest_entry or {}).get("thumbnail")
    if not thumb:
        hero = post.get("hero_image")
        if isinstance(hero, dict):
            thumb = hero.get("url")
    og_image = (SITE + thumb) if thumb else None

    doc = template

    # 1) <title>
    doc = doc.replace(
        "<title>직장인 수익일기</title>",
        "<title>%s</title>" % esc_text(page_title),
        1,
    )

    # 2) meta description (id 없음 → 정규식)
    doc = re.sub(
        r'<meta name="description" content="[^"]*">',
        lambda _: '<meta name="description" content="%s">' % esc_attr(page_desc),
        doc,
        count=1,
    )

    # 3) canonical href
    doc = set_attr_by_id(doc, "canonicalTag", "href", esc_attr(page_url))

    # 4) og / twitter 메타 (id 기반)
    doc = set_attr_by_id(doc, "ogTitle", "content", esc_attr(page_title))
    doc = set_attr_by_id(doc, "ogDesc", "content", esc_attr(page_desc))
    doc = set_attr_by_id(doc, "ogUrl", "content", esc_attr(page_url))
    doc = set_attr_by_id(doc, "ogPublished", "content", esc_attr(created))
    doc = set_attr_by_id(doc, "ogSection", "content", esc_attr(category))
    doc = set_attr_by_id(doc, "twTitle", "content", esc_attr(page_title))
    doc = set_attr_by_id(doc, "twDesc", "content", esc_attr(page_desc))
    if og_image:
        doc = set_attr_by_id(doc, "ogImage", "content", esc_attr(og_image))
        doc = set_attr_by_id(doc, "twImage", "content", esc_attr(og_image))

    # 5) JSON-LD BlogPosting (post.html JS 구조와 동일) → </head> 직전 삽입
    json_ld = {
        "@context": "https://schema.org",
        "@type": "BlogPosting",
        "headline": title,
        "description": page_desc,
        "url": page_url,
        "datePublished": created,
        "dateModified": created,
        "author": {
            "@type": "Person",
            "name": "박대홍",
            "url": "https://koreansalaryman.com/about.html",
        },
        "publisher": {
            "@type": "Organization",
            "name": "직장인 수익일기",
            "url": "https://koreansalaryman.com",
        },
        "keywords": ", ".join(tags),
        "articleSection": category,
        "inLanguage": "ko-KR",
        "mainEntityOfPage": {"@type": "WebPage", "@id": page_url},
    }
    ld_json = json.dumps(json_ld, ensure_ascii=False).replace("</", "<\\/")
    ld_block = '<script type="application/ld+json">%s</script>\n</head>' % ld_json
    doc = doc.replace("</head>", ld_block, 1)

    # 6) __PRERENDERED__ 플래그 (본문 데이터 직전)
    doc = doc.replace(
        '<div id="postHero" class="post-hero" style="display:none">',
        '<script>window.__PRERENDERED__ = true;</script>\n'
        '<div id="postHero" class="post-hero" style="display:block">',
        1,
    )

    # 7) 스켈레톤 숨김
    doc = doc.replace(
        '<div id="loadingSkeleton" style="max-width:1080px;margin:40px auto;padding:0 24px;">',
        '<div id="loadingSkeleton" style="max-width:1080px;margin:40px auto;padding:0 24px;display:none;">',
        1,
    )

    # 8) postLayout 표시
    doc = doc.replace(
        '<div id="postLayout" class="post-layout" style="display:none">',
        '<div id="postLayout" class="post-layout" style="display:grid">',
        1,
    )

    # 9) hero 채우기
    doc = doc.replace(
        '<span id="heroCat"></span>',
        '<span id="heroCat">%s</span>' % esc_text(category), 1)
    doc = doc.replace(
        '<div id="heroCatPill" class="post-cat-pill"></div>',
        '<div id="heroCatPill" class="post-cat-pill">%s</div>' % esc_text(category), 1)
    doc = doc.replace(
        '<h1 id="heroTitle"></h1>',
        '<h1 id="heroTitle">%s</h1>' % esc_text(title), 1)
    doc = doc.replace(
        '<span class="post-meta-info" id="heroDate"></span>',
        '<span class="post-meta-info" id="heroDate">%s</span>' % esc_text(format_date_kr(created)), 1)
    doc = doc.replace(
        '<span class="post-meta-info" id="heroReadTime"></span>',
        '<span class="post-meta-info" id="heroReadTime">읽는 시간 %s</span>' % esc_text(read_time(content)), 1)

    # 10) 요약
    if summary:
        summary_html = ('<div class="article-summary" id="articleSummary">'
                        '<div class="article-summary-label">SUMMARY</div>'
                        '<p>%s</p></div>') % summary.replace("\n", "<br>")
        doc = doc.replace(
            '<div class="article-summary" id="articleSummary"></div>', summary_html, 1)
    else:
        doc = doc.replace(
            '<div class="article-summary" id="articleSummary"></div>',
            '<div class="article-summary" id="articleSummary" style="display:none"></div>', 1)

    # 11) 본문 (HTML 이면 그대로, 아니면 textToHtml 폴백)
    if content.strip().startswith("<"):
        body_html = content
    else:
        body_html = text_to_html(content)
    doc = doc.replace(
        '<div class="article-body" id="articleBody"></div>',
        '<div class="article-body" id="articleBody">%s</div>' % body_html, 1)

    # 12) submitComment 의 postId 추출을 전역 postId 로 (정적 페이지엔 ?id= 없음)
    doc = doc.replace(
        "  const postId = new URLSearchParams(window.location.search).get('id');",
        "  // postId 는 정적으로 주입됨 (전역 사용)", 1)

    # 13) fetch 렌더링 실행 블록 제거 → 정적 init 으로 교체
    marker = "// URL 파라미터에서 포스트 ID 추출"
    mi = doc.find(marker)
    if mi == -1:
        raise RuntimeError("fetch 렌더링 마커를 찾지 못함")
    si = doc.find("</script>", mi)
    if si == -1:
        raise RuntimeError("</script> 종료 태그를 찾지 못함")
    init_js = STATIC_INIT % {"filename": filename, "category": esc_attr(category)}
    doc = doc[:mi] + init_js + doc[si:]

    return pid, doc


def main():
    with open(TEMPLATE_PATH, encoding="utf-8") as f:
        template = f.read()
    with open(MANIFEST_PATH, encoding="utf-8") as f:
        manifest = json.load(f)

    by_name = {m["filename"]: m for m in manifest}
    published = [m for m in manifest if m.get("status") == "published"]

    os.makedirs(OUT_DIR, exist_ok=True)

    generated = skipped = failed = 0
    fail_list = []
    for entry in published:
        filename = entry["filename"]
        path = os.path.join(POSTS_DIR, filename)
        if not os.path.exists(path):
            skipped += 1
            print("SKIP (파일 없음):", filename)
            continue
        try:
            with open(path, encoding="utf-8") as f:
                post = json.load(f)
            pid, doc = build_page(template, post, filename, by_name.get(filename))
            out_path = os.path.join(OUT_DIR, pid + ".html")
            with open(out_path, "w", encoding="utf-8") as f:
                f.write(doc)
            generated += 1
        except Exception as e:  # 한 글 실패해도 전체 중단 X
            failed += 1
            fail_list.append((filename, str(e)))
            print("FAIL:", filename, "->", e)

    print("\n=== 정적 생성 결과 ===")
    print("published 대상:", len(published))
    print("생성:", generated)
    print("스킵:", skipped)
    print("실패:", failed)
    if fail_list:
        print("실패 목록:")
        for fn, err in fail_list:
            print("  -", fn, ":", err)


if __name__ == "__main__":
    main()
