"""Vercel Python serverless: article에 이미지/HTML/SEO 메타를 추가한다.

automation.finalize_article을 호출해 단일 진실 소스를 유지한다.
cron, 직접 글 요청, 네이버 변형 — 3개 경로 모두 같은 인프라.
"""

from http.server import BaseHTTPRequestHandler
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

            # automation.py의 finalize_article 호출 — 단일 진실 소스
            from automation import finalize_article

            finalized = finalize_article(article)

            if not finalized:
                self._send_json(500, {"error": "finalize_article returned None"})
                return

            self._send_json(200, {"article": finalized})

        except json.JSONDecodeError as e:
            self._send_json(400, {"error": "invalid JSON", "detail": str(e)})
        except Exception as e:
            self._send_json(500, {
                "error": "finalize failed",
                "detail": str(e),
                "trace": traceback.format_exc(),
            })
