"""Rasterize the first page of the CV PDF into a small PNG thumbnail."""
import io

import pypdfium2 as pdfium
from PIL import Image

# ~2x the on-screen display width: crisp on retina, light to ship.
PREVIEW_WIDTH = 720


def pdf_first_page_png(pdf_bytes: bytes) -> bytes:
    """Render page 1 of `pdf_bytes` at ~144 dpi and downscale to PREVIEW_WIDTH px."""
    pdf = pdfium.PdfDocument(pdf_bytes)
    try:
        image = pdf[0].render(scale=2).to_pil()
    finally:
        pdf.close()
    height = round(image.height * PREVIEW_WIDTH / image.width)
    image = image.resize((PREVIEW_WIDTH, height), Image.Resampling.LANCZOS)
    buffer = io.BytesIO()
    image.save(buffer, format="PNG", optimize=True)
    return buffer.getvalue()
