"""(#6534) The hosting switch and the operator's support address, low in the core so every layer can send a stuck person to
the support of a hosted server instead of "the admin of this server" (a self-hosted server keeps its admin sentences).
admin.hosting re-exports HOSTED / SUPPORT_EMAIL_ENV / support_email; the setting in Administration > Server wins."""
import os

from ..core.env import env_bool
from ..core.i18n import N_, tr
from ..core.db import gsetting

HOSTED = env_bool("KALMIDO_HOSTED", False)
SUPPORT_EMAIL_ENV = os.environ.get("KALMIDO_SUPPORT_EMAIL", "").strip()[:200]


def support_email(c):
    """The support address when one is set (setting / KALMIDO_SUPPORT_EMAIL), else '' -- (#2490): never an
    admin's own address (the client then says to ask the admin)."""
    return gsetting(c, "support_email") or SUPPORT_EMAIL_ENV or ""


def support_ask(c, selfhost, hosted, *a, lg=None):
    """A sentence that sends a person to someone: self-hosted `selfhost` (the server's admin) as before; hosted `hosted`
    with the support address as the last placeholder (both N_ texts, `a` = the other values), or `selfhost` when the
    operator set no address."""
    s = support_email(c) if HOSTED else ""
    return tr(hosted, *a, s, lg=lg) if s else tr(selfhost, *a, lg=lg)


# the sentences of exports and imports that send a person to the server admin, with their hosted twin (support_ask(c, *X))
SUP_EXPORT_SPACE = (N_("There is not enough space on the server for the export. Please ask the server admin."),
                    N_("There is not enough space on the server for the export. Please write to support: {0}"))
SUP_IMPORT_SPACE = (N_("There is not enough space on the server for the import. Please ask the server admin."),
                    N_("There is not enough space on the server for the import. Please write to support: {0}"))
SUP_EXPORT_FAILED = (N_("The export failed. Please try again later or ask the server admin (server log)."),
                     N_("The export failed. Please try again later or write to support: {0}"))
