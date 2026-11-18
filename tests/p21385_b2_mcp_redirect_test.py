#!/usr/bin/env python3
# kalmido-suite: nodata
"""2.1385.0 B2 (#6435 11): the agent starter's HTTP clients never follow a redirect with the token - against two fake HTTP
servers, no container:
 - the MCP client (mcp/kalmido_mcp.py class Kalmido): a 302 / 307 / 301 to another server ends as ApiError with the 3xx status and
   a hint to KALMIDO_URL; the other server never gets a request (so never the Authorization header); GET and POST alike
 - the job runner (mcp/agent_job.py class Api) the same: an error, nothing reaches the other server
 - no starter Python file calls urllib.request.urlopen (which follows redirects with every header) any more (kalmido_mcp,
   agent_job, agent_extras, agent_run, claude_usage_hook use their own opener without redirects)
usage: python3 tests/p21385_b2_mcp_redirect_test.py"""
import glob
import importlib.util
import os
import sys
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

from kt import check, done

N = os.path.dirname(os.path.abspath(__file__))
MCP = os.path.join(N, "..", "mcp")


def load(name):
    sp = importlib.util.spec_from_file_location(name, os.path.join(MCP, name + ".py"))
    m = importlib.util.module_from_spec(sp)
    sp.loader.exec_module(m)
    return m


EVIL = []  # (method, path, Authorization) the other server got


class Evil(BaseHTTPRequestHandler):
    def log_message(self, *a):
        pass

    def _go(self):
        n = int(self.headers.get("Content-Length") or 0)
        self.rfile.read(n)
        EVIL.append((self.command, self.path, self.headers.get("Authorization")))
        body = b'{"ok": true}'
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    do_GET = do_POST = do_PATCH = do_PUT = do_DELETE = _go


evil = ThreadingHTTPServer(("127.0.0.1", 0), Evil)
threading.Thread(target=evil.serve_forever, daemon=True).start()
EVIL_URL = f"http://127.0.0.1:{evil.server_address[1]}"
CODE = {"/api/v1/tasks/1": 302, "/api/v1/tasks/2/comments": 307, "/api/v1/agent": 301}


class Kal(BaseHTTPRequestHandler):
    def log_message(self, *a):
        pass

    def _go(self):
        n = int(self.headers.get("Content-Length") or 0)
        self.rfile.read(n)
        path = self.path.split("?")[0]
        self.send_response(CODE.get(path, 302))
        self.send_header("Location", EVIL_URL + "/steal" + path)
        self.send_header("Content-Length", "0")
        self.end_headers()

    do_GET = do_POST = do_PATCH = do_PUT = do_DELETE = _go


kal = ThreadingHTTPServer(("127.0.0.1", 0), Kal)
threading.Thread(target=kal.serve_forever, daemon=True).start()
KAL_URL = f"http://127.0.0.1:{kal.server_address[1]}"
TOKEN = "abk_" + "r" * 40

mcp = load("kalmido_mcp")
mcp._sleep = lambda s: None
api = mcp.Kalmido(KAL_URL, TOKEN, timeout=10)
for method, path, body in (("GET", "/tasks/1", None), ("POST", "/tasks/2/comments", {"body": "x"}), ("GET", "/agent", None)):
    EVIL.clear()
    try:
        api.call(method, path, body=body)
        e = None
    except mcp.ApiError as x:
        e = x
    check(e is not None and 300 <= e.status < 400 and "KALMIDO_URL" in e.message,
          f"#6435 11: MCP {method} {path}: the redirect ends as an error with a hint ({getattr(e, 'status', None)} {getattr(e, 'message', '')!r})")
    check(not EVIL, f"#6435 11: MCP {method} {path}: the other server got nothing (no token) {EVIL}")

os.environ["KALMIDO_URL"], os.environ["KALMIDO_TOKEN"] = KAL_URL, TOKEN
job = load("agent_job")
EVIL.clear()
try:
    job.Api().req("GET", "/agent")
    err = None
except Exception as x:  # noqa: BLE001 - the runner raises RuntimeError on an HTTP error
    err = x
check(err is not None and "HTTP 301" in str(err), f"#6435 11: the job runner: the redirect is an error {err!r}")
check(not EVIL, f"#6435 11: the job runner: the other server got nothing {EVIL}")

left = [os.path.basename(p) for p in sorted(glob.glob(os.path.join(MCP, "*.py"))) if "urllib.request.urlopen(" in open(p, encoding="utf-8").read()]
check(not left, f"#6435 11: no starter file calls urllib.request.urlopen (it follows redirects with the token) {left}")

sys.exit(done("p21385_b2_mcp_redirect"))
