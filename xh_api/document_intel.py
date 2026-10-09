"""document_intel — turn a document a machine cannot read into text a machine can use.

One call, five input kinds: PDF (native text, with OCR fallback for scans), images (OCR), DOCX, HTML and
plain text. It reports what it actually did per page — native extraction or OCR — plus the digest of the
bytes it read, so a buyer can verify the document it paid to parse.

Runs entirely on this server: pymupdf for PDFs, tesseract for OCR. No third-party document API is called,
so there is no per-page cost and no copy of the customer's file leaving the machine.
"""

import base64
import hashlib
import io
import json
import os
import re
import time
import urllib.parse
import urllib.request
from dataclasses import dataclass
from typing import Any, Callable

MAX_BYTES = 30 * 1024 * 1024
MAX_CHARS = 60_000
OCR_DPI = 200
OCR_LANGS = os.environ.get("XH_OCR_LANGS", "eng")


@dataclass
class Ctx:
    check_ssrf: Callable[[str], str | None]


def _sniff(data: bytes, content_type: str, filename: str) -> str:
    if data[:5] == b"%PDF-":
        return "pdf"
    if data[:8] == b"\x89PNG\r\n\x1a\n":
        return "png"
    if data[:3] == b"\xff\xd8\xff":
        return "jpeg"
    if data[:4] == b"PK\x03\x04":
        if b"word/" in data[:4000] or (filename or "").endswith(".docx"):
            return "docx"
        return "zip"
    if data[:4] == b"RIFF" and data[8:12] == b"WEBP":
        return "webp"
    ct = (content_type or "").lower()
    if "pdf" in ct:
        return "pdf"
    if ct.startswith("image/"):
        return "image"
    if "html" in ct:
        return "html"
    if filename and filename.lower().endswith((".html", ".htm")):
        return "html"
    if filename and filename.lower().endswith(".docx"):
        return "docx"
    if ct.startswith("text/") or (data[:1] and all(b < 128 for b in data[:512])):
        return "text"
    return "unknown"


def _ocr_image(data: bytes) -> str:
    from PIL import Image
    import pytesseract
    with Image.open(io.BytesIO(data)) as im:
        if im.mode not in ("L", "RGB"):
            im = im.convert("RGB")
        return pytesseract.image_to_string(im, lang=OCR_LANGS)


def _pdf(data: bytes, ocr: bool) -> dict:
    import pymupdf
    out = {"pages": [], "native_chars": 0, "ocr_pages": 0, "rendered_pages": 0, "ocr_skipped": False}
    doc = pymupdf.open(stream=data, filetype="pdf")
    meta = doc.metadata or {}
    out["pdf_metadata"] = {k: v for k, v in meta.items() if v}
    for i, page in enumerate(doc):
        text = page.get_text("text") or ""
        method = "native"
        if len(text.strip()) < 40 and ocr:
            try:
                pix = page.get_pixmap(dpi=OCR_DPI)
                out["rendered_pages"] += 1
                img = pix.tobytes("png")
                ocr_text = _ocr_image(img)
                if len(ocr_text.strip()) > len(text.strip()):
                    text = ocr_text
                    method = "ocr"
                    out["ocr_pages"] += 1
            except Exception as e:
                out.setdefault("ocr_errors", []).append(f"page {i + 1}: {type(e).__name__}")
        elif len(text.strip()) < 40 and not ocr:
            out["ocr_skipped"] = True
        out["pages"].append({"n": i + 1, "method": method, "chars": len(text), "text": text})
        if method == "native":
            out["native_chars"] += len(text)
        if sum(p["chars"] for p in out["pages"]) > MAX_CHARS:
            out["truncated"] = True
            break
    out["page_count"] = doc.page_count
    doc.close()
    return out


def _docx(data: bytes) -> str:
    import zipfile
    out = []
    with zipfile.ZipFile(io.BytesIO(data)) as z:
        for name in ("word/document.xml",):
            if name in z.namelist():
                xml = z.read(name).decode("utf-8", "replace")
                xml = re.sub(r"</w:p>", "\n", xml)
                xml = re.sub(r"<[^>]+>", "", xml)
                out.append(xml)
    return "\n".join(out)


def _html(text: str) -> str:
    text = re.sub(r"(?is)<(script|style|noscript)[^>]*>.*?</\1>", " ", text)
    text = re.sub(r"(?is)<br\s*/?>|</p>|</div>|</li>|</h[1-6]>", "\n", text)
    text = re.sub(r"<[^>]+>", " ", text)
    text = re.sub(r"&nbsp;", " ", text)
    text = re.sub(r"&amp;", "&", text)
    text = re.sub(r"[ \t]{2,}", " ", text)
    return re.sub(r"\n{3,}", "\n\n", text)


def extract(ctx: Ctx, url: str | None = None, b64: str | None = None, filename: str | None = None,
            ocr: bool = True, max_chars: int = MAX_CHARS) -> dict:
    started = time.time()
    data: bytes | None = None
    content_type = ""
    source = None
    fetch_meta: dict[str, Any] = {}

    if url:
        bad = ctx.check_ssrf(url)
        if bad:
            return {"error": f"refused: {bad}", "url": url}
        try:
            req = urllib.request.Request(url, headers={
                "User-Agent": "xh-agents-documents/1.0", "Accept": "*/*"})
            with urllib.request.urlopen(req, timeout=60) as r:
                content_type = r.headers.get("content-type", "")
                data = r.read(MAX_BYTES + 1)
                fetch_meta = {"status": r.status, "content_type": content_type,
                              "content_length": r.headers.get("content-length")}
        except Exception as e:
            return {"error": f"fetch failed: {type(e).__name__}: {str(e)[:160]}", "url": url}
        source = "url"
        if len(data) > MAX_BYTES:
            return {"error": f"document larger than the {MAX_BYTES // (1024 * 1024)} MB limit", "url": url}
    elif b64:
        try:
            raw = b64.split(",", 1)[1] if b64.startswith("data:") and "," in b64 else b64
            data = base64.b64decode(raw + "=" * (-len(raw) % 4))
        except Exception as e:
            return {"error": f"base64 decode failed: {type(e).__name__}"}
        source = "base64"
    else:
        return {"error": "provide either url or base64"}

    if data is None:  # defensive: every branch above either sets bytes or returns
        return {"error": "no document bytes were obtained"}
    kind = _sniff(data, content_type, filename or (urllib.parse.urlparse(url or "").path if url else ""))
    result: dict[str, Any] = {
        "source": source, "bytes": len(data), "kind": kind,
        "sha256": hashlib.sha256(data).hexdigest(),
        "ocr_enabled": ocr, "fetch": fetch_meta,
    }
    text = ""
    pages: list[dict] = []
    try:
        if kind == "pdf":
            pdf = _pdf(data, ocr)
            pages = [{"n": p["n"], "method": p["method"], "chars": p["chars"]} for p in pdf["pages"]]
            text = "\n\n".join(p["text"] for p in pdf["pages"])
            result.update({"page_count": pdf.get("page_count"), "pages": pages,
                           "ocr_pages": pdf.get("ocr_pages", 0),
                           "native_pages": len([p for p in pdf["pages"] if p["method"] == "native"]),
                           "pdf_metadata": pdf.get("pdf_metadata"),
                           "truncated": bool(pdf.get("truncated")),
                           "ocr_skipped_for_empty_pages": bool(pdf.get("ocr_skipped"))})
            if pdf.get("ocr_errors"):
                result["ocr_errors"] = pdf["ocr_errors"][:5]
        elif kind in ("png", "jpeg", "webp", "image"):
            text = _ocr_image(data) if ocr else ""
            result.update({"pages": [{"n": 1, "method": "ocr" if ocr else "none", "chars": len(text)}],
                           "ocr_pages": 1 if ocr else 0})
            if not ocr:
                result["note"] = "ocr disabled by the caller: an image with no OCR returns no text"
        elif kind == "docx":
            text = _docx(data)
            result["pages"] = [{"n": 1, "method": "native", "chars": len(text)}]
        elif kind == "html":
            text = _html(data.decode("utf-8", "replace"))
            result["pages"] = [{"n": 1, "method": "native", "chars": len(text)}]
        elif kind == "zip":
            result["error"] = "zip archives are not unpacked; send a PDF, DOCX or image"
            return result
        else:
            text = data.decode("utf-8", "replace")
            result["pages"] = [{"n": 1, "method": "native", "chars": len(text)}]
    except Exception as e:
        result["error"] = f"{type(e).__name__}: {str(e)[:200]}"
        return result

    text = text.strip()
    if len(text) > max_chars:
        text = text[:max_chars]
        result["truncated_to_chars"] = max_chars
    result.update({
        "text": text, "text_chars": len(text),
        "words": len(text.split()),
        "language_hint": "ocr:" + OCR_LANGS if result.get("ocr_pages") else "native",
        "elapsed_ms": round((time.time() - started) * 1000),
        "methodology": {
            "pdf": "pymupdf native text per page; pages with under 40 characters are re-rendered at "
                   f"{OCR_DPI} dpi and read with tesseract ({OCR_LANGS})",
            "images": f"tesseract OCR, {OCR_LANGS}",
            "docx": "word/document.xml unpacked from the archive with the standard library",
            "html": "tags and scripts stripped, block elements turned into line breaks",
            "integrity": "sha256 of the exact bytes read, so the buyer can verify the source",
        },
        "not_checked": [
            "table structure (cells are flattened into text, not returned as a grid)",
            "charts and diagrams (images are described as nothing — only machine-readable text is returned)",
            "handwriting and low-resolution scans: OCR quality depends on the source image",
            f"languages other than {OCR_LANGS}",
        ],
    })
    return result


def register(app, ctx: Ctx) -> None:
    from pydantic import BaseModel, Field

    class DocReq(BaseModel):
        url: str | None = Field(None, description="Public URL of the document")
        base64: str | None = Field(None, description="The document itself, base64 (data: prefix allowed)")
        filename: str | None = Field(None, description="Optional filename hint (.pdf, .docx, .png…)")
        ocr: bool = Field(True, description="Allow OCR for scans and images")
        max_chars: int = Field(60000, ge=500, le=200000)

    @app.get("/document-extract/method")
    def index():
        return {
            "provider": "XH Agents — document to text (PDF, scans, images, DOCX, HTML)",
            "what_it_is": ("Send a document URL or its base64 bytes; get back usable text, per-page method "
                           "(native or OCR), the digest of the bytes read, and an honest list of what was not "
                           "extracted. Runs on this server: no third-party document API, no per-page fee, and "
                           "the file is not stored."),
            "price_usdc_per_call": 0.05,
            "endpoints": [{"route": "POST /api/document-extract", "price_usd": 0.05},
                          {"route": "GET /api/document-extract?url=…", "price_usd": 0.05}],
            "supported": ["pdf (native + OCR fallback)", "png/jpeg/webp (OCR)", "docx", "html", "txt/csv/json"],
            "limits": {"max_bytes": MAX_BYTES, "max_chars_default": MAX_CHARS, "ocr_langs": OCR_LANGS},
            "not_checked": ["table structure", "charts", "handwriting", "non-English OCR"],
        }

    def _run(req: DocReq) -> dict:
        if not req.url and not req.base64:
            from fastapi import HTTPException
            raise HTTPException(status_code=400, detail="provide url or base64")
        return extract(ctx, req.url, req.base64, req.filename, req.ocr, req.max_chars)

    @app.post("/document-extract")
    def doc_post(req: DocReq):
        return _run(req)

    @app.get("/document-extract")
    def doc_get(url: str, ocr: bool = True, max_chars: int = 60000):
        return extract(ctx, url, None, None, ocr, max_chars)
