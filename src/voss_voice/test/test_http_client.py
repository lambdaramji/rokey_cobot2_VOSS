"""http_client 시험: 로컬 가짜 서버로 정상·오류·timeout 처리 확인 (실제 FastAPI·Spring 불필요)."""

import json
import threading
from http.server import BaseHTTPRequestHandler, HTTPServer

import pytest

from voss_voice import http_client


class _Handler(BaseHTTPRequestHandler):
    def log_message(self, *args):  # 조용히
        pass

    def _send(self, code, body):
        data = json.dumps(body, ensure_ascii=False).encode("utf-8")
        self.send_response(code)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        self.wfile.write(data)

    def do_POST(self):
        body = self.rfile.read(int(self.headers["Content-Length"]))
        if self.path == "/ai/stt":
            ok = b'name="audio"' in body and b"RIFF" in body and b'name="language"' in body
            self._send(200 if ok else 400, {"ok": ok, "text": "작업 시작", "stt_ms": 12})
            return
        req = json.loads(body)

        if req["text"] == "parse_fail":
            self._send(422, {"ok": False, "message": "PARSE_ERROR"})
            return

        if req["text"] == "fail":
            self._send(502, {"ok": False, "message": "LLM_ERROR"})
        else:
            self._send(200, {"ok": True, "intent": {"type": "start", "raw_text": req["text"]}})

    def do_GET(self):
        if "query_kind=held_count" in self.path:
            self._send(503, {"ok": False, "message": "DB_ERROR"})
        else:
            self._send(200, {"ok": True, "count": 3, "path": self.path})


@pytest.fixture(scope="module")
def base():
    srv = HTTPServer(("127.0.0.1", 0), _Handler)
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    yield f"http://127.0.0.1:{srv.server_address[1]}"
    srv.shutdown()


def test_post_intent_ok(base):
    assert http_client.post_intent("시작", {}, base=base) == {"type": "start", "raw_text": "시작"}


def test_post_intent_error_returns_none(base):
    assert http_client.post_intent("fail", {}, base=base) is None


def test_unreachable_returns_none():
    assert http_client.post_intent("시작", {}, base="http://127.0.0.1:9", timeout_s=0.5) is None


def test_get_stats_ok_and_encodes_dong(base):
    r = http_client.get_stats({"query_kind": "count_by_dong", "dong": "역삼동"}, base=base)
    assert r["ok"] and r["count"] == 3
    assert "dong=%EC%97%AD%EC%82%BC%EB%8F%99" in r["path"]


def test_get_stats_db_error_body_is_returned(base):
    r = http_client.get_stats({"query_kind": "held_count", "dong": ""}, base=base)
    assert r == {"ok": False, "message": "DB_ERROR"}


def test_post_stt_sends_multipart_wav(base):
    r = http_client.post_stt(b"RIFF....WAVEfmt ", base=base)
    assert r["ok"] and r["text"] == "작업 시작"


def test_post_stt_unreachable_returns_none():
    assert http_client.post_stt(b"RIFF", base="http://127.0.0.1:9", timeout_s=0.5) is None


def test_post_intent_parse_error_raises_specific_exception(base) -> None:
    """HTTP 422 PARSE_ERROR를 연결 장애와 구분한다."""
    with pytest.raises(http_client.IntentParseError):
        http_client.post_intent("parse_fail", {}, base=base)
