#!/usr/bin/env python3
# kalmido-suite: fresh
"""#6535 (audit #4803, first hour of an office client): the help covers the first hour - the areas Organisation (create the
company, invite people and roles), Company & office (set up the office, who sees what, coming from another program,
e-invoices) and Account (an account or a new password, help from a person), each with its "Show me" places; one source
(docs/*.md -> /api/help, the same the agents read). A paragraph marked <!-- self-hosted --> / <!-- hosted --> shows only on
that kind of server (api/helpdocs.py hlp_hosting): the sentence "An admin of the server can switch these links off" is no
help on a hosted service.
freelancer-matrix: own (a person without an organisation reads the same help)
Red without the fix: the three areas and their sections are missing; the self-hosting sentence and the marker comment show
on a hosted server.
usage: p6535_help_firsthour_test.py <datadir>   (P6535_NOSTART=1: the container runs already, not hosted)"""
import kt
from kt import B, check
from freelancer_fixture import freelancer

INVITE = "team#how-to-invite-someone-without-an-account-by-a-link"
HUMAN = "team#how-to-get-help-from-a-person"
NEW = {"org": ["team#how-to-create-your-company", "team#how-to-invite-people-and-give-them-a-role"],
       "company": ["office#how-to-set-up-your-office", "office#how-to-decide-who-sees-what-in-the-office",
                   "office#how-to-come-from-another-program", "office#how-to-send-e-invoices"],
       "account": ["team#how-to-create-an-account-or-get-a-new-password", HUMAN]}


def section(s, key, lang):
    s.patch(B + "/api/settings", json={"lang": lang})
    r = s.get(B + "/api/help/section", params={"key": key})
    return r.json() if r.ok else {}


def run(hosted):
    tag = "hosted" if hosted else "self-hosted"
    A = kt.setup()
    _fid, F = freelancer(B, A)
    for s, who in ((A, "admin"), (F, "freelancer")):
        s.patch(B + "/api/settings", json={"lang": "de"})
        j = s.get(B + "/api/help").json()
        areas = {a["area"]: a for a in j.get("areas", [])}
        for area, keys in NEW.items():
            got = [x["key"] for x in areas.get(area, {}).get("sections", [])]
            check(got == keys, f"{tag} {who}: the area {area} with its sections {got}")
        check([a for a in areas if a in NEW] == ["org", "company", "account"], f"{tag}: the new areas come last, in order")
        check(areas.get("company", {}).get("title") == "Firma & Büro" and areas.get("org", {}).get("title") == "Organisation"
              and areas.get("account", {}).get("title") == "Konto", f"{tag}: the areas in the words of the settings")
        check(all(2 <= len(a["sections"]) <= 4 for a in areas.values()), f"{tag}: each area 2-4 short sections")
    sec = section(F, "team#how-to-create-your-company", "de")
    check(sec.get("title") == "Deine Firma anlegen" and "**Organisation hinzufügen**" in sec.get("text", "")
          and [x.get("target") for x in sec.get("steps", [])] == ["settings.open", "settings.account", "org.add"],
          f"{tag}: the German section with its Show me steps {sec.get('title')} {sec.get('steps')}")
    sec = section(F, "office#how-to-come-from-another-program", "de")
    check("Mit der Firma auf einen anderen Server umziehen" in " ".join(sec.get("text", "").split()), f"{tag}: moving data is linked, not written twice")
    for lang, sentence, mail, report in (("de", "Ein Admin des Servers kann diese Links ausschalten", "Dem Support schreiben", "Problem melden"),
                                         ("en", "An admin of the server can switch these links off", "Write to support", "Report a problem")):
        inv, hum = section(F, INVITE, lang), section(F, HUMAN, lang)
        txt = inv.get("text", "") + hum.get("text", "")
        check(inv.get("text") and "<!--" not in txt, f"{tag} {lang}: no marker comment in the text")
        check((sentence in inv.get("text", "")) == (not hosted), f"{tag} {lang}: the self-hosting sentence {'hidden' if hosted else 'shown'}")
        check((mail in hum.get("text", "")) == hosted and (report in hum.get("text", "")) == (not hosted),
              f"{tag} {lang}: help from a person - the support of the service or the admin of the own server")
        check("Withdraw" in inv.get("text", "") or "Zurückziehen" in inv.get("text", ""), f"{tag} {lang}: the rest of the section stays")
    r = F.get(B + "/api/search", params={"kind": "help", "q": "Leitweg"})
    check(r.ok and any(h["key"] == "office#how-to-send-e-invoices" for h in r.json().get("data", [])), f"{tag}: the search finds the e-invoice section")


kt.fresh(prefix="P6535")
run(False)
if not kt.nostart("P6535"):
    kt.fresh(env={"KALMIDO_HOSTED": "1", "KALMIDO_SUPPORT_EMAIL": "support@example.test"}, prefix="P6535")
    run(True)

raise SystemExit(kt.done("p6535_help_firsthour_test"))
