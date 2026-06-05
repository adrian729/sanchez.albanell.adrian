import mimetypes
from pathlib import Path

from fastapi import FastAPI, Request, Response
from fastapi.responses import HTMLResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from weasyprint import CSS, HTML, default_url_fetcher

from app import PDF_FILENAME

app = FastAPI()

app.mount("/static", StaticFiles(directory="static"), name="static")

templates = Jinja2Templates(directory="templates")

STATIC_DIR = Path("static").resolve()


def _static_url_fetcher(url: str, timeout: int = 10, ssl_context=None):
    # WeasyPrint resolves absolute paths like /static/photo.jpg against
    # `file://`, so the default fetcher looks for /static/photo.jpg at the
    # filesystem root and fails. Reroute any /static/<rel> reference back to
    # the on-disk static directory.
    marker = "/static/"
    idx = url.find(marker)
    if idx != -1:
        rel = url[idx + len(marker):]
        path = (STATIC_DIR / rel).resolve()
        if path.is_file() and STATIC_DIR in path.parents:
            mime, _ = mimetypes.guess_type(path)
            return {"file_obj": path.open("rb"), "mime_type": mime}
    return default_url_fetcher(url, timeout=timeout, ssl_context=ssl_context)


@app.get("/", response_class=HTMLResponse)
def view_index(request: Request):
    return templates.TemplateResponse(
        "index.html", {"request": request, "pdf_filename": PDF_FILENAME}
    )


@app.get("/cv.pdf")
def cv_pdf(request: Request):
    html_string = templates.get_template("cv_pdf.html").render(
        {"request": request, "pdf_filename": PDF_FILENAME}
    )

    pdf_bytes = HTML(
        string=html_string,
        base_url=str(request.base_url),
        url_fetcher=_static_url_fetcher,
    ).write_pdf(stylesheets=[CSS("static/cv.css")])

    headers = {
        "Content-Disposition": f'attachment; filename="{PDF_FILENAME}"',
    }
    return Response(content=pdf_bytes, media_type="application/pdf", headers=headers)


@app.get("/health")
async def health_check():
    return {"status": "healthy"}
