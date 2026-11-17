"""2.1337.0 (#6876): the organisation import's step for a flow (admin/oi_store.py _rule) called directly inside the app
container with a crafted archive row: a flow with a webhook address and a secret. -> (stored value of doc_rules.data or
None, the output on failure). Used by p2581_c_flows (server without a key) and p2581_e_flowreview (with a key)."""
import json
import subprocess

from kt import CT

SECRET = "geheim-6876-importiert"
URL = "https://hooks.example.com/import-6876"

CODE = """
import json, types
from kalmido.admin import oi_store as O
src = {"data": json.dumps({"name": "Importiert", "kind": "any", "match": "Importfall", "tags": ["Importtag"],
                           "webhook": %r, "hook_secret": %r})}
run = types.SimpleNamespace(put=lambda *a: None, m=lambda *a: None, warning=lambda *a: None)
ctx = types.SimpleNamespace(space=%r, uid=%d, who=lambda x: None)
d = O._rule(c, run, src, {}, ctx)
print("RESULT=" + json.dumps((d or {}).get("data")))
"""


def import_flow(uid, org=None):
    code = CODE % (URL, SECRET, org, uid)
    body = "\n".join("    " + x for x in code.strip().split("\n"))
    out = subprocess.run(["docker", "exec", CT, "python", "-c",
                          "import app\nfrom kalmido.core.db import connect\nfrom kalmido.core.pg import system_ctx\nc = connect()\n"
                          "with system_ctx(c):\n" + body + "\nc.close()"], capture_output=True, text=True)
    text = out.stdout + out.stderr
    line = next((x for x in text.splitlines() if x.startswith("RESULT=")), None)
    return (json.loads(line[7:]) if line else None), text[-1500:]
