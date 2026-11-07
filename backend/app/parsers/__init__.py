"""Statement parsers. Add a bank: implement ``looks_like(header)`` and ``parse_pdf(fp)``."""

from typing import BinaryIO

from app.parsers import vtb
from app.parsers.base import ParsedStatement, StatementError

PARSERS = {"vtb": vtb}


def detect_and_parse(fp: str | BinaryIO) -> ParsedStatement:
    import pdfplumber

    with pdfplumber.open(fp) as pdf:
        header = pdf.pages[0].extract_text() or ""
    if hasattr(fp, "seek"):
        fp.seek(0)
    for mod in PARSERS.values():
        if mod.looks_like(header):
            return mod.parse_pdf(fp)
    raise StatementError("unknown statement format (supported: " + ", ".join(PARSERS) + ")")
