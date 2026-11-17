#!/usr/bin/env python3
"""2.754.0 (#5297): every ${} in an HTML template of the web client is escaped, a safe helper, or marked.

A template literal with markup (a `...` holding <tag) ends up in innerHTML / insertAdjacentHTML / outerHTML. A ${value} in it
that is not escaped becomes markup when the value comes from a person (a name, a title, a host). Reads every template literal
of static/js/**/*.js that holds markup (the template reader of tools/check_trh.py) and checks each ${expr}:

  safe   esc(...) / i18nEsc(...) / escA(...) as a whole, trh / trnh (escape their values), tr(...) / trn(...) as the WHOLE
         expression (tools/check_trh.py checks their values there); 2.1364.0 (#6297 (15)): inside a ternary / || / && / a
         concatenation only with a constant text and safe values (tr('Hello'), tr('{0} done', esc(x)), trn('…', '…', n)),
         a number literal, x.length / x.size, Math.* / Number() / parseInt() / (x|0), a constant string, a template literal
         with markup (own ${} are checked on their own), a call of a helper that builds escaped markup (SAFE_HELPERS),
         a ternary / || / && whose every branch is one of these, .map(... => `...`).join(...) (its template is checked)
  marked ${/*html-ok*/ expr} = HTML on purpose (built elsewhere from esc()); say in a comment why
  concat 2.1364.0 (#6297 (15)): a string concatenation into innerHTML / outerHTML (= and +=) or insertAdjacentHTML(pos, …)
         ('<b>' + name + '</b>'): each part by the same rules (a constant string, a template literal, a safe expression)
  else   reported as a finding. Old findings are the baseline (tools/innerhtml_baseline.json, "file|expression" -> count,
         no line numbers); a NEW one is red. The baseline only ever shrinks: --update rewrites it (never adds).

usage: python3 tools/check_innerhtml.py [-v] [--update] [--selftest]      exit 1 on a new finding (a fixed one only shows as a note)
Standard library only.
"""
import glob
import json
import os
import re
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import check_trh as T  # noqa: E402  (template reader, call_args)

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
BASE = os.path.join(ROOT, "tools", "innerhtml_baseline.json")
MARK = "/*html-ok*/"
# helpers whose result is markup built from escaped parts (checked at their definition) or plain safe text
SAFE_HELPERS = ("esc", "i18nEsc", "escA", "trh", "trnh", "icon", "ic", "svg", "sw")
TRS = ("tr", "trn")  # 2.1364.0 (#6297 (15)): safe as the whole ${} (check_trh.py), elsewhere only with a constant text + safe values
STR = re.compile(r"""(['"])(?:(?!\1)[^\\\n]|\\.)*\1$""")
NUM = re.compile(r"-?\d+(\.\d+)?$")
LEN = re.compile(r"[\w$.\[\]()?]+\.(length|size)$")
MATH = re.compile(r"(Math\.\w+|Number|parseInt|parseFloat)\(.*\)$", re.S)
MAPJ = re.compile(r"\.map\(.*=>\s*\(?\s*(`|esc\()", re.S)


def split_top(a, ops):
    """Split a on the top-level operators in ops (strings, brackets, templates skipped); ternary '?' ':' are kept apart."""
    parts, depth, j, start, n = [], 0, 0, 0, len(a)
    while j < n:
        c = a[j]
        if c in "'\"":
            m = re.compile(c + r"(?:[^" + c + r"\\\n]|\\.)*" + c).match(a, j)
            j = m.end() if m else j + 1
            continue
        if c == "`":
            _x, j = T.call_args(a, j - 1, tpl_only=True)
            continue
        if c in "([{":
            depth += 1
        elif c in ")]}":
            depth -= 1
        elif depth == 0:
            for op in ops:
                if a.startswith(op, j) and not (op == "?" and a[j + 1:j + 2] in ".?") and not (op == ":" and False):
                    parts.append(a[start:j])
                    start = j + len(op)
                    j = start - 1
                    break
        j += 1
    parts.append(a[start:])
    return [p.strip() for p in parts]


def safe(a, top=True, bad=None):
    """top: a is the whole ${} expression (a tr() there is check_trh.py's); bad: a list that gets every unsafe part."""
    a = a.strip()
    if not a or MARK in a:
        return True
    if a[0] in "'\"":
        return len(split_top(a, ["+"])) == 1 or all([safe(p, False, bad) for p in split_top(a, ["+"])])
    if a[0] == "`":
        return True  # a nested template inherits "markup" from its parent: its own ${} are checked on their own
    if a[0] == "(" and a[-1] == ")" and T.call_args(a, 0)[1] == len(a):
        return safe(a[1:-1], top, bad)
    q = split_top(a, ["?"])
    if len(q) > 1:  # ternary: cond ? x : y  (the condition is no output)
        br = split_top(a[len(q[0]) + 1:], [":"])
        return all([safe(x, False, bad) for x in ([br[0], ":".join(br[1:])] if len(br) > 1 else br)])
    for op in ("||", "??", "&&"):
        p = split_top(a, [op])
        if len(p) > 1:  # for && the left side is only a condition
            return all([safe(x, False, bad) for x in (p[1:] if op == "&&" else p)])
    p = split_top(a, ["+"])
    if len(p) > 1:  # 2.1364.0 (#6297 (15)): a concatenation is as safe as each of its parts
        return all([safe(x, False, bad) for x in p])
    if NUM.match(a) or LEN.match(a) or MATH.match(a) or re.match(r"\(.*\|\s*0\)$", a):
        return True
    m = re.match(r"([\w$.]+)\(", a)
    if m and m.group(1) in SAFE_HELPERS and T.call_args(a, m.end() - 1)[1] == len(a):
        return True
    if m and m.group(1) in TRS:
        args, end = T.call_args(a, m.end() - 1)
        if end == len(a):
            return top or _tr_safe(m.group(1), args)
    if MAPJ.search(a) and re.search(r"\.join\(", a):
        return True
    if bad is not None:
        bad.append(a)
    return False


def _tr_safe(fn, args):
    """tr('constant', safe…) / trn('one', 'other', n, safe…): the author's text with escaped or harmless values (n = a count,
    as check_trh.py)."""
    k = 2 if fn == "trn" else 1
    if len(args) < k or not all(STR.match(x) for x in args[:k]):
        return False
    rest = args[k:]
    if fn == "trn" and rest:  # n: a count (a name, a member, "x || 0", a number)
        if not re.fullmatch(r"[\w$.\[\]()?]+(\s*\|\|\s*\d+)?|-?\d+", rest[0]) and not safe(rest[0], False):
            return False
        rest = rest[1:]
    return all(safe(x, False) for x in rest)


SINK = re.compile(r"\.(?:innerHTML|outerHTML)\s*\+?=(?!=)|\.insertAdjacentHTML\s*\(")


def _stmt_end(src, j):
    """The end of the expression from j: ';' / ',' or a closing bracket at depth 0, or a line end that no operator carries on."""
    depth, n = 0, len(src)
    while j < n:
        c = src[j]
        if c in "'\"":
            m = re.compile(c + r"(?:[^" + c + r"\\\n]|\\.)*" + c).match(src, j)
            j = m.end() if m else j + 1
            continue
        if c == "`":
            _x, j = T.call_args(src, j - 1, tpl_only=True)
            continue
        if src.startswith("//", j) and depth == 0:
            return j
        if c in "([{":
            depth += 1
        elif c in ")]}":
            if depth == 0:
                return j
            depth -= 1
        elif depth == 0 and c in ";,":
            return j
        elif depth == 0 and c == "\n":
            before, after = src[:j].rstrip()[-1:], src[j:].lstrip()[:1]
            if before not in "+?:(,=|&" and after not in "+?:.|&":
                return j
        j += 1
    return n


def _code_only(a):
    """a without its string and template literals (a '+' inside a text is no concatenation)."""
    out, j, n = [], 0, len(a)
    while j < n:
        c = a[j]
        if c in "'\"":
            m = re.compile(c + r"(?:[^" + c + r"\\\n]|\\.)*" + c).match(a, j)
            j = m.end() if m else j + 1
            out.append('""')
            continue
        if c == "`":
            _x, j = T.call_args(a, j - 1, tpl_only=True)
            out.append('""')
            continue
        out.append(c)
        j += 1
    return "".join(out)


def scan_concat(src):
    """-> [(line, expression)] of the unsafe parts of a string concatenation into innerHTML / outerHTML / insertAdjacentHTML."""
    for m in SINK.finditer(src):
        if m.group(0).startswith(".insertAdjacentHTML"):
            args, _e = T.call_args(src, m.end() - 1)
            if len(args) < 2:
                continue
            rhs = args[1]
            pos = src.find(rhs, m.end())
        else:
            pos = m.end()
            while pos < len(src) and src[pos] in " \t":
                pos += 1
            rhs = src[pos:_stmt_end(src, pos)]
        if not re.search(r"(?<![+])\+(?![+=])", _code_only(rhs)):
            continue  # no concatenation: a template is checked above, a variable holds markup built elsewhere
        bad = []
        safe(rhs, False, bad)
        for p in bad:
            yield src.count("\n", 0, max(pos, 0)) + 1, "+ " + re.sub(r"\s+", " ", p).strip()


def scan(src):
    """-> [(line, expression)] of the unsafe ${} in every markup template (and of every concatenation into an HTML sink)."""
    yield from scan_concat(src)
    tpls = T.templates(src)
    for k, (_s, _parts, exprs, _p) in enumerate(tpls):
        if not T.html(tpls, k):
            continue
        for e in exprs:
            end = _expr_end(src, e)
            a = src[e:end]
            if not safe(a):
                yield src.count("\n", 0, e) + 1, re.sub(r"\s+", " ", a).strip()


def _expr_end(src, e):
    depth, j, n = 0, e, len(src)
    while j < n:
        c = src[j]
        if c in "'\"":
            m = re.compile(c + r"(?:[^" + c + r"\\\n]|\\.)*" + c).match(src, j)
            j = m.end() if m else j + 1
            continue
        if c == "`":
            _x, j = T.call_args(src, j - 1, tpl_only=True)
            continue
        if c in "([{":
            depth += 1
        elif c in ")]}":
            if c == "}" and depth == 0:
                return j
            depth -= 1
        j += 1
    return n


def collect():
    found = {}
    for p in sorted(glob.glob(os.path.join(ROOT, "static", "js", "**", "*.js"), recursive=True)):
        rel = os.path.relpath(p, ROOT)
        for line, ex in scan(open(p, encoding="utf-8").read()):
            found.setdefault(f"{rel}|{ex}", []).append(line)
    return found


def selftest():
    bad = ["`<b>${name}</b>`", "`<i>${a.title + 'x'}</i>`", "`<p>${x ? name : ''}</p>`", "`<p>${list.join('')}</p>`"]
    good = ["`<b>${esc(name)}</b>`", "`<b>${n}</b>`".replace("n", "3"), "`<p>${x ? esc(a) : ''}</p>`",
            "`<p>${a.length}</p>`", "`<p>${trh('{0}', n)}</p>`", "`<p>${/*html-ok*/ h}</p>`",
            "`<p>${rows.map(r => `<i>${esc(r)}</i>`).join('')}</p>`", "`<p>${esc(a) || ''}</p>`", "`no markup ${x}`", "`<p>${v ? ` s=\"${esc(v)}\"` : ''}</p>`",
            "`<p>${tr('Hello')}</p>`", "`<p class=\"${on ? 'a' : 'b'}\">${esc(x)}</p>`",
            # 2.1364.0 (#6297 (15)): tr() as the whole ${} (check_trh.py), else with a constant text and safe values; concatenations
            "`<p>${tr('Hi {0}', name)}</p>`", "`<p>${x ? tr('Hi {0}', esc(name)) : ''}</p>`",
            "`<p>${x ? trn('{0} file', '{0} files', n) : tr('none')}</p>`", "`<p>${esc(a) + ' · ' + esc(b)}</p>`",
            "el.innerHTML = '<b>' + esc(name) + '</b>';", "el.innerHTML = html;", "el.innerHTML = `<b>${esc(x)}</b>` + tr('Hello');",
            "el.insertAdjacentHTML('beforeend', '<i>' + esc(t.title) + '</i>');", "el.innerHTML = 'a+b';",
            "el.innerHTML = x ? '<b>' + esc(n) + '</b>' : '';"]
    # 2.1364.0 (#6297 (15)): what the guard did not see before
    bad += ["`<p>${x ? tr('Hi {0}', name) : ''}</p>`", "`<p>${x ? tr(label) : ''}</p>`", "`<p>${esc(a) + name}</p>`",
            "`<p>${x ? trn('{0} of {1}', '{0} of {1}', n, who) : ''}</p>`",
            "el.innerHTML = '<b>' + name + '</b>';", "el.outerHTML += '<b>' + x.name;",
            "el.insertAdjacentHTML('beforeend', '<i>' + t.title + '</i>');", "el.innerHTML = x ? '<b>' + n.name + '</b>' : '';",
            "el.innerHTML = '<b>' +\n  name +\n  '</b>';"]
    f = 0
    for s in bad:
        if not list(scan(s)):
            print("selftest: not reported:", s)
            f += 1
    for s in good:
        r = list(scan(s))
        if r:
            print("selftest: wrongly reported:", s, r)
            f += 1
    print("check_innerhtml selftest:", "FAILED %d" % f if f else "ok")
    return 1 if f else 0


def main(argv):
    if "--selftest" in argv:
        return selftest()
    found = collect()
    base = json.load(open(BASE, encoding="utf-8")) if os.path.exists(BASE) else {}
    cnt = {k: len(v) for k, v in found.items()}
    if "--update" in argv:
        new = {k: min(v, base.get(k, v)) for k, v in cnt.items() if (k in base or not base)}
        json.dump(dict(sorted(new.items())), open(BASE, "w", encoding="utf-8"), indent=0, ensure_ascii=False)
        print("check_innerhtml: baseline written,", len(new), "entries,", sum(new.values()), "findings")
        return 0
    out = []
    for k, n in sorted(cnt.items()):
        if n > base.get(k, 0):
            f, ex = k.split("|", 1)
            if ex.startswith("+ "):  # 2.1364.0 (#6297 (15)): a part of a concatenation into innerHTML / insertAdjacentHTML
                out.append(f"{f}:{found[k][-1]}: {ex[2:]} in a concatenation into innerHTML / insertAdjacentHTML is not escaped "
                           f"- esc() / trh(), or build it as a template; HTML on purpose: {MARK} in front of it")
                continue
            out.append(f"{f}:{found[k][-1]}: ${{{ex}}} in an HTML template is not escaped - esc() / tr() / trh(), "
                       f"HTML on purpose: ${{{MARK} …}}")
    stale = sorted(k for k, n in base.items() if cnt.get(k, 0) < n)
    for x in out:
        print(x)
    for k in stale:
        print(f"tools/innerhtml_baseline.json: fewer than recorded (good), `--update` shrinks the baseline: {k}")
    print(f"check_innerhtml: {len(out)} new finding(s), {sum(cnt.values())} in the baseline, {len(stale)} fixed since")
    return 1 if out else 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
