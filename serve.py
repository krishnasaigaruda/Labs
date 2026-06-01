#!/usr/bin/env python3
"""
Tiny static server for ToolLabs.

The Aesthetic Checker renders its AI mockups through blob: URLs and calls the
Pollinations API with fetch(). Browsers block both of those when a page is
opened directly as a file:// URL (file pages are treated as unique, locked-down
origins). Serving the folder over http://localhost fixes it.

Usage:
    python3 serve.py [port]      # default port 8787
"""
import http.server
import os
import socketserver
import sys
import webbrowser

PORT = int(sys.argv[1]) if len(sys.argv) > 1 else 8787

# Serve from the directory this script lives in (the Labs root).
os.chdir(os.path.dirname(os.path.abspath(__file__)))


class Handler(http.server.SimpleHTTPRequestHandler):
    def end_headers(self):
        # Don't cache during local dev so edits show up on reload.
        self.send_header("Cache-Control", "no-store")
        super().end_headers()

    def log_message(self, fmt, *args):  # quieter console
        pass


def open_server(port):
    """Bind to `port`, or the next free port if it's already taken."""
    for candidate in range(port, port + 20):
        try:
            return candidate, socketserver.TCPServer(("127.0.0.1", candidate), Handler)
        except OSError:
            print(f"Port {candidate} is busy, trying {candidate + 1}…")
    raise SystemExit(f"Could not find a free port in {port}-{port + 19}.")


def main():
    port, httpd = open_server(PORT)
    with httpd:
        home = f"http://localhost:{port}/Labs.html"
        tool = f"http://localhost:{port}/AestheticChecker/index.html"
        print(f"ToolLabs is running:  {home}")
        print(f"Aesthetic Checker:    {tool}")
        print("Press Ctrl+C to stop.")
        try:
            webbrowser.open(tool)
        except Exception:
            pass
        try:
            httpd.serve_forever()
        except KeyboardInterrupt:
            print("\nStopped.")


if __name__ == "__main__":
    main()
