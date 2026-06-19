# HANDOFF — 직장인 수익일기 (koreansalaryman.com)

> 다음 세션의 Claude에게: **이 문서만 읽고 전체 맥락을 잡을 수 있도록** 작성됨.
> 운영 규칙(맨 아래 §운영 규칙)을 먼저 숙지하고 시작할 것. 강제승인모드가 기본이다.

---

## 현재 버전: v3.9 (2026-06-12 ~ 06-19 세션)  *(이전: v3.8 2026-06-07~06-09 — 아래 §0~§9에 보존)*

> 이 repo 루트에 HANDOFF.md가 없어 v3.8부터 이 파일로 새로 시작함.
> v3.7 이하 이력은 백업 repo `daehongpark/blog-automation` 또는 이전 세션 기록 참조.
> 이후 세션은 이 파일에 v3.9, v4.0… 으로 섹션을 이어 쓸 것.

---

## 0. 프로젝트 한눈에

- **무엇**: 직장인 박대홍 페르소나의 부업·재테크·자기계발 블로그. 글을 **자동 생성·발행**하는 파이프라인이 핵심.
- **스택**: 정적 HTML/CSS/JS 사이트 + Python 자동화 + Vercel 호스팅 + GitHub Actions cron.
- **도메인**: https://koreansalaryman.com (Vercel, `cleanUrls: true`, `trailingSlash: false`)
- **글 데이터**: `posts/{filename}.json` (글 1편 = JSON 1개) + `posts/manifest.json` (전체 목록 인덱스)
- **글 주소**: **`/p/{한글-슬러그}.html`** (이번 세션에 전환 완료. 옛 `?id=`, `/p/post_xxx` 전부 리다이렉트)

### 핵심 파일 지도
| 파일 | 역할 |
|---|---|
| `automation.py` | 글 자동 생성 본체 (주제선정→자료조사→본문생성→SEO→썸네일→저장) |
| `trend_pipeline.py` | **신규** 실시간 트렌드 수집→주제 변환 (RSS + Gemini) |
| `generate_static_posts.py` | **신규** post.html 템플릿 기반 정적 글페이지 생성 + 슬러그 부여 + redirect stub |
| `generate_sitemap.py` | sitemap.xml 생성 (슬러그 주소) |
| `post.html` | 글 상세 **템플릿** (정적화의 원본. CSR fallback도 겸함) |
| `index.html` / `blog.html` / `category-*.html` (7개) | 목록/카테고리 페이지 (글 카드 링크 → 슬러그) |
| `posts/manifest.json` | 글 목록 + 메타 + **slug 필드(영구)** |
| `vercel.json` | redirects(옛주소→슬러그) + headers |
| `.github/workflows/daily_post.yml` | 매일 cron 자동 생성 워크플로 |
| `.github/workflows/static_rebuild.yml` | **신규** posts/*.json push 시 정적+sitemap 재생성 |

---

## 1. 색인 / sitemap (v3.8)

- `generate_sitemap.py` **BLOG_DIR 경로버그 수정** (잘못된 경로로 글을 못 읽던 문제).
- `daily_post.yml`에 **sitemap 자동 갱신 스텝** 추가 → 매일 글 생성 후 sitemap 최신화.
- GSC(구글 서치콘솔) 재제출로 **색인 증가 확인**.

## 2. admin 409 self-healing (v3.8)

- admin 패널(글 발행/삭제/예약)에서 GitHub API 충돌 대응:
  - `ghPut`/`ghDelete`가 **409/422** 받으면 **최신 sha 재조회 후 재시도(최대 5회)**.
  - `syncManifest` 전체 재시도 로직.
  - `_ghRetry`에 `skipStatuses` 추가 (특정 상태코드는 재시도 제외).
- 배경: 여러 워크플로/수동 작업이 동시에 manifest를 건드릴 때 sha 불일치로 실패하던 것.

## 3. 주제 다양성 (v3.8)

- **CATEGORY_BALANCE**: finance 30 / realestate 20 / money 15 / trending 15 / ai 10 / startup 10 / **book 0 (자동생성 금지)**.
- 시드풀 확장: money 42 / ai 38 / finance 40 / startup 30 / realestate 40 / trending 48.
- 주제 선정: `available[:20]`에서 **제곱근 가중 랜덤** (상위 주제 약간 우대하되 다양성 확보).

## 4. 트렌드 추적 시스템 ★핵심 신규 (v3.8)

### `trend_pipeline.py`
- **수집 소스**: 구글트렌드 RSS + 구글뉴스(BUSINESS/TECH/HEALTH) + 연합뉴스 경제 + 전자신문 + 정책브리핑 + 부동산 검색 RSS.
- **BLOCK_KEYWORDS** 안전필터 (정치/사건사고/자극적 주제 제외).
- **`convert_trends_to_topics`**: Gemini **2.5-flash**로 트렌드 키워드 → 블로그 주제 변환.
  - 503 백오프 3회, `maxOutputTokens: 4000` + `responseMimeType: application/json` (JSON 안정 출력).

### `automation.py` 통합
- `get_seo_optimized_keywords`에서 **트렌드 주제 사전 수집**(`trend_topics_by_cat`):
  - **이중 try/except**, 실패 시 **시드풀 100% 폴백** (트렌드 죽어도 글 생성은 계속).
- 카테고리 루프: **트렌드 우선 채택** + 의미 기반 cooldown(최근 쓴 주제 회피).
- `build_prompt`에 `trend_source`/`trend_angle` 주입 + **트렌드 도입부 훅** + **2026 GEO 블록**
  (신선도/패시지/답-먼저/수치/EEAT — **모든 글에 적용**).
- 트렌드 **주간 쿼터 7일**.

### 검증
- 로컬 풀코스에서 **트렌드 채택 3건 + 시드 폴백 + 쿼터 보충** 전부 작동 확인.
- ⚠️ RSS는 **Claude 컨테이너에선 403**(차단), **사용자 로컬/GitHub Actions(미국IP)에선 200**. → 트렌드 실제 작동 여부는 **GitHub Actions 로그로만** 최종 확인 가능 (PENDING §9).

## 5. 안정화 (v3.8)

- **본문 생성 429 처리**: `credit`/`depleted`/`quota`/`billing` 감지 시
  `RuntimeError("GEMINI_CREDITS_DEPLETED")`로 **즉시 중단**.
  - ⚠️ 구현 주의: `except RuntimeError: raise`를 **generic `except` 앞에** 둘 것 (안 그러면 generic이 먼저 잡아 무한재시도).
  - `run_daily` 전체 중단하되 **이미 생성된 글은 저장**.
- 자료조사 단계 429는 **graceful skip** (자료 없이 진행).
- `daily_post.yml`: `timeout-minutes: 90`, `actions/checkout@v5`.
- **배경**: 6/4~6/7 크레딧 소진으로 무한 hang → 워크플로 6시간 돌다 cancelled. 이걸 막는 게 목적.

## 6. 메타 정비 (v3.8)

- `index.html` **title 32자 / description 61자** 재정비, "500만원" 과장 표현 제거.
- og/twitter 메타 통일.
- ⚠️ **본문 히어로의 "월 500만원" 문구는 미정리(PENDING §9)**.

## 7. 실명 정책 (v3.8)

- 기존에 쌓인 실명/구체적 표현은 **전부 유지** (사용자 결정).
- **새로 넣지만 않는다** — 신규 글에 실명·과한 구체 수치 추가 금지.

## 8. 글 정적화 + 한글 슬러그 ★핵심 신규 (v3.8)

> **이번 세션의 메인 작업.** 배경: 글 주소가 `/post?id=xxx.json`(CSR)이라 크롤러가 빈 페이지를 봄 → SEO 치명적. 정적 HTML로 근본 해결.

### A단계 — 정적 생성기 (`generate_static_posts.py`)
- `post.html`을 **템플릿으로 읽어** 문자열/정규식 치환 (의존성 추가 없음, BeautifulSoup 안 씀).
- 치환 내용: `<title>`/description/canonical/og·twitter(id 기반)/**JSON-LD BlogPosting**(`</head>` 직전) + 본문(hero/summary/body) 정적 삽입.
- `window.__PRERENDERED__ = true` 플래그, 스켈레톤 숨김·레이아웃 표시.
- **fetch 렌더링 블록 제거**(크롤러가 완성본을 바로 봄), 조회수/공유/댓글/네비 **인터랙션 JS는 유지**.
- 한 글 실패해도 **전체 중단 안 함**(그 글만 skip).

### B단계 — 사이트 전환
- 사이트 전체 링크를 `/p/...`로 교체: blog / index(goToPost+배너+카드) / category×7(goToPost+카드) / post(이전·다음·관련글).
- sitemap 새 주소, **vercel.json 301 리다이렉트**(`/post.html`, `/post` 둘 다 — query `id`가 `.json`이면 `/p/:id.html`로).
- post.html에 **JS fallback**(vercel 실패 대비 이중 안전망).
- 자동화 연결: `daily_post.yml`에 정적 생성 스텝 + `git add ... p/`, 신규 **`static_rebuild.yml`**(`posts/**.json` push 시 정적+sitemap 재생성. paths 한정이라 자기 자신 재트리거 없음 = 무한루프 없음).

### 상대경로 404 수정
- `/p/` 하위 정적본에서 `index.html` 등 상대링크가 `/p/index.html`로 깨지던 버그.
- `generate_static_posts.py`에 **절대경로화** 단계: REL_PAGES 8종(`index/blog/about/class/challenge/income/privacy/terms.html`) + manifest fetch(작은/큰따옴표/백틱).

### 한글 슬러그 전환 (최종 형태)
- **`/p/post_20260607_223830.html` → `/p/2026-고환율-시대-직장인-해외-자산-관리와-환테크-전략-5단계.html`**
- `make_slug(title, existing)`: NFC 정규화 → 특수문자 제거(`[^\w가-힣\s-]`) → 공백→하이픈 → 50자 → 중복 시 `-2`.
- **slug는 `manifest.json`에 영구 저장** (한 번 정해지면 불변).
- **self-healing**: `generate_static_posts.py`가 slug 없는 published 발견 시 자동 부여 후 manifest 저장 → **automation.py 수정 불필요, 새 글 자동 커버**.
- 옛 `/p/post_xxx.html` 자리엔 **리다이렉트 stub**(canonical + meta refresh + JS replace)로 슬러그 주소 이동 (공유/크롤 링크 보존).
- `?id=` fallback도 **manifest 조회 후 슬러그로** 이동(못 찾으면 stub이 받음 — 체인).
- 사이트 링크 전부 **slug 기반**: `encodeURIComponent(p.slug || p.filename.replace(/\.json$/,''))}.html`. sitemap도 슬러그.
- `static_rebuild.yml` git add에 **`posts/manifest.json` 포함**(새 slug 영구 저장 보장).
- ⚠️ **`postId`(조회수/댓글 localStorage 키)는 filename 유지** — 주소 바뀌어도 기존 조회수/댓글 데이터 보존.

### 현재 상태
- published 102편(세션 종료 시점) 전부 슬러그 페이지 + stub 생성 완료. sitemap 102 슬러그 URL.
- 커밋: `305fdf6`(A) → `b64b665`(B) → `9f8203a`(상대경로) → `1b7e553`(슬러그).

---

## 9. PENDING (다음 세션 할 일)

1. **다음 자동 run 로그 검증** (GitHub Actions): 로그에서 아래 확인
   - `[트렌드] … 확보` / `✓ [트렌드 채택]` → GitHub Actions 미국IP에서 RSS 200으로 트렌드가 실제로 붙는지.
   - `⏱ 글 생성 N초` → **속도 병목 진단**(글당 ~12분이면 느림). 5편이면 timeout 90분에 빠듯한지.
2. **사용자가 GSC + 네이버 sitemap 재제출** (슬러그 주소 기준). → 색인 갈아끼우기.
3. **본문 히어로 "월 500만원" 문구 정리 여부** 결정 (index 메타는 정리됨, 본문 히어로는 미정).
4. **영어 콘텐츠 프로젝트**: 외국인 대상 한국 직장문화 글. **서브도메인 또는 무료도메인의 별도 사이트**로 결정됨(본진 SEO와 격리). 아이디어 개발 예정 — 아직 착수 안 함.

---

# ═══════════════════════════════════════════
# v3.9 (2026-06-12 ~ 06-19 세션)
# ═══════════════════════════════════════════

> v3.8 §9 PENDING 처리 결과: 1번(트렌드 로그 검증)→v3.9 §1에서 처리, 2번(GSC/sitemap 재제출)→§4 진행 중, 4번(영어 프로젝트)→별도 repo로 분리(§7). 3번(히어로 "월 500만원")은 여전히 미정 → v3.9 PENDING 유지.

## v3.9-1. 트렌드 시스템 안정화 ★핵심
- **Gemini 2.5-flash 503 'high demand' 스파이크가 변환 단계를 죽여 트렌드 0 채택**이던 것 수정: 재시도 **5회 + 백오프 45초**, `thinkingBudget 0`.
- **silent 폴백 제거** → 폴백 사유를 단계별 로그로 노출 (뉴스 0건 / 변환 0개 / 쿨다운).
- `trend_source` / `trend_angle`를 글 JSON에 **영속화** (추적 버그 수정).
- **AI 전용 뉴스 RSS 추가** (소스 8 → 28건).
- 결과: 최근 트렌드 채택률 회복 (시드 : 트렌드 혼합). 관련 커밋 `5d3c8bc`(우선채택/max5/전카테고리).

## v3.9-2. 시드풀 대청소 + 콘텐츠 품질
- AI 입문/올드툴(ChatGPT 입문, Zapier, MAKE 등) **전부 제거** → 비교/큐레이션/최신 30개로 교체.
- realestate 정책 나열 축소, **실전형**(무순위청약/가점계산 등) 41개.
- **제목 '2026' 강제 제거** — `prompt_template.json`이 주범(92% 도배였음). 커밋 `5d3c8bc`.
- `build_prompt` 가드: 입문 개념설명·'~란' 금지, **비교/실전 우선**.

## v3.9-3. 주제 반복 방지
- **TOPIC_GROUPS**: 연말정산·절세 / 청약·대출 / 세금·신고(종소세·부가세) 그룹화.
- **GROUP_COOLDOWN**: **14편 ∪ 45일** (기존 라벨 단위 7편·실제 7일이라 월 단위 반복을 못 잡던 것 수정). 커밋 `aaf6da5`(세금·신고 그룹 추가).
- **`_has_strong_overlap`**: 제목 핵심토큰 **3개+ 겹침** 회피.

## v3.9-4. 색인 가속 (SEO)
- **한글 슬러그 URL 전환 완료** (`/p/한글-제목.html`).
- **`archive.html` 신설**: 전 글 정적 HTML 링크 = **크롤러 진입점** (blog/index가 JS 렌더라 크롤러가 글을 발견 못하던 문제 해소). 커밋 `ab9ca2e`.
- **admin '색인주소 복사' 버튼 3종**: 한글 디코딩 상태로 복사 → GSC 인코딩 오류 회피. 커밋 `7c6982d`.
- **GSC 현황**: sitemap 제출은 성공이나 신규+주소변경으로 크롤 지연 → **매일 수동 색인요청 10개 루틴** 운영 중.

## v3.9-5. 워크플로 안정화
- **static_rebuild / daily_post push 레이스 수정**: concurrency 직렬화 + pull-rebase 5회 재시도 (실전 검증됨). 커밋 `ee9acc7`.
- **cron apt(한글폰트) hang으로 6/19 글 누락** → 폰트설치 스텝 **timeout 6분 + 재시도 3회 + continue-on-error** (automation.py는 폰트 없으면 기본폰트 폴백, line 900-905). 커밋 `38f7334`.
- **★ 본진 `_already_ran_today()`는 KST 기준 유지.** EN repo와 cron 타이밍이 **반대**(본진=22:30 UTC 생성 + 00:17/00:47 UTC 폴백, UTC 자정 가로지르되 같은 KST날). **UTC로 바꾸면 폴백이 중복 발행** → EN의 81a62d0(KST→UTC) 패치는 **본진에 적용 금지** (시뮬레이션으로 확정).

## v3.9-6. 뉴스레터
- **Supascribe 임베드**로 구독 연결 (Substack 직접호출 / Vercel 프록시 둘 다 **403 차단**됨). 커밋 `9f425f9` → `4bd1f95` → `4da2cd1`.
- 본진 임베드 **id: 938473434490**, 로더 `js.supascribe.com`.
- `handleSubscribe` / api 프록시 **죽은 코드 제거**.

## v3.9-7. 영어 사이트 = 별도 repo
- **`daehongpark/korean-salaryman-en`** (외국인 대상 한국 직장문화). 본진 SEO와 격리. 상세는 **EN HANDOFF v2.0** 참조.

---

## 9b. PENDING (v3.9 이후 — 다음 세션 할 일)

1. **본진 뉴스레터 구독 실테스트** — Supascribe 통해 구독 시 Substack 명단에 실제로 뜨는지 확인 + Supascribe 폼 디자인 커스텀.
2. **양쪽 Vercel Redeploy** — 예약발행 SECRET 반영.
3. **6/19 폴백 cron 글 생성 확인** — 폰트 hang 수정 후 폴백 cron이 6/19분을 실제로 생성했는지.
4. **GSC 색인 추이 관찰** — archive.html + 한글 슬러그 효과.
5. **본문 히어로 "월 500만원" 정리 여부** — 여전히 미정 (v3.8부터 이월).

---

## 운영 규칙 (매 세션 리마인드)

- **강제승인모드가 기본** — 사용자가 "강제승인"이라 하면 작업을 한 방에 끝까지 진행. 중간에 묻지 않는다.
- **먼저 묻지 않기** — 합리적 기본값으로 진행하고 결과 보고. 질문은 정말 갈리는 지점만.
- **시간/컨디션 추정 금지** — "오래 걸린다", "피곤하실 텐데" 류 추정 안 함.
- **추측 말고 데이터 확인** — 코드/로그/실제 파일을 보고 판단. 모르면 확인.
- **실명 새로 넣지 않기** — 기존 건 유지, 신규 추가 금지(§7).
- **검증 필수** — 작업 후 반드시 검증 스크립트로 통과 확인하고 보고.
- **경로**:
  - 회사 PC: `C:\Users\ENS\Desktop\ddaehong\korean-salaryman-blog` (git lock 걸리면 `.git/*.lock` 삭제)
  - 집 PC: `C:\Users\pride\OneDrive\Desktop\korean-salaryman-blog`
- **비용**: 월 **1만원 한도**. (Gemini API 등)
- **push 충돌 잦음** — 자동화 워크플로가 수시로 원격을 갱신함. push 거부 시 `git pull --rebase` 후 충돌(주로 sitemap.xml/manifest.json)은 **재생성으로 해소**(generate_static_posts.py + generate_sitemap.py 돌리면 self-healing).

---

*v3.9 작성 완료. 다음 세션은 §9b PENDING(v3.9 이후)부터.*
