from __future__ import annotations

import json
import sys
from http.server import BaseHTTPRequestHandler
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "CLI"))

from aira.deterministic_scan import scan_inline_source, scan_inline_sources


class handler(BaseHTTPRequestHandler):
    def _send_json(self, status: int, payload: dict):
        body = json.dumps(payload).encode("utf-8")
        self.send_response(status)
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Access-Control-Allow-Methods", "POST, OPTIONS")
        self.send_header("Access-Control-Allow-Headers", "Content-Type")
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def do_OPTIONS(self):
        self.send_response(200)
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Access-Control-Allow-Methods", "POST, OPTIONS")
        self.send_header("Access-Control-Allow-Headers", "Content-Type")
        self.end_headers()

    MAX_PAYLOAD_BYTES = 1_048_576

    def do_POST(self):
        try:
            raw_length = self.headers.get("Content-Length", "0")
            content_length = int(raw_length)
        except (ValueError, TypeError):
            self._send_json(400, {"error": {"message": "Invalid Content-Length header."}})
            return

        if content_length < 0 or content_length > self.MAX_PAYLOAD_BYTES:
            self._send_json(413, {"error": {"message": f"Payload too large. Maximum: {self.MAX_PAYLOAD_BYTES} bytes."}})
            return

        try:
            raw = self.rfile.read(content_length).decode("utf-8", errors="replace") if content_length else "{}"
            body = json.loads(raw or "{}")
        except json.JSONDecodeError:
            self._send_json(400, {"error": {"message": "Invalid JSON body."}})
            return

        files = body.get("files")
        lang = str(body.get("lang") or "")
        if files is not None and not isinstance(files, list):
            self._send_json(400, {"error": {"message": "Deterministic scan files must be an array."}})
            return

        try:
            if isinstance(files, list) and files:
                result = scan_inline_sources(files, default_lang=lang)
            else:
                code = str(body.get("code") or "")
                if not code.strip():
                    self._send_json(400, {"error": {"message": "No code supplied for deterministic scan."}})
                    return
                if not lang.strip():
                    self._send_json(400, {"error": {"message": "No language supplied for deterministic scan."}})
                    return
                result = scan_inline_source(code, lang)
        except ValueError as exc:
            self._send_json(400, {"error": {"message": str(exc)}})
            return
        except Exception as exc:
            self._send_json(500, {"error": {"message": f"Deterministic scan failed: {exc}"}})
            return

        self._send_json(200, result)
