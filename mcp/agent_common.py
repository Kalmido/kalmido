#!/usr/bin/env python3
"""agent_common.py -- the helpers the reference starter's modules share (#7151). agent_run.py, agent_job.py, agent_extras.py
and agent_dispatch.py import them from here instead of each keeping a copy: a fix lands once (before, the same fix went into
four files, and the job runner's redact let JWTs, PEM keys and password pairs through).

Part of the starter (mcp/starter_files.txt, checked by its SHA-256 like the others). kalmido_mcp.py stays a file of its own
(the server image carries only it; a person may run it alone as an MCP server): defuse_fence and env_credentials live there
and are taken from it here, so there is still one copy of each.

Standard library only."""
import json
import mimetypes
import os
import re
import subprocess
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
import uuid

HERE = os.path.dirname(os.path.abspath(__file__))
if HERE not in sys.path:
    sys.path.insert(0, HERE)
from kalmido_mcp import defuse_fence, env_credentials  # noqa: E402,F401  the one copy of each (see above)

CHAT_CHUNK = 7500  # the server takes 8000 characters per message
RETRY_429_S = (5, 15, 30, 60)  # 2.44.0 (#1448): HTTP 429 of the API -> try again after 5 / 15 / 30 / 60 s

# ---- secrets never leave the host in a text (steps, job logs, results, chat)
REDACTED = "[redacted]"
SECRET_RES = [
    re.compile(r"-----BEGIN [A-Z0-9 ]*(?:PRIVATE KEY|KEY|CERTIFICATE)-----.*?(?:-----END [A-Z0-9 ]*-----|\Z)", re.S),
    re.compile(r"\b(?:abk|sk-ant|sk-proj|sk)[-_][A-Za-z0-9_-]{16,}"),
    re.compile(r"\b(?:ghp|gho|ghu|ghs|ghr|github_pat)_[A-Za-z0-9_]{16,}"),
    re.compile(r"\bglpat-[A-Za-z0-9_-]{16,}"),
    re.compile(r"\b(?:AKIA|ASIA)[0-9A-Z]{16}\b"),
    re.compile(r"\bxox[abprs]-[A-Za-z0-9-]{10,}"),
    re.compile(r"\beyJ[A-Za-z0-9_-]{8,}\.[A-Za-z0-9_-]{8,}\.[A-Za-z0-9_-]{4,}"),
    re.compile(r"\b(?:Bearer|Basic|Token)\s+(?=[A-Za-z0-9._~+/=-]{0,200}\d)[A-Za-z0-9._~+/=-]{12,}"),
    re.compile(r"(?i)(?<=://)[^/\s:@]+:[^/\s@]+(?=@)"),
    re.compile(r"(?i)\b([A-Za-z0-9_]{0,30}(?:token|secret|password|passwd|api_?key)[A-Za-z0-9_]{0,30}\"?\s*[:=]\s*\"?)[^\s\"']{8,}"),
]


def redact(text):
    """Known secret values (the token, values of *TOKEN* / *SECRET* / *PASSWORD* / *API_KEY* variables) and token patterns
    (API keys, GitHub / GitLab / AWS / Slack tokens, JWTs, PEM keys, user:password@ in URLs, name=value pairs) -> [redacted]."""
    if not text:
        return "" if text is None else text
    # #7051 (Fable reader N2): a job started from a run has no KALMIDO_TOKEN in its environment; the value comes from the env file
    vals = [env_credentials()[1]]
    vals += [v for k, v in os.environ.items() if re.search(r"TOKEN|SECRET|PASSWORD|API_KEY", k)]
    for v in sorted({v for v in vals if len(v) >= 8}, key=len, reverse=True):
        text = text.replace(v, REDACTED)
    for i, pat in enumerate(SECRET_RES):
        text = pat.sub((lambda m: m.group(1) + REDACTED) if i == len(SECRET_RES) - 1 else REDACTED, text)
    return text


# ---- files and processes

def write_json(path, data, indent=None):
    """Write JSON atomically (a reader never sees half a file); the folder is made when missing."""
    d = os.path.dirname(path)
    if d:
        os.makedirs(d, exist_ok=True)
    tmp = path + ".new"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=indent)
    os.replace(tmp, path)


def kill_tree(p):
    """2.44.0 (#1448): end a command AND what it started (its process group; Windows: taskkill /T). p: a Popen (waited for
    5 s, then killed) or a process id."""
    pid = getattr(p, "pid", p)
    if not pid:
        return
    try:
        if os.name == "nt":
            subprocess.run(["taskkill", "/T", "/F", "/PID", str(int(pid))], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, timeout=30)
        else:
            import signal
            os.killpg(int(pid), signal.SIGTERM)
            if hasattr(p, "wait"):
                try:
                    p.wait(5)
                except subprocess.TimeoutExpired:
                    os.killpg(int(pid), signal.SIGKILL)
    except (OSError, subprocess.SubprocessError, ValueError, TypeError):  # gone already, no right, no taskkill
        if hasattr(p, "kill"):
            try:
                p.kill()
            except OSError:
                pass


# ---- chat texts and uploads

def chunks(text, n=CHAT_CHUNK):
    """2.40.0 (#1100 chunk_fences): a long answer in chat-sized parts, cut at a paragraph (else a line); a code block open
    at the cut is closed there and opened again (same language) in the next part; several parts are numbered (i/n)."""
    text = (text or "").strip("\n")
    n = max(200, n - 40)  # room for the closing fence and the part number
    out = []
    while len(text) > n:
        cut = text.rfind("\n\n", 0, n)
        if cut < n // 2:
            cut = text.rfind("\n", 0, n)
        if cut < n // 2:
            cut = n
        piece, text = text[:cut].rstrip(), text[cut:].lstrip("\n")
        fences = re.findall(r"^[ \t]*```([^\n`]*)$", piece, re.M)
        if len(fences) % 2 == 1:  # a code block is open at the cut
            piece += "\n```"
            text = "```" + fences[-1].strip() + "\n" + text
        out.append(piece)
    if text.strip():
        out.append(text)
    return [f"{p}\n\n_({i + 1}/{len(out)})_" for i, p in enumerate(out)] if len(out) > 1 else out


def multipart(fields, files):
    """(body bytes, content type) of a multipart/form-data request; files = [(field, path)]."""
    bd = "----kalmido" + uuid.uuid4().hex
    out = []
    for k, v in fields.items():
        out.append(f'--{bd}\r\nContent-Disposition: form-data; name="{k}"\r\n\r\n{v}\r\n'.encode())
    for k, p in files:
        name = os.path.basename(p).replace('"', "_")
        mime = mimetypes.guess_type(p)[0] or "application/octet-stream"
        with open(p, "rb") as f:
            out.append((f'--{bd}\r\nContent-Disposition: form-data; name="{k}"; filename="{name}"\r\n'
                        f"Content-Type: {mime}\r\n\r\n").encode() + f.read() + b"\r\n")
    out.append(f"--{bd}--\r\n".encode())
    return b"".join(out), "multipart/form-data; boundary=" + bd


# ---- the agent API

class ApiError(Exception):
    def __init__(self, status, body):
        super().__init__(f"HTTP {status}")
        self.status, self.body = status, body or ""


class Api:
    """The transport of the agent API both runners use (agent_run.Api adds its calls, agent_job.Api its token renewal):
    HTTP 429 is tried again after 5 / 15 / 30 / 60 s (kalmido-capability: robust_runs, 2.44.0 #1448); 2.1386.0 (#6668,
    review F4): a client with renew() that gets 401 (its request token was replaced or ended) asks once for a new token and
    sends the call again with it; no new token = the 401 stands (never the agent's own token)."""

    renew = None

    def __init__(self, url, token):
        self.base = url.rstrip("/") + "/api/v1"
        self.token = token

    def note(self, msg):
        sys.stderr.write(time.strftime("%Y-%m-%d %H:%M:%S") + " agent: " + msg + "\n")

    def req(self, method, path, body=None, query=None, timeout=30, retry=True, raw=None, ctype=None):
        try:
            return self._req_429(method, path, body, query, timeout, retry, raw, ctype)
        except ApiError as e:
            if e.status != 401 or not callable(self.renew):
                raise
            tok = self.renew()
            if not tok or tok == self.token:
                raise
            self.note(f"{path.split('?')[0]}: HTTP 401, a new request token")
            self.token = tok
            return self._req_429(method, path, body, query, timeout, retry, raw, ctype)

    def _req_429(self, method, path, body=None, query=None, timeout=30, retry=True, raw=None, ctype=None):
        kw = {"raw": raw, "ctype": ctype} if raw is not None else {}  # _req(method, path, body, query, timeout) stays the call
        for wait in (RETRY_429_S if retry else ()):
            try:
                return self._req(method, path, body, query, timeout, **kw)
            except ApiError as e:
                if e.status != 429:
                    raise
                self.note(f"{path.split('?')[0]}: HTTP 429, trying again in {wait} s")
                time.sleep(wait)
        return self._req(method, path, body, query, timeout, **kw)

    def _req(self, method, path, body=None, query=None, timeout=30, raw=None, ctype=None):
        url = self.base + path + ("?" + urllib.parse.urlencode(query) if query else "")
        data = raw if raw is not None else (json.dumps(body).encode() if body is not None else None)
        h = {"Authorization": "Bearer " + self.token, "Accept": "application/json"}
        if data is not None:
            h["Content-Type"] = ctype or "application/json"
        rq = urllib.request.Request(url, data=data, method=method, headers=h)
        try:
            with urllib.request.urlopen(rq, timeout=timeout) as r:
                b = r.read()
                return json.loads(b) if b else {}
        except urllib.error.HTTPError as e:
            raise ApiError(e.code, e.read().decode(errors="replace")[:500])
