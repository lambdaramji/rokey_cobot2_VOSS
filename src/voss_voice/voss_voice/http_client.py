"""FastAPI /ai, Spring Boot /api 호출 (표준 라이브러리만, docs/interfaces/web_api.md).

음성 노드는 공용 PC 로컬(127.0.0.1)로만 부른다. 실패는 예외 대신 None 을 돌려주고,
호출한 쪽이 되묻기·"조회할 수 없습니다" 로 처리한다.
"""

from __future__ import annotations

import json
import urllib.error
import urllib.parse
import urllib.request

AI_BASE = "http://127.0.0.1:8000"
API_BASE = "http://127.0.0.1:8080"


def _request(req: urllib.request.Request, timeout_s: float) -> dict | None:
    try:
        with urllib.request.urlopen(req, timeout=timeout_s) as r:
            return json.loads(r.read().decode("utf-8"))
    except urllib.error.HTTPError as e:  # 4xx·5xx 도 본문에 {"ok": false, ...} 가 온다
        try:
            return json.loads(e.read().decode("utf-8"))
        except (ValueError, OSError):
            return None
    except (urllib.error.URLError, TimeoutError, ValueError, OSError):
        return None


def post_intent(
    text: str, allowed: dict, base: str = AI_BASE, timeout_s: float = 3.0
) -> dict | None:
    """POST /ai/intent → intent JSON (dict) 또는 None(timeout·오류·ok=false)."""
    body = json.dumps({"text": text, "allowed": allowed}, ensure_ascii=False).encode("utf-8")
    req = urllib.request.Request(
        f"{base}/ai/intent", data=body, headers={"Content-Type": "application/json"}, method="POST"
    )
    resp = _request(req, timeout_s)
    if not resp or not resp.get("ok") or not isinstance(resp.get("intent"), dict):
        return None
    return resp["intent"]


def get_stats(query: dict, base: str = API_BASE, timeout_s: float = 2.0) -> dict | None:
    """GET /api/stats → 응답 dict (ok 포함) 또는 None."""
    params = {"query_kind": query["query_kind"]}
    if query.get("dong"):
        params["dong"] = query["dong"]
    url = f"{base}/api/stats?{urllib.parse.urlencode(params)}"
    return _request(urllib.request.Request(url, method="GET"), timeout_s)


def post_stt(
    wav: bytes, language: str = "ko", base: str = AI_BASE, timeout_s: float = 5.0
) -> dict | None:
    """POST /ai/stt (multipart: audio WAV) → {"ok": true, "text": ..., "stt_ms": ...} 또는 None."""
    boundary = "vossboundary7e3f"
    parts = [
        f'--{boundary}\r\nContent-Disposition: form-data; name="language"\r\n\r\n{language}\r\n'.encode(),
        (
            f'--{boundary}\r\nContent-Disposition: form-data; name="audio"; filename="seg.wav"\r\n'
            "Content-Type: audio/wav\r\n\r\n"
        ).encode()
        + wav
        + b"\r\n",
        f"--{boundary}--\r\n".encode(),
    ]
    req = urllib.request.Request(
        f"{base}/ai/stt",
        data=b"".join(parts),
        headers={"Content-Type": f"multipart/form-data; boundary={boundary}"},
        method="POST",
    )
    resp = _request(req, timeout_s)
    if not resp or not resp.get("ok") or not isinstance(resp.get("text"), str):
        return None
    return resp
