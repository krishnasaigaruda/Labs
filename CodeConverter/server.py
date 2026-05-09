"""CodeConverter local server.

Run with:  python3 server.py
Then open: http://localhost:8765

Stdlib only — no pip install needed.
"""
import json
import os
import sys
import webbrowser
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import urlparse

from engine import convert, list_languages, compatibility_matrix, IncompatiblePair

PORT = 7531
ROOT = os.path.dirname(os.path.abspath(__file__))


class Handler(BaseHTTPRequestHandler):
    server_version = "CodeConverter/2.0"

    def log_message(self, fmt, *args):
        sys.stderr.write(f"[{self.log_date_time_string()}] {fmt % args}\n")

    # ---- responses ----
    def _json(self, status, payload):
        body = json.dumps(payload).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Access-Control-Allow-Origin", "*")
        self.end_headers()
        self.wfile.write(body)

    def _file(self, path, content_type):
        try:
            with open(path, "rb") as f:
                data = f.read()
        except FileNotFoundError:
            self.send_error(404, "Not Found")
            return
        self.send_response(200)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(data)))
        self.send_header("Cache-Control", "no-cache")
        self.end_headers()
        self.wfile.write(data)

    # ---- routes ----
    def do_GET(self):
        url = urlparse(self.path)
        if url.path in ("/", "/index.html"):
            self._file(os.path.join(ROOT, "index.html"), "text/html; charset=utf-8")
            return
        if url.path == "/api/languages":
            self._json(200, {
                "languages": list_languages(),
                "compatibility": compatibility_matrix(),
            })
            return
        # static files (only allow files in ROOT)
        rel = url.path.lstrip("/")
        full = os.path.normpath(os.path.join(ROOT, rel))
        if not full.startswith(ROOT):
            self.send_error(403, "Forbidden")
            return
        if os.path.isfile(full):
            ext = os.path.splitext(full)[1].lower()
            ct = {
                ".html": "text/html; charset=utf-8",
                ".js": "text/javascript",
                ".css": "text/css",
                ".json": "application/json",
                ".svg": "image/svg+xml",
            }.get(ext, "application/octet-stream")
            self._file(full, ct)
            return
        self.send_error(404, "Not Found")

    def do_POST(self):
        if self.path != "/api/convert":
            self.send_error(404)
            return
        try:
            length = int(self.headers.get("Content-Length", "0"))
            raw = self.rfile.read(length)
            data = json.loads(raw)
        except Exception as e:
            self._json(400, {"error": f"Invalid JSON: {e}"})
            return

        source = data.get("source", "")
        src_lang = data.get("from", "javascript")
        dst_lang = data.get("to", "python")
        try:
            output = convert(source, src_lang, dst_lang)
            self._json(200, {"output": output})
        except IncompatiblePair as e:
            self._json(200, {"error": str(e), "output": "", "incompatible": True})
        except SyntaxError as e:
            self._json(200, {
                "error": f"Couldn't parse {src_lang}: {e.msg} (line {e.lineno})",
                "output": "",
            })
        except Exception as e:
            self._json(200, {
                "error": f"Conversion error: {type(e).__name__}: {e}",
                "output": "",
            })

    def do_OPTIONS(self):
        self.send_response(204)
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Access-Control-Allow-Methods", "GET, POST, OPTIONS")
        self.send_header("Access-Control-Allow-Headers", "Content-Type")
        self.end_headers()


def main():
    addr = ("127.0.0.1", PORT)
    httpd = ThreadingHTTPServer(addr, Handler)
    url = f"http://localhost:{PORT}"
    print(f"\nCodeConverter running at {url}")
    print("Press Ctrl+C to stop.\n")
    try:
        webbrowser.open(url)
    except Exception:
        pass
    try:
        httpd.serve_forever()
    except KeyboardInterrupt:
        print("\nShutting down.")
        httpd.shutdown()


if __name__ == "__main__":
    main()
