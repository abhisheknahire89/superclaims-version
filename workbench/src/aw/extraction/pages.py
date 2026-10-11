"""Page splitting, text-layer detection and page rendering for PDFs and images.

Native text (and word/line boxes) come from pdfplumber. Pages with no usable text layer are marked NONE and
need OCR (an OCR provider is configured per ADR-05 after the bake-off; none runs in the Phase 1 environment).
Page images for the evidence viewer are rendered with pypdfium2 at 110 dpi.
"""
from __future__ import annotations

import io
from dataclasses import dataclass, field

MIN_NATIVE_CHARS = 25


@dataclass
class PageText:
    page_no: int
    width: float
    height: float
    text: str
    lines: list[dict] = field(default_factory=list)   # {text, x0, top, x1, bottom}
    words: list[dict] = field(default_factory=list)   # {text, x0, top, x1, bottom}
    text_layer: str = "NATIVE"                         # NATIVE | NONE

    def to_json(self) -> dict:
        return {"page_no": self.page_no, "width": self.width, "height": self.height, "text": self.text,
                "lines": self.lines, "words": self.words, "text_layer": self.text_layer}

    @staticmethod
    def from_json(d: dict) -> "PageText":
        return PageText(d["page_no"], d["width"], d["height"], d["text"], d["lines"], d["words"], d["text_layer"])


def _r(v: float) -> float:
    return round(float(v), 1)


def read_pdf(data: bytes) -> list[PageText]:
    import pdfplumber

    out: list[PageText] = []
    with pdfplumber.open(io.BytesIO(data)) as pdf:
        for i, page in enumerate(pdf.pages, start=1):
            words = [{"text": w["text"], "x0": _r(w["x0"]), "top": _r(w["top"]), "x1": _r(w["x1"]), "bottom": _r(w["bottom"])}
                     for w in page.extract_words(keep_blank_chars=False, use_text_flow=False)]
            lines = [{"text": ln["text"], "x0": _r(ln["x0"]), "top": _r(ln["top"]), "x1": _r(ln["x1"]), "bottom": _r(ln["bottom"])}
                     for ln in page.extract_text_lines(return_chars=False)]
            text = "\n".join(ln["text"] for ln in lines)
            layer = "NATIVE" if len(text.replace(" ", "")) >= MIN_NATIVE_CHARS else "NONE"
            out.append(PageText(i, _r(page.width), _r(page.height), text, lines, words, layer))
    return out


def render_png(data: bytes, page_no: int, dpi: int = 110) -> bytes:
    import pypdfium2 as pdfium

    pdf = pdfium.PdfDocument(data)
    try:
        page = pdf[page_no - 1]
        image = page.render(scale=dpi / 72).to_pil()
        buf = io.BytesIO()
        image.save(buf, format="PNG", optimize=True)
        return buf.getvalue()
    finally:
        pdf.close()


def sniff_mime(data: bytes) -> str | None:
    if data[:5] == b"%PDF-":
        return "application/pdf"
    if data[:8] == b"\x89PNG\r\n\x1a\n":
        return "image/png"
    if data[:3] == b"\xff\xd8\xff":
        return "image/jpeg"
    if data[:4] in (b"II*\x00", b"MM\x00*"):
        return "image/tiff"
    return None
