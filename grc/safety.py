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

import zipfile
from pathlib import Path

MAX_FILE_BYTES = 50 * 1024 * 1024          # one upload
MAX_UNZIPPED_BYTES = 400 * 1024 * 1024     # an Office file, unpacked
MAX_RATIO = 200                             # unpacked / packed, per member, for members over 1 MB unpacked
MAX_MEMBERS = 20_000
MAX_PDF_PAGES = 600
FORMULA_START = ("=", "+", "-", "@", "\t", "\r")


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


def check_upload(path: Path, inside: Path | None = None) -> None:
    """Every check that fits the file's type."""
    check_file(path, inside)
    if Path(path).suffix.lower() in (".xlsx", ".xlsm", ".docx", ".pptx", ".zip"):
        check_zip(path)


def xml_root(data: bytes | str):
    """Parse XML from an untrusted package. A DTD (and so any entity declaration) is refused."""
    import xml.etree.ElementTree as ET  # nosec B405 - DTDs are refused below and ElementTree never fetches external entities
    head = data[:4096] if isinstance(data, (bytes, bytearray)) else data[:4096].encode("utf-8", "replace")
    body = data if isinstance(data, (bytes, bytearray)) else data.encode("utf-8")
    if b"<!DOCTYPE" in head.upper() or b"<!ENTITY" in body.upper():
        raise UnsafeFile("its XML declares a DTD or entities, which Office files never do")
    return ET.fromstring(body)  # nosec B314 - see above


def cell_text(v):
    """A value for a spreadsheet or CSV cell that a person will open: text that would start a formula gets a
    leading apostrophe, which Excel shows as plain text. Numbers, dates and booleans pass through."""
    if isinstance(v, str) and v.startswith(FORMULA_START):
        return "'" + v
    return v
