"""Guards for files the engine did not write: client uploads (intake/), questionnaire workbooks a customer sent,
and anything else read from a pull request. They come from outside, so they are checked before parsing:

  - a regular file inside the folder it was found in (no symlinks, nothing that resolves elsewhere: a symlink in
    intake/ must never send a runner file to Claude or into a report);
  - a size limit, and for Office files (zip packages) limits on the unpacked size, compression ratio and member
    count, so a zip bomb fails fast instead of exhausting the runner;
  - XML with a DTD is refused (Office XML never has one; a DTD is how entity-expansion attacks start), and
    ElementTree never fetches external entities;
  - PDFs are read to a page limit.

Values the engine writes into spreadsheets or CSV for people to open are neutralised when they would start a
formula (`=`, `+`, `-`, `@`, tab, carriage return), so text from a client document can't run in an auditor's Excel.
"""
from __future__ import annotations

import re
import zipfile
from pathlib import Path

MAX_FILE_BYTES = 50 * 1024 * 1024          # one upload
MAX_UNZIPPED_BYTES = 150 * 1024 * 1024     # an Office file, unpacked (openpyxl holds a sheet in memory)
MAX_RATIO = 200                             # unpacked / packed, per member, for members over 1 MB unpacked
MAX_MEMBERS = 20_000
MAX_PDF_PAGES = 600
FORMULA_START = ("=", "+", "-", "@", "\t", "\r", "\uff1d", "\uff0b", "\uff0d", "\uff20")   # and full-width forms


class UnsafeFile(ValueError):
    """A file the engine refuses to parse; the message says why, in words for the report."""


def check_file(path: Path, inside: Path | None = None, max_bytes: int = MAX_FILE_BYTES) -> None:
    p = Path(path)
    if p.is_symlink():
        raise UnsafeFile("it is a symbolic link; upload the file itself")
    if not p.is_file():
        raise UnsafeFile("it is not a regular file")
    if inside is not None:
        try:
            p.resolve().relative_to(Path(inside).resolve())
        except ValueError:
            raise UnsafeFile("it resolves to a location outside the folder it was uploaded to") from None
    size = p.stat().st_size
    if size > max_bytes:
        raise UnsafeFile(f"it is {size // (1024 * 1024)} MB; the limit is {max_bytes // (1024 * 1024)} MB")


def check_zip(path: Path) -> None:
    """An Office file (or any zip) whose unpacked size, ratio or member count would be a zip bomb."""
    try:
        with zipfile.ZipFile(path) as z:
            infos = z.infolist()
    except zipfile.BadZipFile:
        raise UnsafeFile("it is not a valid Office file (not a zip package)") from None
    if len(infos) > MAX_MEMBERS:
        raise UnsafeFile(f"it holds {len(infos)} parts; the limit is {MAX_MEMBERS}")
    total = 0
    for i in infos:
        total += i.file_size
        if i.file_size > 1024 * 1024 and i.compress_size and i.file_size / i.compress_size > MAX_RATIO:
            raise UnsafeFile(f"part {i.filename} unpacks {i.file_size // i.compress_size}x; it looks like a zip bomb")
        name = i.filename.replace("\\", "/")
        if name.startswith("/") or ".." in name.split("/"):
            raise UnsafeFile(f"part {i.filename} has a path outside the package")
    if total > MAX_UNZIPPED_BYTES:
        raise UnsafeFile(f"it unpacks to {total // (1024 * 1024)} MB; the limit is {MAX_UNZIPPED_BYTES // (1024 * 1024)} MB")


def within(path: Path, root: Path) -> Path | None:
    """`root` when `path`, as given (before resolving links), is inside it, else None: a file in the repository
    must not resolve out of it through a symlinked folder, while a path a person types on the command line from
    elsewhere (their Downloads folder) is theirs to choose."""
    import os
    given, base = os.path.abspath(path), os.path.abspath(root)
    return Path(root) if given == base or given.startswith(base + os.sep) else None


def check_upload(path: Path, inside: Path | None = None) -> None:
    """Every check that fits the file's type."""
    check_file(path, inside)
    if Path(path).suffix.lower() in (".xlsx", ".xlsm", ".docx", ".pptx", ".zip"):
        check_zip(path)


def _refuse_dtd(*_):
    raise UnsafeFile("its XML declares a DTD or entities, which Office files never do")


def xml_root(data: bytes | str):
    """Parse XML from an untrusted package. A DTD (and so any entity declaration) is refused: expat reports it
    whatever the encoding (UTF-8, UTF-16 with a BOM) or position, before ElementTree parses anything."""
    import xml.etree.ElementTree as ET  # nosec B405 - DTDs refused by the expat pass below; no external fetches
    from xml.parsers import expat
    body = data if isinstance(data, (bytes, bytearray)) else data.encode("utf-8")
    p = expat.ParserCreate()
    p.StartDoctypeDeclHandler = _refuse_dtd
    p.EntityDeclHandler = _refuse_dtd
    p.UnparsedEntityDeclHandler = _refuse_dtd
    p.ExternalEntityRefHandler = lambda *_: _refuse_dtd()
    try:
        p.Parse(body, True)
    except expat.ExpatError as exc:
        raise UnsafeFile(f"its XML is not well formed ({exc})") from None
    return ET.fromstring(body)  # nosec B314 - see above


def md_text(s) -> str:
    """Text from a document or a file name, made inert for a GitHub comment or Markdown report: no links or
    images (no data leaving through an image URL), no @mentions, no HTML (no hidden comments), no formatting."""
    s = " ".join(str(s if s is not None else "").split())
    s = s.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")
    s = re.sub(r"([\\`*_\[\]()!|#~{}])", r"\\\1", s)
    return s.replace("@", "@\u2060")      # a word joiner after @ stops GitHub's mention parser


def md_code(s) -> str:
    """A file name or id shown as code: backticks can't end the span early, and nothing in it is live."""
    s = " ".join(str(s if s is not None else "").split()).replace("`", "'")
    return f"`{s}`"


def cell_text(v):
    """A value for a spreadsheet or CSV cell that a person will open: text that would start a formula gets a
    leading apostrophe, which Excel shows as plain text. Numbers, dates and booleans pass through."""
    if isinstance(v, str) and v.lstrip(" \n\u3000").startswith(FORMULA_START):
        return "'" + v
    return v


# Files that hold local settings or secrets and must never be in a repository: Claude Code's local settings keep
# permission rules (which can include a pasted token), .env files hold keys, and key or certificate files are keys.
SECRET_FILE_NAMES = {"settings.local.json": ".claude", "CLAUDE.local.md": None}
SECRET_FILE_RE = re.compile(r"(^|/)(\.env(\..*)?|[^/]*\.(pem|key|p12|pfx))$")
SECRET_FILE_OK = re.compile(r"(^|/)\.env\.(example|sample|template)$")


def secret_files(names) -> list[str]:
    """The paths, from a list of tracked files, that look like local settings or secrets."""
    out = []
    for n in names:
        n = str(n).replace("\\", "/")
        base, parent = n.rsplit("/", 1)[-1], (n.rsplit("/", 2)[-2] if n.count("/") else "")
        if base in SECRET_FILE_NAMES and SECRET_FILE_NAMES[base] in (None, parent):
            out.append(n)
        elif SECRET_FILE_RE.search(n) and not SECRET_FILE_OK.search(n):
            out.append(n)
    return out


def tracked_secret_files(repo: Path) -> list[str]:
    """secret_files() over what git tracks in `repo` ([] outside a git repository)."""
    import subprocess  # nosec B404 - fixed argv, no shell
    try:
        r = subprocess.run(["git", "-C", str(repo), "ls-files", "-z"], capture_output=True, timeout=20)  # nosec B603 B607
    except (OSError, subprocess.SubprocessError):
        return []
    if r.returncode != 0:
        return []
    return secret_files(x for x in r.stdout.decode("utf-8", "replace").split("\0") if x)
