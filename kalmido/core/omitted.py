"""2.1324.0 (#6589): what an export leaves out is said, never dropped silently.

Omitted collects (name, reason) while an export is built; write() puts a text file "not included.txt" (in the reader's
language, e.g. "nicht enthalten.txt") into the ZIP root with one line per item: name and reason. Nothing collected ->
no file. Used by the folder ZIP of the files (files/bulk.py) and the other ZIP exports (integrations/exporters.py, wiki).
Reasons are i18n keys (N_), translated when the file is written; only names the reader may see go in."""
from .i18n import N_, tr, trn

OMIT_FILE = N_("not included|file name of the list in a ZIP")
OMIT_HEAD = N_("These items are not in this ZIP:")
OMIT_MAX = 20000  # lines written; beyond that one line with the rest's count (the file stays small)


class Omitted:
    """The items an export leaves out: add(name, reason key, *values), then write(zipfile) once at the end."""

    def __init__(self, lg=None):
        self.lg = lg
        self.items = []  # [(name, reason key, values)]
        self.notes = []  # [(key, values)]: lines above the list (e.g. a count)

    def add(self, name, reason, *a):
        self.items.append((str(name or "").replace("\n", " ").replace("\r", " "), reason, a))

    def note(self, key, *a):
        self.notes.append((key, a))

    def __len__(self):
        return len(self.items)

    def __bool__(self):
        return bool(self.items or self.notes)

    def file_name(self, taken=()):
        """The file's name in the reader's language, made unique against taken (lower-case names of the ZIP root)."""
        base = tr(OMIT_FILE, lg=self.lg).replace("/", "_").replace("\\", "_").strip() or "not included"
        nm, i = base + ".txt", 2
        while nm.lower() in taken:
            nm = f"{base} ({i}).txt"
            i += 1
        return nm

    def text(self):
        out = [tr(k, *a, lg=self.lg) for k, a in self.notes]
        if self.items:
            if out:
                out.append("")
            out.append(tr(OMIT_HEAD, lg=self.lg))
            out.append("")
            for name, reason, a in self.items[:OMIT_MAX]:
                out.append(f"{name} - {tr(reason, *a, lg=self.lg)}")
            if len(self.items) > OMIT_MAX:
                out.append(trn("and {0} more", "and {0} more", len(self.items) - OMIT_MAX, lg=self.lg))
        return "\r\n".join(out) + "\r\n"

    def write(self, z, taken=()):
        """Writes the file into the open zipfile z when anything was collected -> its name (None: nothing left out)."""
        if not self:
            return None
        nm = self.file_name({str(t).lower() for t in taken})
        z.writestr(nm, self.text().encode("utf-8"))
        return nm


_WIP_KEYS = (N_('a link to another item, not a file'), N_('blocked by the virus scanner or not checked yet'), N_('the stored file is damaged or missing'), N_('in a locked (end-to-end encrypted) folder: open it in the app and download the files there'), N_('folder nested too deeply: what is inside is not included'), N_('locked with a password (end-to-end encrypted): the server only holds it as ciphertext'), N_('shared with you: only the projects you own are exported'), N_('Shared projects not included: {0}. Only the projects you own are in this export.'))  # WIP only
