"""A local stand-in for the OpenAI API (standard library only).

Run it with `PYTHONPATH=tests uv run python -m mocks.fake_openai_server`; it prints
`listening http://127.0.0.1:<port>` and serves until interrupted. Tests can also start it
in-process with `FakeOpenAIServer().start()`.

Endpoints:
  POST /v1/embeddings         deterministic 1,536-dimension unit vectors
  POST /v1/chat/completions   a fixed reply text
  GET  /v1/models/<id>        a model object
  POST /_control/script       {"responses": [{"status": 429, "delay": 0, "wrong_size": false}]}
  GET  /_control/requests     the record of received requests
  POST /_control/reset        clear the record and the script

Only the key `sk-test-valid` is accepted; any other key gets an OpenAI-shaped 401.
"""

from __future__ import annotations

import argparse
import base64
import hashlib
import json
import math
import re
import struct
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from typing import Any

VALID_KEY = "sk-test-valid"
INVALID_KEY = "sk-test-invalid"
DIMENSIONS = 1536
CONSTANT_COMPONENT = 0.02
CHAT_REPLY = "This is a stand-in reply."
_TOKEN = re.compile(r"[a-z0-9]+")


def embed_text(text: str) -> list[float]:
    """Deterministic unit vector: hashed lowercase words plus a small constant, never zero."""
    vector = [CONSTANT_COMPONENT] * DIMENSIONS
    for token in _TOKEN.findall(text.lower()):
        digest = hashlib.sha256(token.encode()).digest()
        vector[int.from_bytes(digest[:4], "big") % DIMENSIONS] += 1.0
    norm = math.sqrt(sum(value * value for value in vector))
    return [value / norm for value in vector]


def _error_body(message: str, kind: str, code: str | None) -> dict[str, Any]:
    return {"error": {"message": message, "type": kind, "param": None, "code": code}}


_STATUS_ERRORS = {
    400: ("Bad request from the stand-in", "invalid_request_error", None),
    401: ("Incorrect API key provided", "invalid_request_error", "invalid_api_key"),
    429: ("Rate limit reached", "rate_limit_error", "rate_limit_exceeded"),
    500: ("The stand-in failed", "server_error", None),
    503: ("The stand-in is unavailable", "server_error", None),
}


class FakeOpenAIServer:
    def __init__(self, host: str = "127.0.0.1", port: int = 0) -> None:
        self._lock = threading.Lock()
        self._script: list[dict[str, Any]] = []
        self._requests: list[dict[str, Any]] = []
        owner = self

        class Handler(BaseHTTPRequestHandler):
            protocol_version = "HTTP/1.1"

            def log_message(self, format: str, *args: Any) -> None:
                return

            def _send(self, status: int, body: dict[str, Any]) -> None:
                payload = json.dumps(body).encode()
                try:
                    self.send_response(status)
                    self.send_header("Content-Type", "application/json")
                    self.send_header("Content-Length", str(len(payload)))
                    self.end_headers()
                    self.wfile.write(payload)
                except OSError:
                    pass

            def _json_body(self) -> dict[str, Any]:
                length = int(self.headers.get("Content-Length") or 0)
                raw = self.rfile.read(length) if length else b""
                return json.loads(raw) if raw else {}

            def do_GET(self) -> None:
                if self.path == "/_control/requests":
                    self._send(200, {"requests": owner.requests})
                elif self.path.startswith("/v1/models/"):
                    if not owner._key_accepted(self.headers):
                        self._send(401, _error_body(*_STATUS_ERRORS[401]))
                    else:
                        model = self.path.rsplit("/", 1)[1]
                        self._send(200, {"id": model, "object": "model", "owned_by": "stand-in"})
                else:
                    self._send(404, _error_body("Not found", "invalid_request_error", None))

            def do_POST(self) -> None:
                body = self._json_body()
                if self.path == "/_control/script":
                    owner.script(body.get("responses", []))
                    self._send(200, {"ok": True})
                elif self.path == "/_control/reset":
                    owner.reset()
                    self._send(200, {"ok": True})
                elif self.path == "/v1/embeddings":
                    owner._embeddings(self, body)
                elif self.path == "/v1/chat/completions":
                    owner._chat(self, body)
                else:
                    self._send(404, _error_body("Not found", "invalid_request_error", None))

        self._server = ThreadingHTTPServer((host, port), Handler)
        self._server.daemon_threads = True
        self._thread: threading.Thread | None = None

    # -- lifecycle ------------------------------------------------------------------------

    @property
    def port(self) -> int:
        return self._server.server_address[1]

    @property
    def base_url(self) -> str:
        """The `/v1` URL the OpenAI client library uses."""
        return f"http://127.0.0.1:{self.port}/v1"

    def start(self) -> FakeOpenAIServer:
        self._thread = threading.Thread(target=self._server.serve_forever, daemon=True)
        self._thread.start()
        return self

    def stop(self) -> None:
        self._server.shutdown()
        self._server.server_close()
        if self._thread is not None:
            self._thread.join(timeout=5)

    def serve_forever(self) -> None:
        self._server.serve_forever()

    # -- control --------------------------------------------------------------------------

    def script(self, responses: list[dict[str, Any]]) -> None:
        """Queue answers for the next embedding requests, consumed in order."""
        with self._lock:
            self._script.extend(responses)

    def reset(self) -> None:
        with self._lock:
            self._script.clear()
            self._requests.clear()

    @property
    def requests(self) -> list[dict[str, Any]]:
        with self._lock:
            return [dict(item) for item in self._requests]

    def embedding_requests(self) -> list[dict[str, Any]]:
        return [item for item in self.requests if item["path"] == "/v1/embeddings"]

    def chat_requests(self) -> list[dict[str, Any]]:
        return [item for item in self.requests if item["path"] == "/v1/chat/completions"]

    # -- handlers -------------------------------------------------------------------------

    @staticmethod
    def _key_accepted(headers: Any) -> bool:
        authorization = headers.get("Authorization", "")
        return authorization == f"Bearer {VALID_KEY}"

    def _record(self, path: str, headers: Any, **fields: Any) -> bool:
        accepted = self._key_accepted(headers)
        with self._lock:
            self._requests.append({"path": path, "key_accepted": accepted, **fields})
        return accepted

    def _next_scripted(self) -> dict[str, Any]:
        with self._lock:
            return self._script.pop(0) if self._script else {}

    def _embeddings(self, handler: BaseHTTPRequestHandler, body: dict[str, Any]) -> None:
        inputs = body.get("input", [])
        if isinstance(inputs, str):
            inputs = [inputs]
        accepted = self._record(
            "/v1/embeddings", handler.headers, model=body.get("model"), inputs=len(inputs)
        )
        if not accepted:
            handler._send(401, _error_body(*_STATUS_ERRORS[401]))  # type: ignore[attr-defined]
            return
        scripted = self._next_scripted()
        delay = scripted.get("delay", 0)
        if delay:
            time.sleep(delay)
        status = int(scripted.get("status", 200))
        if status != 200:
            handler._send(status, _error_body(*_STATUS_ERRORS.get(status, _STATUS_ERRORS[400])))  # type: ignore[attr-defined]
            return
        wrong_size = bool(scripted.get("wrong_size"))
        use_base64 = body.get("encoding_format") == "base64"
        data = []
        for index, text in enumerate(inputs):
            vector = [1.0, 0.0, 0.0] if wrong_size else embed_text(str(text))
            embedding: Any = vector
            if use_base64:
                embedding = base64.b64encode(struct.pack(f"<{len(vector)}f", *vector)).decode()
            data.append({"object": "embedding", "index": index, "embedding": embedding})
        handler._send(  # type: ignore[attr-defined]
            200,
            {
                "object": "list",
                "data": data,
                "model": body.get("model"),
                "usage": {"prompt_tokens": len(inputs), "total_tokens": len(inputs)},
            },
        )

    def _chat(self, handler: BaseHTTPRequestHandler, body: dict[str, Any]) -> None:
        accepted = self._record(
            "/v1/chat/completions",
            handler.headers,
            model=body.get("model"),
            temperature=body.get("temperature"),
        )
        if not accepted:
            handler._send(401, _error_body(*_STATUS_ERRORS[401]))  # type: ignore[attr-defined]
            return
        handler._send(  # type: ignore[attr-defined]
            200,
            {
                "id": "chatcmpl-standin",
                "object": "chat.completion",
                "created": 0,
                "model": body.get("model"),
                "choices": [
                    {
                        "index": 0,
                        "message": {"role": "assistant", "content": CHAT_REPLY},
                        "finish_reason": "stop",
                    }
                ],
                "usage": {"prompt_tokens": 1, "completion_tokens": 1, "total_tokens": 2},
            },
        )


def main() -> None:
    parser = argparse.ArgumentParser(description="Local stand-in for the OpenAI API.")
    parser.add_argument("--port", type=int, default=0)
    args = parser.parse_args()
    server = FakeOpenAIServer(port=args.port)
    print(f"listening http://127.0.0.1:{server.port}", flush=True)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass


if __name__ == "__main__":
    main()
