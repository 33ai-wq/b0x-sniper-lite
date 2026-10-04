#!/usr/bin/env python3
"""Uji jalur OCR: bikin gambar berisi teks, lalu minta document_intel membacanya."""
import base64
import io
import sys

sys.path.insert(0, "/home/ubuntu/prpo_ai/xh_api")
import document_intel  # noqa: E402
import server  # noqa: E402

from PIL import Image, ImageDraw, ImageFont  # noqa: E402

TEXT = "XH AGENTS OCR TEST 2026\ninvoice 0.05 USDC\nBase mainnet"
img = Image.new("RGB", (760, 220), "white")
d = ImageDraw.Draw(img)
try:
    font = ImageFont.truetype("/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf", 30)
except Exception:
    font = ImageFont.load_default()
d.text((24, 30), TEXT, fill="black", font=font)
buf = io.BytesIO()
img.save(buf, format="PNG")
raw = buf.getvalue()
b64 = base64.b64encode(raw).decode()
print(f"gambar uji: {len(raw)} byte")

r = document_intel.extract(document_intel.Ctx(check_ssrf=server._check_ssrf), None, b64, "ocr-test.png", True)
print("kind:", r.get("kind"), "| ocr_pages:", r.get("ocr_pages"), "| chars:", r.get("text_chars"))
print("teks terbaca:")
print(r.get("text", "")[:300])
print("cocok?" , "OCR TEST" in (r.get("text") or "").upper(), "| invoice terbaca?", "0.05" in (r.get("text") or ""))

# jalur PDF hasil scan: render gambar ke PDF (tanpa lapisan teks) lalu minta ekstraksi
pdf = Image.open(io.BytesIO(raw)).convert("RGB")
p2 = io.BytesIO()
pdf.save(p2, format="PDF", resolution=150)
r2 = document_intel.extract(document_intel.Ctx(check_ssrf=server._check_ssrf), None,
                            base64.b64encode(p2.getvalue()).decode(), "scan.pdf", True)
print("\nPDF scan -> pages:", r2.get("page_count"), "| ocr_pages:", r2.get("ocr_pages"),
      "| chars:", r2.get("text_chars"))
print("teks:", repr((r2.get("text") or "")[:160]))
