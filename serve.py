#!/usr/bin/env python3
"""Serve the dashboard locally: python3 serve.py [port]"""
import functools, http.server, socketserver, sys, urllib.parse

PORT = int(sys.argv[1]) if len(sys.argv) > 1 else 8000
# one workbook per board; passing both on the URL bypasses the api/sheet.js proxy
SHEETS = {
    'existing': '1MJHjM6ubBba_ZHXBk8jsYqLdcixdOBrgxvH8AdZWZYI',
    'netnew':   '1NNFcCsa29lr4gavs7PFyXxm88PLIMpnNTmaIbyKax18',
}
Handler = functools.partial(http.server.SimpleHTTPRequestHandler, directory=".")


class Quiet(Handler.func):
    def end_headers(self):
        self.send_header("cache-control", "no-store")
        super().end_headers()


socketserver.TCPServer.allow_reuse_address = True
with socketserver.TCPServer(("", PORT), functools.partial(Quiet, directory=".")) as httpd:
    print(f"http://localhost:{PORT}/index.html?{urllib.parse.urlencode(SHEETS)}")
    httpd.serve_forever()
