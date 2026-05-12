# 네이버 변형 통합 — 박대홍님 액션 안내

5/10 피드백 4번(네이버 변형 4문제) Option D 풀버전 통합 작업이 끝났습니다. 다음 두 가지만 확인하시면 됩니다.

---

## 1. Vercel 환경변수 확인

Vercel 대시보드 → 프로젝트 → Settings → Environment Variables에 아래가 박혀있어야 합니다. 이미 자동화(cron) 돌고 있으니 대부분 있을 거예요.

| 변수명 | 용도 | 필수여부 |
| --- | --- | --- |
| `GEMINI_API_KEY` | 본문/제목/AEO 필드 생성 | ✅ 필수 |
| `UNSPLASH_ACCESS_KEY` | 본문 이미지(Unsplash) | ⚠️ 권장 (없으면 사진 0장) |
| `BLOG_TITLE` | "직장인 수익일기" 브랜드 | 선택 (기본값 동작) |
| `AUTO_PUBLISH` | 자동 발행 여부 | 선택 (네이버 변형은 항상 draft) |
| `NAVER_AD_API_KEY` | SEO 키워드 분석 (cron만) | 선택 — 네이버 변형 무관 |

**확인 방법:** Vercel 대시보드에서 Environment Variables 페이지 들어가서 위 키들 있나 보세요. `UNSPLASH_ACCESS_KEY`만 없으면 추가하시면 됩니다(없으면 본문 이미지가 안 박혀요).

---

## 2. 동작 확인 (네이버 글 1편 테스트)

1. push 후 Vercel 빌드 완료 기다리기 (대시보드에서 Deployments 탭 → 초록불 확인)
2. https://koreansalaryman.com/admin.html 접속
3. "📥 네이버 글 변형" 모달 열기
4. 네이버 블로그 글 1편 본문 통째로 붙여넣기 + 카테고리 선택
5. "🔄 변환하기" 클릭
   - Gemini 변형 중 (~30초)
   - 이미지·HTML 조립 중 (~15초, Unsplash 호출)
6. 미리보기에 다음이 박혀있나 확인:
   - 제목 / 요약 OK
   - 보강 통계: `🖼 히어로 이미지: ✓ · 본문 이미지: 2장 · FAQ: 5개 · 차트: bar …`
   - 본문 미리보기에 마크다운 `##` 헤더가 보이면 OK (HTML 변환은 저장 시점에 이미 끝남)
7. "💾 draft로 저장" 클릭 → 어드민 목록에서 새 글 확인
8. 어드민에서 미리보기 → 다음 4가지 확인:
   - 이모티콘/광고체 표현 사라졌는지
   - `##` / `***` 같은 raw 마크다운이 노출되지 않는지 (모두 HTML 변환)
   - TL;DR 박스 / FAQ 섹션 / 차트 / 참고자료 박스 모두 보이는지
   - 히어로 이미지 + 본문 이미지가 박혀있는지

---

## 3. 변경된 흐름 한눈에

```
[admin.html] convertNaverPost
  ↓ POST /api/generate-post { mode:'naver_transform', original_text, category }
[api/generate-post.js] mode 분기 → prompt_template.json 재사용 → Gemini
  ↑ parsed JSON (title/category/summary/content/tldr/comparison_table/steps/faq/references/chart/tags)
[admin.html] /api/finalize-post 호출
  ↓ POST { article: parsed }
[api/finalize-post.py] automation.finalize_article(article)
  ├─ get_hero_image() — Pillow + Unsplash
  ├─ get_body_images() — Unsplash
  ├─ content_to_html() — 마크다운 → HTML
  ├─ _build_tldr / audience / comparison / chart / steps / faq / refs_html
  └─ seo_title / seo_description / seo_keywords / jsonld
  ↑ 완성된 article (자동화 출력과 동일 형식)
[admin.html] saveNaverDraft → ghPut + syncManifest
```

**단일 진실 소스 보장:** cron · 직접 글 요청 · 네이버 변형 — 3개 경로 모두 `prompt_template.json` + `automation.finalize_article` 동일 인프라.

---

## 4. 문제 발생 시 디버깅

- **Gemini 응답이 깨졌다**: admin에서 "JSON 파싱 실패" 토스트 → 한 번 더 시도
- **이미지가 안 박힌다**: Vercel `UNSPLASH_ACCESS_KEY` 없을 때 → 대시보드에서 추가
- **finalize-post가 timeout (60s)**: `_compose_thumbnail`이 느린 경우. Pillow 폰트 다운로드가 걸린 거면 다음 호출엔 캐시 적용
- **Vercel 빌드 실패**: `requirements.txt`에 `Pillow / python-dotenv` 추가됨 → 빌드 로그에서 install 성공 확인

---

## 5. 추가 작업 안 한 것 (의도적)

- **A/B 테스트**: 네이버 변형 1편 돌려보고 결과 좋으면 OK
- **재시도 로직**: Gemini 1회 호출 실패 시 사용자가 직접 다시 누름 (자동 재시도 X — 의도)
- **백업**: `buildNaverConvertPrompt` 제거됨. 이전 인라인 프롬프트는 git history에 보존

문의나 막히는 점 있으면 알려주세요.
