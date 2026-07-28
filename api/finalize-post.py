"""Vercel Python serverless: article에 이미지/HTML/SEO 메타를 추가한다.

automation.finalize_article을 호출해 단일 진실 소스를 유지한다.
cron, 직접 글 요청, 네이버 변형, 후보 큐 픽 — admin의 모든 생성 경로가 같은 인프라를 쓴다.

이미지(히어로 썸네일 / 본문 이미지)도 automation.py의 생성 로직을 그대로 재사용한다.
- 본문 이미지는 Unsplash URL만 다루고 디스크에 아무것도 안 쓰므로 그대로 재사용 가능.
- 히어로 썸네일은 원래 로컬 디스크(posts/thumbnails/)에 PNG로 저장하는 함수(get_hero_image)를
  쓰는데, Vercel 서버리스는 요청 간 파일시스템이 휘발되어 그 경로는 못 쓴다. 대신
  build_hero_image_bytes()로 같은 합성(Unsplash/Gemini/그라데이션 폴백 + 제목 오버레이)을
  메모리에서만 하고 PNG 바이트를 base64로 응답에 실어 보낸다. 실제 커밋(posts/thumbnails/에
  파일로 남기는 것)은 호출자(admin.html)가 GitHub Contents API로 직접 한다.

이미지 생성이 실패해도(UNSPLASH_ACCESS_KEY 없음, 네트워크 오류 등) 전체 finalize는 죽지
않는다 — 실패한 이미지는 조용히 빠지고 나머지 글 필드는 정상 반환한다.
"""

from http.server import BaseHTTPRequestHandler
import base64
import json
import os
import sys
import traceback

# repo 루트를 PYTHONPATH에 추가해서 automation 모듈을 import 가능하게 한다.
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


class handler(BaseHTTPRequestHandler):
    def _set_cors(self):
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Access-Control-Allow-Methods", "POST, OPTIONS")
        self.send_header("Access-Control-Allow-Headers", "Content-Type")

    def _send_json(self, status, payload):
        self.send_response(status)
        self._set_cors()
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.end_headers()
        self.wfile.write(json.dumps(payload, ensure_ascii=False).encode("utf-8"))

    def do_OPTIONS(self):
        self.send_response(200)
        self._set_cors()
        self.end_headers()

    def do_POST(self):
        try:
            content_length = int(self.headers.get("Content-Length", 0))
            body = self.rfile.read(content_length).decode("utf-8")
            data = json.loads(body)

            article = data.get("article")
            if not article or not isinstance(article, dict):
                self._send_json(400, {"error": "article (dict) required"})
                return

            import automation  # 단일 진실 소스

            category = article.get("category", "")
            title = article.get("title", "")
            keyword = article.get("keyword") or title or category
            raw_content = article.get("content", "") or ""

            # ── 본문 이미지: Unsplash URL만 다뤄서 디스크 이슈 없음. 실패해도 빈 리스트로 진행 ──
            body_images = []
            try:
                target_img = automation.estimate_body_image_count(raw_content)
                if target_img > 0:
                    body_images = automation.get_body_images(category, target_img)
            except Exception as e:
                print(f"[finalize-post] 본문 이미지 생성 실패(무시하고 진행): {e}")
                body_images = []

            # ── 히어로 썸네일: 파일 대신 base64로. 실패해도 None으로 진행(크래시 금지) ──
            hero_meta = None
            hero_thumbnail = None
            try:
                hero_built = automation.build_hero_image_bytes(category, keyword, title)
                if hero_built:
                    hero_meta = hero_built["meta"]
                    hero_thumbnail = {
                        "filename": hero_built["filename"],
                        "base64": base64.b64encode(hero_built["png_bytes"]).decode("ascii"),
                    }
            except Exception as e:
                print(f"[finalize-post] 히어로 썸네일 생성 실패(무시하고 진행): {e}")
                hero_meta = None
                hero_thumbnail = None

            # automation.py의 finalize_article 호출 — 단일 진실 소스
            finalized = automation.finalize_article(article, hero_meta, body_images)

            if not finalized:
                self._send_json(500, {"error": "finalize_article returned None"})
                return

            # hero_thumbnail: 히어로 썸네일을 못 만들었으면 None (admin.html은 업로드 스킵)
            self._send_json(200, {"article": finalized, "hero_thumbnail": hero_thumbnail})

        except json.JSONDecodeError as e:
            self._send_json(400, {"error": "invalid JSON", "detail": str(e)})
        except Exception as e:
            self._send_json(500, {
                "error": "finalize failed",
                "detail": str(e),
                "trace": traceback.format_exc(),
            })
