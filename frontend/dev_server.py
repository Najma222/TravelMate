"""Small dependency-free frontend server for local development.

It serves the static frontend and proxies /api and /media to Flask on localhost:5000.
This avoids Python's plain http.server returning 501 for POST/PUT/DELETE requests.
"""
from __future__ import annotations

import os
import urllib.error
import urllib.request
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer


BACKEND = os.environ.get("TRAVELMATE_BACKEND", "http://127.0.0.1:5000").rstrip("/")
PORT = int(os.environ.get("TRAVELMATE_FRONTEND_PORT", "8080"))


class Handler(SimpleHTTPRequestHandler):
    def _is_proxy_path(self) -> bool:
        return self.path.startswith("/api/") or self.path.startswith("/media/") or self.path == "/health"

    def _proxy(self) -> None:
        length = int(self.headers.get("Content-Length", "0"))
        body = self.rfile.read(length) if length else None
        target = urllib.request.Request(
            BACKEND + self.path,
            data=body,
            method=self.command,
            headers={
                key: value
                for key, value in self.headers.items()
                if key.lower() not in {"host", "connection", "content-length"}
            },
        )
        try:
            with urllib.request.urlopen(target, timeout=30) as response:
                payload = response.read()
                self.send_response(response.status)
                for key, value in response.headers.items():
                    if key.lower() not in {"connection", "transfer-encoding", "content-length"}:
                        self.send_header(key, value)
                self.send_header("Content-Length", str(len(payload)))
                self.end_headers()
                self.wfile.write(payload)
        except urllib.error.HTTPError as error:
            payload = error.read()
            self.send_response(error.code)
            self.send_header("Content-Type", error.headers.get("Content-Type", "application/json"))
            self.send_header("Content-Length", str(len(payload)))
            self.end_headers()
            self.wfile.write(payload)
        except (urllib.error.URLError, TimeoutError) as error:
            message = ("Backend unavailable at " + BACKEND + ": " + str(error)).encode()
            self.send_response(502)
            self.send_header("Content-Type", "text/plain; charset=utf-8")
            self.send_header("Content-Length", str(len(message)))
            self.end_headers()
            self.wfile.write(message)

    def do_GET(self) -> None:  # noqa: N802
        if self._is_proxy_path():
            self._proxy()
        else:
            super().do_GET()

    def do_POST(self) -> None:  # noqa: N802
        self._proxy() if self._is_proxy_path() else self.send_error(405)

    def do_PUT(self) -> None:  # noqa: N802
        self._proxy() if self._is_proxy_path() else self.send_error(405)

    def do_DELETE(self) -> None:  # noqa: N802
        self._proxy() if self._is_proxy_path() else self.send_error(405)


if __name__ == "__main__":
    server = ThreadingHTTPServer(("127.0.0.1", PORT), Handler)
    print(f"TravelMate frontend: http://127.0.0.1:{PORT}/")
    print(f"Proxying /api and /media to {BACKEND}")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        server.server_close()
