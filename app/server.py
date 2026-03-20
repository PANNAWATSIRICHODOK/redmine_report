from __future__ import annotations

import json
import mimetypes
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from typing import Any
from urllib.parse import parse_qs, urlparse

from .config import ConfigError, STATIC_DIR, TEMPLATES_DIR, load_server_config
from .reporting import build_report, list_report_users


def json_bytes(payload: dict[str, Any]) -> bytes:
    return json.dumps(payload, ensure_ascii=False, separators=(",", ":")).encode("utf-8")


def content_type_with_charset(content_type: str) -> str:
    if content_type.startswith("text/") or content_type in {"application/json", "application/javascript"}:
        return f"{content_type}; charset=utf-8"
    return content_type


class ReportHandler(BaseHTTPRequestHandler):
    server_version = "RedmineReport"
    sys_version = ""

    def do_GET(self) -> None:
        parsed = urlparse(self.path)
        if parsed.path == "/":
            self.serve_index()
            return
        if parsed.path == "/api/report":
            self.serve_report(parsed.query)
            return
        if parsed.path == "/api/report-users":
            self.serve_report_users()
            return
        if parsed.path == "/health":
            self.send_json(HTTPStatus.OK, {"status": "ok"})
            return
        if parsed.path.startswith("/static/"):
            self.serve_static(parsed.path)
            return
        self.send_json(HTTPStatus.NOT_FOUND, {"error": "Not found"})

    def serve_index(self) -> None:
        index_path = TEMPLATES_DIR / "index.html"
        if not index_path.exists():
            self.send_json(HTTPStatus.INTERNAL_SERVER_ERROR, {"error": "Missing templates/index.html"})
            return

        self.send_body(HTTPStatus.OK, index_path.read_bytes(), "text/html", cache_control="no-store")

    def serve_static(self, request_path: str) -> None:
        relative_path = request_path.removeprefix("/static/").strip("/")
        file_path = (STATIC_DIR / relative_path).resolve()

        try:
            file_path.relative_to(STATIC_DIR.resolve())
        except ValueError:
            self.send_json(HTTPStatus.FORBIDDEN, {"error": "Invalid static path"})
            return

        if not relative_path or not file_path.exists() or not file_path.is_file():
            self.send_json(HTTPStatus.NOT_FOUND, {"error": "Static file not found"})
            return

        content_type = mimetypes.guess_type(str(file_path))[0] or "application/octet-stream"
        self.send_body(
            HTTPStatus.OK,
            file_path.read_bytes(),
            content_type,
            cache_control="public, max-age=300",
        )

    def serve_report(self, query_string: str) -> None:
        try:
            payload = build_report(parse_qs(query_string, keep_blank_values=False))
        except ConfigError as exc:
            self.send_json(HTTPStatus.INTERNAL_SERVER_ERROR, {"error": str(exc)})
            return
        except ValueError as exc:
            self.send_json(HTTPStatus.BAD_REQUEST, {"error": str(exc)})
            return
        except Exception as exc:  # pragma: no cover
            self.send_json(HTTPStatus.BAD_GATEWAY, {"error": str(exc)})
            return

        self.send_json(HTTPStatus.OK, payload)

    def serve_report_users(self) -> None:
        try:
            payload = list_report_users()
        except ConfigError as exc:
            self.send_json(HTTPStatus.INTERNAL_SERVER_ERROR, {"error": str(exc)})
            return
        except ValueError as exc:
            self.send_json(HTTPStatus.BAD_REQUEST, {"error": str(exc)})
            return
        except Exception as exc:  # pragma: no cover
            self.send_json(HTTPStatus.BAD_GATEWAY, {"error": str(exc)})
            return

        self.send_json(HTTPStatus.OK, payload)

    def send_body(
        self,
        status: HTTPStatus,
        body: bytes,
        content_type: str,
        cache_control: str,
    ) -> None:
        self.send_response(status)
        self.send_header("Content-Type", content_type_with_charset(content_type))
        self.send_header("Cache-Control", cache_control)
        self.send_header("X-Content-Type-Options", "nosniff")
        self.send_header("Referrer-Policy", "same-origin")
        self.send_header("X-Frame-Options", "DENY")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        try:
            self.wfile.write(body)
        except (BrokenPipeError, ConnectionResetError):
            return

    def send_json(self, status: HTTPStatus, payload: dict[str, Any]) -> None:
        self.send_body(status, json_bytes(payload), "application/json", cache_control="no-store")

    def log_message(self, format: str, *args: Any) -> None:
        return


def run_server() -> None:
    config = load_server_config()
    server = ThreadingHTTPServer((config.host, config.port), ReportHandler)
    print(f"Redmine report is running at http://{config.host}:{config.port}")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        server.server_close()
