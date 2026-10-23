"""Thin wrapper around poppler's ``pdftotext`` CLI.

Chosen over pdfplumber/pypdf after a direct comparison on a real module-table
page (see studyrag-decisions-log.md, 2026-10-14): ``-raw`` mode gives correct
characters (no umlaut mojibake) *and* correct sequential label-to-value order
in one pass, so there's no library-mixing or character-patching needed.
"""

from __future__ import annotations

import shutil
import subprocess

PAGE_BREAK = "\f"

_PDFTOTEXT = shutil.which("pdftotext")
_PDFINFO = shutil.which("pdfinfo")


class PdfTextError(RuntimeError):
    """Raised when poppler's pdftotext/pdfinfo cannot be found or fails."""


def extract_text(
    pdf_path: str,
    first_page: int | None = None,
    last_page: int | None = None,
) -> str:
    """Extract text from a PDF with poppler's ``pdftotext -raw -enc UTF-8``.

    ``first_page``/``last_page`` are 1-indexed and inclusive, matching
    pdftotext's own ``-f``/``-l`` flags. Pages remain separated by the
    original form-feed (``\\f``) characters pdftotext inserts, so callers
    that need to know which page a piece of text came from can use
    :func:`page_of`.
    """
    if _PDFTOTEXT is None:
        raise PdfTextError(
            "poppler's pdftotext was not found on PATH. Install poppler-utils "
            "(it's what provides pdftotext/pdfinfo) — this project relies on "
            "it for PDF text extraction, see studyrag-decisions-log.md."
        )
    cmd = [_PDFTOTEXT, "-raw", "-enc", "UTF-8"]
    if first_page is not None:
        cmd += ["-f", str(first_page)]
    if last_page is not None:
        cmd += ["-l", str(last_page)]
    cmd += [pdf_path, "-"]

    result = subprocess.run(cmd, capture_output=True, text=True, encoding="utf-8")
    if result.returncode != 0:
        raise PdfTextError(f"pdftotext failed on {pdf_path!r}: {result.stderr.strip()}")
    return result.stdout


def page_count(pdf_path: str) -> int:
    """Number of pages in the PDF, via poppler's pdfinfo."""
    if _PDFINFO is None:
        raise PdfTextError("poppler's pdfinfo was not found on PATH.")
    result = subprocess.run([_PDFINFO, pdf_path], capture_output=True, text=True, encoding="utf-8")
    if result.returncode != 0:
        raise PdfTextError(f"pdfinfo failed on {pdf_path!r}: {result.stderr.strip()}")
    for line in result.stdout.splitlines():
        if line.startswith("Pages:"):
            return int(line.split(":", 1)[1].strip())
    raise PdfTextError(f"Could not find a page count in pdfinfo output for {pdf_path!r}")


def page_of(text: str, offset: int) -> int:
    """1-indexed page number containing character ``offset`` of ``text``.

    ``text`` must still contain the original form-feed page separators (i.e.
    be extracted without slicing them out first).
    """
    return text.count(PAGE_BREAK, 0, offset) + 1
