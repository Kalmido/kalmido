"""2.146.0 (#2453 #2455 #2457): the one in-memory ZIP reader of the importers -- the bank import of 2.144.1 (#2450,
office/bank.py), receipts, the household budget and contacts read a ZIP the user picked here. Nothing is ever unpacked to
disk and no name of an entry is used as a path.

Rules (2.144.1 review, kept as they were): the entry count of the end record is checked before zipfile builds an object
per entry (zip64 is not taken), folders and the hidden files of packing systems (__MACOSX/, ._x, .x) are left out, nested
ZIPs and other types are skipped (never opened), encrypted entries get a message, the sizes in the ZIP's header are never
trusted (reading stops one byte after the limit), a broken entry never stops the others.

  zip_read(data, exts, file_max, total_max, entries_max) -> ZipRead(files [(name, bytes)], errors [{file, error}],
                                                             skipped [names], n)   raises ZipLimit (a translated text)
  is_zip(name, data)   a ZIP by name or by its first bytes
  base_name(v)         the file name of an upload / entry (no path, no control characters)

2.1282.0 (#6426): the check before zipfile, for EVERY ZIP reader of the app (importers, account / organisation import,
knowledge import, Paperless export, .xlsx readers). zipfile builds one object per entry of the central directory (about
336 bytes of memory per 46 bytes of file) before a caller sees its first entry, and it takes the directory's size from a
zip64 record in front of the end record when there is one -- an entry limit checked on infolist() comes too late, and a
check of the end record alone is passed with a zip64 record. zip_guard reads the end record and the zip64 records itself,
counts the directory's entries without building anything and refuses before zipfile is called:

  zip_guard(f, entries_max, zip64=True) -> the number of entries   raises ZipOver (too many entries / directory too large)
                                                                    or ZipBad (no readable ZIP; zip64=False: any zip64 mark)
  json_guard(raw, nodes_max, left=None) -> the number of nodes of a JSON text (UTF-8 bytes), counted BEFORE json.loads;
                                           raises ZipOver above nodes_max (left = [nodes left] of a budget over several
                                           parts), ZipBad for a zero byte (UTF-16 / UTF-32)"""
import io
import struct
import unicodedata
import zipfile

from .i18n import tr

ZIP_ENTRIES_MAX = 2000  # entries in a ZIP's central directory, checked before anything is read
ZIP_FILES_MAX = 400  # wanted files of one ZIP
ZIP_TOTAL_MAX = 60 * 1024 * 1024  # all wanted files together, unpacked


class ZipLimit(ValueError):
    """A hard limit of the whole ZIP (too many entries / files, too large together): the caller answers 400 with the text."""


class ZipOver(ValueError):
    """zip_guard / json_guard: more entries (or nodes) than the caller allows. No text: every caller has its own."""


class ZipBad(ValueError):
    """zip_guard: not a ZIP that zipfile could read (or a zip64 one where the caller takes none)."""


ZIP_CD_ENTRY = 46 + 256  # bytes of the central directory allowed per entry (46 fixed + name, extra field and comment on average)
ZIP_CD_SLACK = 64 * 1024
_EOCD, _LOC64, _REC64, _CDH = b"PK\x05\x06", b"PK\x06\x07", b"PK\x06\x06", b"PK\x01\x02"


def _at(f, pos, n):
    """n bytes at pos (fewer at the end of the file); a raw file may answer short reads."""
    if pos < 0:
        return b""
    f.seek(pos)
    out = f.read(n) or b""
    if len(out) >= n or not out:
        return out
    out = bytearray(out)
    while len(out) < n:
        b = f.read(n - len(out))
        if not b:
            break
        out += b
    return bytes(out)


_CD_WINDOW = 1024 * 1024


def _cd_count(f, start, size, stop):
    """The entries of a central directory of `size` bytes at `start`, walked the way zipfile walks it (46 bytes + name +
    extra + comment each, until `size` bytes are used) without building an object, in windows of 1 MB (the directory is
    never held as a whole). None when it is not a clean directory (zipfile would refuse it too, if it starts there);
    stops counting above `stop`."""
    if start < 0:
        return None
    n = done = 0  # done: bytes of the directory walked so far
    buf, i = b"", 0
    while done < size:
        if len(buf) - i < 46:
            want = min(size - done - (len(buf) - i), _CD_WINDOW)
            if want <= 0:
                return None  # fewer than 46 bytes are left
            more = _at(f, start + done + (len(buf) - i), want)
            if len(more) != want:
                return None
            buf, i = buf[i:] + more, 0
            continue
        if buf[i:i + 4] != _CDH:
            return None
        a, b, c = struct.unpack_from("<HHH", buf, i + 28)
        step = 46 + a + b + c
        if done + step > size:
            return None
        done += step
        n += 1
        if n > stop:
            return n
        if i + step <= len(buf):
            i += step
        else:
            buf, i = b"", 0  # the name runs over the window: the next read starts behind it
    return n


def zip_guard(f, entries_max, zip64=True):
    """f: the ZIP as bytes or as a seekable binary file (it is left at any position; zipfile seeks itself).
    Every place zipfile of any Python version may take the directory's size and count from is read: the end record (found
    as zipfile finds it: at the very end, else the last signature in the last 64 KB) and, behind a zip64 locator, the
    zip64 record right in front of the locator and the one at the locator's offset. The largest values count. The entries
    are counted from the directory itself (the count fields are not trusted: zipfile ignores them and reads by size);
    where the directory cannot be walked the count is the most that fits into its size."""
    if isinstance(f, (bytes, bytearray, memoryview)):
        f = io.BytesIO(f)
    try:
        f.seek(0, 2)
        end = f.tell()
        tail = _at(f, end - 22, 22)
        if len(tail) == 22 and tail[:4] == _EOCD and tail[-2:] == b"\0\0":
            e = end - 22
        else:
            base = max(end - 65535 - 22, 0)
            buf = _at(f, base, 65535 + 22)
            i = buf.rfind(_EOCD)
            if i < 0 or len(buf) - i < 22:
                raise ZipBad()
            e, tail = base + i, buf[i:i + 22]
        cnt_disk, cnt, size, off = struct.unpack_from("<HHII", tail, 8)
        found = [(max(cnt, cnt_disk), size, e)]  # (entries said, directory bytes, where the directory ends)
        loc = _at(f, e - 20, 20)
        if len(loc) == 20 and loc[:4] == _LOC64:
            if not zip64:
                raise ZipBad()
            for p in {e - 20 - 56, struct.unpack_from("<Q", loc, 8)[0]}:
                rec = _at(f, p, 56) if 0 <= p <= end else b""
                if len(rec) == 56 and rec[:4] == _REC64:
                    c1, c2, sz = struct.unpack_from("<QQQ", rec, 24)
                    found.append((max(c1, c2), sz, p))
                    if p == e - 20 - 56:
                        # a zip64 record right in front of the locator: every Python takes a zip64 record then, never the end
                        # record's own values (a writer leaves 0xFFFF there, or the size of a directory that ends 76 bytes
                        # earlier -- walked from the end record it would count as "the most that fits")
                        found[0] = None
        elif not zip64 and (cnt == 0xFFFF or cnt_disk == 0xFFFF or size == 0xFFFFFFFF or off == 0xFFFFFFFF):
            raise ZipBad()
        most = 0
        for said, sz, stop_at in [x for x in found if x]:
            if said > entries_max or sz > entries_max * ZIP_CD_ENTRY + ZIP_CD_SLACK:
                raise ZipOver()
            n = _cd_count(f, stop_at - sz, sz, entries_max)
            n = sz // 46 if n is None else n
            if n > entries_max:
                raise ZipOver()
            most = max(most, n)
        return most
    except (OSError, EOFError, struct.error, ValueError) as x:
        if isinstance(x, (ZipOver, ZipBad)):
            raise
        raise ZipBad() from None


_JSON_WINDOW = 1024 * 1024


def json_guard(raw, nodes_max, left=None):
    """The nodes (values and containers) json.loads would build from the JSON bytes (UTF-8): commas + opening brackets,
    counted outside of strings, + 1. A text of tiny values takes over 20 times its size in memory once it is parsed (an
    empty object: 3 bytes of text, 72 of memory), so a byte limit alone does not hold the memory. Raises ZipOver above
    nodes_max or above what is left of the caller's budget (left[0] is lowered by the count), ZipBad for a text with a
    zero byte (no JSON in UTF-8: json.loads would read it as UTF-16 / UTF-32, where this count means nothing).
    The text is walked in windows of 1 MB with bytes methods only (no pattern, nothing kept per string): the count itself
    costs a few MB and stops at the limit, whatever the text is made of."""
    if b"\0" in raw:
        raise ZipBad()
    cap = nodes_max if left is None else min(nodes_max, left[0])
    n, inside, carry = 1, False, False  # inside: in a string; carry: the window before ended in an escaping backslash
    view = memoryview(raw)
    for o in range(0, len(view), _JSON_WINDOW):
        c = bytes(view[o:o + _JSON_WINDOW])
        if carry:
            c, carry = c[1:], False  # the escaped byte
        if (len(c) - len(c.rstrip(b"\\"))) % 2:
            c, carry = c[:-1], True
        # escaped backslashes go first (pairs from the left of every run), then what is left in front of a quote escapes it
        # (an empty string, two quotes in a row, changes nothing and goes too: a text of quotes costs one pass)
        segs = c.replace(b"\\\\", b"").replace(b'\\"', b"").replace(b'""', b"").split(b'"')
        out = b"".join(segs[1 if inside else 0::2])
        if not len(segs) % 2:
            inside = not inside
        n += out.count(b",") + out.count(b"[") + out.count(b"{")
        if n > cap:
            raise ZipOver()
    if left is not None:
        left[0] -= n
    return n


class ZipRead:
    def __init__(self):
        self.files, self.errors, self.skipped, self.n, self.size = [], [], [], 0, 0


def base_name(v, n=200):
    v = v if isinstance(v, str) else ""
    v = v.replace("\\", "/").rstrip("/").rsplit("/", 1)[-1]
    return "".join(ch for ch in v if unicodedata.category(ch)[0] != "C").strip()[:n]


def is_zip(name, data):
    return (name or "").casefold().endswith(".zip") or data[:4] == b"PK\x03\x04"


def _hidden(raw, base):
    return not base or raw.startswith("__MACOSX/") or "/__MACOSX/" in raw or base.startswith(".")


def zip_read(data, exts, file_max, total_max=ZIP_TOTAL_MAX, entries_max=ZIP_ENTRIES_MAX, files_max=ZIP_FILES_MAX):
    """The wanted entries (name ends with one of exts, casefolded) of the ZIP bytes. A file over file_max is an error
    entry, not a stop; total_max / files_max / entries_max stop the whole ZIP (ZipLimit). An unreadable ZIP gives one
    error entry with the name ""."""
    out = ZipRead()
    # 2.1282.0 (#6426): the end record AND a zip64 record in front of it are read before zipfile (zip_guard); a zip64 ZIP is
    # refused here for real (zipfile followed its record although the end record alone had been checked)
    try:
        zip_guard(data, entries_max, zip64=False)
    except ZipOver:
        raise ZipLimit(tr("The ZIP file holds too many entries (at most {0})", entries_max)) from None
    except ZipBad:
        out.errors.append({"file": "", "error": tr("The ZIP file cannot be read")})
        return out
    try:
        zf = zipfile.ZipFile(io.BytesIO(data))
        infos = zf.infolist()
    except Exception:  # BadZipFile, a broken zip64 locator (struct.error) ...: never a 500
        out.errors.append({"file": "", "error": tr("The ZIP file cannot be read")})
        return out
    if len(infos) > entries_max:
        raise ZipLimit(tr("The ZIP file holds too many entries (at most {0})", entries_max))
    exts = tuple(x.casefold() for x in exts)
    for info in infos:
        raw = info.filename.replace("\\", "/")
        base = base_name(raw)
        if info.is_dir() or _hidden(raw, base):
            continue  # folders and the hidden files of the packing system
        if not base.casefold().endswith(exts):
            out.skipped.append(base)  # nested ZIPs included: never opened
            continue
        out.n += 1
        if out.n > files_max:
            raise ZipLimit(tr("At most {0} files per import", files_max))
        if info.flag_bits & 0x1:
            out.errors.append({"file": base, "error": tr("The file is encrypted; please pack it without a password")})
            continue
        if info.file_size > file_max:  # 2.238.0 C (#2873): the header already says too large, nothing is unpacked for it (zipfile never
            # returns more than the header size, so no entry is read only to be thrown away)
            out.errors.append({"file": base, "error": tr("The file is too large (at most {0} MB)", max(1, file_max // (1024 * 1024)))})
            continue
        try:  # the sizes in the ZIP's header are never trusted: reading stops one byte after the limit
            with zf.open(info) as f:
                part = f.read(file_max + 1)
        except Exception:  # BadZipFile, zlib.error, an unknown compression ...: a broken entry never stops the others
            out.errors.append({"file": base, "error": tr("The file cannot be read")})
            continue
        if len(part) > file_max:
            out.errors.append({"file": base, "error": tr("The file is too large (at most {0} MB)", max(1, file_max // (1024 * 1024)))})
            continue
        out.size += len(part)
        if out.size > total_max:
            raise ZipLimit(tr("The files are too large together (at most {0} MB)", total_max // (1024 * 1024)))
        out.files.append((base, part))
    return out
