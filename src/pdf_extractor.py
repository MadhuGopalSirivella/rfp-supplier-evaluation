from dataclasses import dataclass

import pymupdf


@dataclass
class ExtractedPDF:
    pages: list[str]
    text: str


def extract_pdf(content: bytes) -> ExtractedPDF:
    with pymupdf.open(stream=content, filetype="pdf") as document:
        pages = [page.get_text("text").strip() for page in document]
    return ExtractedPDF(pages=pages, text="\n\n".join(pages).strip())