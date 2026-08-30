#!/usr/bin/env python3
"""Serve the dashboard locally: python3 serve.py [port]"""
import functools, http.server, socketserver, sys

PORT = int(sys.argv[1]) if len(sys.argv) > 1 else 8000
SHEET = '1MJHjM6ubBba_ZHXBk8jsYqLdcixdOBrgxvH8AdZWZYI'
Handler = functools.partial(http.server.SimpleHTTPRequestHandler, directory=".")


class Quiet(Handler.func):
    def end_headers(self):
        self.send_header("cache-control", "no-store")
        super().end_headers()


socketserver.TCPServer.allow_reuse_address = True
with socketserver.TCPServer(("", PORT), functools.partial(Quiet, directory=".")) as httpd:
    print(f"http://localhost:{PORT}/index.html?sheet={SHEET}")
    httpd.serve_forever()
