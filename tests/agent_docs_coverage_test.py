#!/usr/bin/env python3
"""2.35.0 (#1098): the agent documentation keeps up with the code. Every agent event (AGENT_EVENTS in
kalmido/agents/core.py), every agent endpoint (/api/v1/agent... routes) and every MCP tool (mcp/kalmido_mcp.py TOOLS)
appears in docs/AGENTS.md or docs/AGENT-SETUP.md; every event and every MCP tool also in mcp/CLAUDE.template.md (the
file a new agent starts from). The in-app rules equal the marked block of the template (#6887: read at runtime from
GET /api/agent-rules, no copy in static/js/agentchat.js). Pure Python, no container: runs in the full test run and in CI."""
import os
import re
import sys

R = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..")
import kt  # noqa: E402
from kt import check  # noqa: E402  2.358.0 D (#2783): shared helpers (tests/kt.py)


def read(*p):
    with open(os.path.join(R, *p), encoding="utf-8") as f:
        return f.read()


def word(text, w):
    return re.search(r"(?<![A-Za-z0-9_])" + re.escape(w) + r"(?![A-Za-z0-9_])", text) is not None


def path_key(p):
    """/api/v1/agent/chats/<int:uid>/messages/{mid} -> agent/chats/{}/messages/{} (parameter names do not matter)."""
    p = re.sub(r"<(?:[a-z]+:)?[a-z_]+>|\{[a-z_]+\}|:[a-z_]+(?=/|$)", "{}", p.strip())
    return re.sub(r"^/api/v1/", "", p).rstrip("/")


core = read("kalmido", "agents", "core.py")
m = re.search(r"^AGENT_EVENTS = \((.*?)\n\s*\)", core, re.S | re.M)
events = re.findall(r'"([a-z_]+)"', re.sub(r"#[^\n]*", "", m.group(1))) if m else []
check(len(events) >= 20, f"AGENT_EVENTS found: {len(events)}")
tools = sorted(set(re.findall(r'^\s*\("([a-z_]+)",\s*["(]', read("mcp", "kalmido_mcp.py"), re.M)))
check(len(tools) >= 100, f"MCP tools found: {len(tools)}")
routes = set()
for dp, _, fs in os.walk(os.path.join(R, "kalmido")):
    for fn in fs:
        if fn.endswith(".py"):
            with open(os.path.join(dp, fn), encoding="utf-8") as f:
                for meth, p in re.findall(r'@app\.(get|post|put|patch|delete)\("(/api/v1/agent(?:/[^"]*)?)"', f.read()):
                    routes.add((meth.upper(), p))
check(len(routes) >= 10, f"agent endpoints found: {len(routes)}")

docs = read("docs", "AGENTS.md") + "\n" + read("docs", "AGENT-SETUP.md")
tpl = read("mcp", "CLAUDE.template.md")
doc_paths = {path_key(x) for x in re.findall(r"(?:/api/v1)?(/agent(?:/[A-Za-z0-9_{}<>:./-]*)?)", docs)}
doc_paths = {path_key("/api/v1" + p if not p.startswith("/api/v1") else p) for p in doc_paths}

for e in events:
    check(word(docs, e), f"event {e} in docs/AGENTS.md or docs/AGENT-SETUP.md")
    check(word(tpl, e), f"event {e} in mcp/CLAUDE.template.md")
for t in tools:
    check(word(docs, t), f"MCP tool {t} in docs/AGENTS.md or docs/AGENT-SETUP.md")
    check(word(tpl, t), f"MCP tool {t} in mcp/CLAUDE.template.md")
for meth, p in sorted(routes):
    k = path_key(p)
    check(k in doc_paths, f"endpoint {meth} /api/v1/{k} in docs/AGENTS.md or docs/AGENT-SETUP.md")

# the in-app guide shows the same rules as the template (Settings > Agents > Set up). #6887: no copy in agentchat.js any
# more; the guide reads them from GET /api/agent-rules, which cuts the same marked block out of the template (the image
# carries the template next to app.py)
mm = re.search(r"<!-- kalmido-agent-rules:start -->\n(.*?)<!-- kalmido-agent-rules:end -->", tpl, re.S)
check(mm is not None and len(mm.group(1)) > 1000, "the template has the marked rules block")
js = read("static", "js", "agentchat.js") if os.path.exists(os.path.join(R, "static", "js", "agentchat.js")) else ""
if js:
    check(not re.search(r"\bAG_RULES\b", js), "#6887: no AG_RULES copy in agentchat.js")
    check("rawFetch('GET', '/api/agent-rules')" in js and "agRulesGet()" in js, "#6887: the guide fetches the rules from /api/agent-rules")
setup = read("kalmido", "agents", "setup.py")
check('@app.get("/api/agent-rules")' in setup, "#6887: the route GET /api/agent-rules")
rm = re.search(r'^AINS_RULES_RE = re\.compile\(r"(.*?)", re\.S\)$', setup, re.M)
check(rm is not None and mm is not None and re.search(rm.group(1).replace("\\n", "\n"), tpl, re.S).group(1) == mm.group(1),
      "#6887: the route cuts exactly the template block")
check('"CLAUDE.template.md")' in setup and re.search(r"^COPY app\.py .*mcp/CLAUDE\.template\.m\[d\] /app/$", read("Dockerfile"), re.M),
      "#6887: the image carries mcp/CLAUDE.template.md next to app.py, the route reads it there")
print(f"agent_docs_coverage: {kt.OKS[0]} ok, {len(kt.FAILS)} failed ({len(events)} events, {len(routes)} endpoints, {len(tools)} tools)")
sys.exit(1 if kt.FAILS else 0)
