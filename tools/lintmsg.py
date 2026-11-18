#!/usr/bin/env python3
"""The shared wording and the shared ratchet of the own lint checks (tools/check_*.py, .semgrep/*.yml).

A red check is read first by an agent that wants the step green again. A bare "finding in x.py" invites the cheapest way out:
a suppression marker, a raised baseline or a second helper next to the rule. So every own check says, after its findings,
why the rule exists and what the right way is, and that the way out is the fix:

  if __name__ == "__main__":
      import lintmsg
      with lintmsg.red_hint("check_x", WHY, INSTEAD):
          sys.exit(main(sys.argv))

On a red exit (SystemExit with a code other than 0 / None) three lines follow the findings (stdout, after them, so a tail of
the output shows them too):

  check_x: Why: <WHY>
  check_x: Instead: <INSTEAD>
  check_x: Do not suppress it and do not build around it: fix the cause. A marker only with its reason in the same comment.

The ratchet (counts(), compare(), lowered()) is the one of tools/check_suppress.py and tools/check_rules.py: per rule a count
per file; the rule's TOTAL may never rise (a file may go up when another goes down by as much, so moving code is no finding),
--update writes lower numbers only. The baseline layout {"rule": {"total": n, "files": {path: n}}} is what
tools/baseline_merge.py merges by value (two packages that both lowered = the lower number, "total" recomputed).
Standard library only.
"""
import contextlib
import json
import os
import sys

NOT = "Do not suppress it and do not build around it: fix the cause. A marker only with its reason in the same comment."


def hint(tool, why, instead):
    """The three lines a red check prints after its findings."""
    return [f"{tool}: Why: {why}", f"{tool}: Instead: {instead}", f"{tool}: {NOT}"]


def say(tool, why, instead, out=None):
    out = out or sys.stdout
    for ln in hint(tool, why, instead):
        print(ln, file=out)


@contextlib.contextmanager
def red_hint(tool, why, instead):
    """Runs the check's main block; a red exit (a SystemExit with a code other than 0 / None) prints hint() after the
    findings and exits with the same code. An exception of the check itself is no finding and gets no hint."""
    try:
        yield
    except SystemExit as e:
        if e.code not in (0, None):
            sys.stdout.flush()
            say(tool, why, instead)
            sys.stdout.flush()
        raise


# --- the ratchet ------------------------------------------------------------------------------------------------------

def load(path):
    """{rule: {"total": n, "files": {path: n}}} of a baseline file ({} when there is none)."""
    if not os.path.exists(path):
        return {}
    with open(path, encoding="utf-8") as f:
        data = json.load(f)
    out = {}
    for rule, v in (data.get("rules") or {}).items():
        files = {k: int(n) for k, n in (v.get("files") or {}).items()}
        out[rule] = {"total": int(v.get("total", sum(files.values()))), "files": files}
    return out


def save(path, about, base):
    data = {"about": about, "rules": {r: {"total": v["total"], "files": dict(sorted(v["files"].items()))}
                                      for r, v in sorted(base.items()) if v["total"]}}
    with open(path, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=1, ensure_ascii=False)
        f.write("\n")


def as_counts(per_file):
    """{rule: {path: n}} -> {rule: {"total": n, "files": {path: n}}} (zero counts left out)."""
    out = {}
    for rule, files in per_file.items():
        files = {p: n for p, n in files.items() if n}
        if files:
            out[rule] = {"total": sum(files.values()), "files": files}
    return out


def compare(now, base, sharp):
    """(rose, fell): rose = [(rule, now, allowed, [(path, n, allowed_in_file)])] for every rule whose total went up,
    the files above their own number named first; fell = [(rule, now, before)] for totals that went down (lower them)."""
    rose, fell = [], []
    for rule in sorted(set(now) | set(base)):
        n = now.get(rule, {}).get("total", 0)
        b = base.get(rule, {}).get("total", 0)
        if n > b:
            nf, bf = now.get(rule, {}).get("files", {}), base.get(rule, {}).get("files", {})
            up = sorted(((p, k, bf.get(p, 0)) for p, k in nf.items() if k > bf.get(p, 0)), key=lambda x: (x[2] - x[1], x[0]))
            rose.append((rule, n, b, up, sharp(rule)))
        elif n < b:
            fell.append((rule, n, b))
    return rose, fell


def lowered(now, base):
    """The baseline after --update: a rule whose total fell or stayed takes today's files; a rule above its number keeps
    the old entry (it stays red); a rule the baseline did not hold is not added; nothing ever rises."""
    out = {}
    for rule, b in base.items():
        n = now.get(rule)
        if n is None:
            continue
        out[rule] = {"total": n["total"], "files": dict(n["files"])} if n["total"] <= b["total"] else b
    return out


def report(tool, rose, fell, label, update_cmd):
    """The lines of compare()'s result; returns the number of red rules."""
    red = 0
    for rule, n, b, up, is_sharp in rose:
        where = ", ".join(f"{p} {k} (was {a})" for p, k, a in up[:6]) + (" ..." if len(up) > 6 else "")
        tag = "" if is_sharp else "notice (not red yet): "
        print(f"{tool}: {tag}{label(rule)}: {n}, the baseline allows {b} - more in: {where or '?'}")
        red += 1 if is_sharp else 0
    for rule, n, b in fell:
        print(f"{tool}: {label(rule)}: {n} (baseline {b}) - lower it: {update_cmd}")
    return red
