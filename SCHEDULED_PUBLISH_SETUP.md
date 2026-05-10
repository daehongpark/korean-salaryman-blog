# 예약 발행 시스템 설정

이 문서는 **박대홍님 직접 작업**이 필요한 항목을 정리합니다.
배포된 코드만으로는 작동하지 않으니, 아래 3단계를 반드시 완료해주세요.

## 작동 흐름

1. 박대홍님이 어드민에서 글에 ⏰ 예약 버튼 클릭 → 날짜/시간 선택
2. 글 파일에 `status: "scheduled"` + `scheduled_at: "..."` 저장됨
3. GitHub Actions가 매 30분(`*/30 * * * *`)마다 `koreansalaryman.com/api/scheduled-publish` 호출
4. 해당 endpoint가 manifest 스캔 → `scheduled_at <= now`인 글을 `published`로 전환
5. 사이트(index/blog/category 페이지)는 `status === 'published'`만 노출

## 1단계: Vercel 환경변수 추가

1. Vercel 대시보드 → `korean-salaryman-blog` 프로젝트
2. **Settings → Environment Variables**
3. 다음 두 개 추가 (Production 환경에 적용):

| Name                       | Value                                           |
|----------------------------|-------------------------------------------------|
| `GH_PAT`                   | GitHub Personal Access Token (repo scope 필수) |
| `SCHEDULED_PUBLISH_SECRET` | 임의의 긴 랜덤 문자열 (30자 이상 권장)         |

`GH_PAT` 발급:
- https://github.com/settings/tokens → "Generate new token (classic)"
- Scope: `repo` (전체) 체크
- 만료일은 길게 (90일~1년)

`SCHEDULED_PUBLISH_SECRET` 생성 예 (PowerShell):
```powershell
-join ((48..57)+(65..90)+(97..122) | Get-Random -Count 40 | % {[char]$_})
```

## 2단계: GitHub Secrets 추가

1. https://github.com/daehongpark/korean-salaryman-blog/settings/secrets/actions
2. **New repository secret**
3. Name: `SCHEDULED_PUBLISH_SECRET`
   Value: **1단계에서 Vercel에 입력한 값과 정확히 동일하게**

## 3단계: 작동 확인

1. Vercel 환경변수 추가 후 재배포가 자동으로 트리거됨 (또는 수동 redeploy)
2. 어드민에서 글 1편을 약 5~10분 후로 예약
3. 30분 안에 published로 자동 전환되는지 확인
4. GitHub Actions 로그: https://github.com/daehongpark/korean-salaryman-blog/actions/workflows/scheduled_publish.yml

수동 테스트(curl):
```bash
curl -X POST https://koreansalaryman.com/api/scheduled-publish \
  -H "x-publish-secret: <1단계에서 입력한 값>" \
  -H "Content-Type: application/json"
```

응답 예시:
```json
{ "message": "Published 1 scheduled posts", "count": 1, "published": ["post_xxx.json"] }
```

## 트러블슈팅

- **401 Unauthorized**: GitHub Secrets와 Vercel 환경변수의 `SCHEDULED_PUBLISH_SECRET` 값이 다름
- **500 Server error / GH_PAT not configured**: Vercel 환경변수 누락 또는 재배포 안 함
- **글이 발행 안 됨**: scheduled_at이 미래거나, manifest의 status가 'scheduled'가 아님
- **30분 이상 지연**: GitHub Actions cron은 정각에 스킵될 수 있음 (1차 0분, 폴백 30분 분산되어 있음)

## 보안 메모

- `SCHEDULED_PUBLISH_SECRET`은 GitHub Secrets와 Vercel 환경변수에만 저장. 코드/문서에 절대 박지 말 것.
- `GH_PAT`은 repo scope만 부여. 만료 시 재발급 후 두 곳 모두 갱신.
- endpoint는 GET/POST 모두 받지만, secret 없으면 401. 공개 노출돼도 인증 통과 못 함.
