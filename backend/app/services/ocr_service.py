"""
Text extraction / OCR service.

Strategy per page:
  1. Try native text extraction (pypdf) — fast, exact, no OCR errors.
  2. If a page has no (or negligible) extractable text, treat it as a
     scanned page: rasterise with pdftoppm and run OCR (PaddleOCR by
     default, or OCR.Space if configured) on the image.
  3. JPG/PNG uploads always go straight through OCR.

Returns a list of per-page text blocks so extraction/evidence can cite
a page number, plus a flag indicating whether OCR was actually invoked
(surfaced in `processing_metadata.ocr_used`).
"""
import io
import subprocess
import tempfile
from dataclasses import dataclass, field
from pathlib import Path

import numpy as np
from PIL import Image
from pypdf import PdfReader

from app.core.config import get_settings
from app.core.logging import get_logger
from app.utils.exceptions import OCRFailedError

logger = get_logger(__name__)

_MIN_NATIVE_TEXT_CHARS = 20  # below this, treat the page as "scanned"

# Lazy singleton for PaddleOCR engine — initialised on first use so startup
# is fast and we only pay the model-loading cost when OCR is actually needed.
_paddle_engine = None


def _get_paddle_engine():
    """Return a cached PaddleOCR instance (initialised on first call)."""
    global _paddle_engine
    if _paddle_engine is None:
        try:
            from paddleocr import PaddleOCR
            init_options = [
                {"lang": "en"},
                {"use_angle_cls": True, "lang": "en"},
                {},
            ]
            last_exc = None
            for kwargs in init_options:
                try:
                    _paddle_engine = PaddleOCR(**kwargs)
                    logger.info("PaddleOCR engine initialised successfully with %s", kwargs)
                    break
                except Exception as exc:  # noqa: BLE001
                    last_exc = exc
                    logger.debug("PaddleOCR init attempt with %s failed: %s", kwargs, exc)
            if _paddle_engine is None:
                raise OCRFailedError(f"Failed to initialise PaddleOCR engine: {last_exc}")
        except Exception as exc:  # noqa: BLE001
            if not isinstance(exc, OCRFailedError):
                raise OCRFailedError(f"Failed to initialise PaddleOCR engine: {exc}") from exc
            raise
    return _paddle_engine


@dataclass
class OCRResult:
    pages: list[str] = field(default_factory=list)  # text per page, 1-indexed via enumerate
    ocr_used: bool = False
    ocr_provider: str | None = None

    @property
    def full_text(self) -> str:
        return "\n".join(
            f"--- Page {i + 1} ---\n{text}" for i, text in enumerate(self.pages)
        )


def extract_text(filename: str, content: bytes, content_type: str) -> OCRResult:
    settings = get_settings()
    try:
        if content_type == "application/pdf":
            return _extract_from_pdf(content, settings)
        else:
            return _extract_from_image(content, settings)
    except OCRFailedError:
        raise
    except Exception as exc:  # noqa: BLE001
        logger.exception("OCR/text extraction failed for %s", filename)
        raise OCRFailedError(f"Failed to extract text from document: {exc}") from exc


def force_ocr_pdf(content: bytes) -> OCRResult:
    """Force rasterisation and OCR on every page of a PDF, bypassing native text layer."""
    settings = get_settings()
    images = _render_pdf_pages(content)
    pages_text = [_ocr_image(img, settings) for img in images]
    return OCRResult(pages=pages_text, ocr_used=True, ocr_provider=settings.OCR_PROVIDER)


def _extract_from_pdf(content: bytes, settings) -> OCRResult:
    reader = PdfReader(io.BytesIO(content))
    pages_text: list[str] = []
    ocr_used = False

    # First pass: native text layer per page.
    for page in reader.pages:
        try:
            text = page.extract_text() or ""
        except Exception:  # noqa: BLE001
            text = ""
        pages_text.append(text)

    # Second pass: OCR any page with negligible native text.
    needs_ocr_idx = [i for i, t in enumerate(pages_text) if len(t.strip()) < _MIN_NATIVE_TEXT_CHARS]
    if needs_ocr_idx:
        images = _render_pdf_pages(content)
        for idx in needs_ocr_idx:
            if idx < len(images):
                ocr_text = _ocr_image(images[idx], settings)
                pages_text[idx] = ocr_text
                ocr_used = True

    return OCRResult(pages=pages_text, ocr_used=ocr_used,
                      ocr_provider=settings.OCR_PROVIDER if ocr_used else None)


def _render_pdf_pages(content: bytes) -> list[Image.Image]:
    """Rasterise every PDF page to a PIL image using PyMuPDF (or pdftoppm fallback)."""
    try:
        try:
            import fitz
            doc = fitz.open(stream=content, filetype="pdf")
        except ImportError:
            import pymupdf
            doc = pymupdf.open(stream=content, filetype="pdf")
        images: list[Image.Image] = []
        for page in doc:
            pix = page.get_pixmap(dpi=200)
            img = Image.frombytes("RGB", [pix.width, pix.height], pix.samples)
            images.append(img)
        if images:
            return images
    except Exception as exc:
        logger.debug("PyMuPDF rasterisation failed, trying pdftoppm: %s", exc)

    with tempfile.TemporaryDirectory() as tmp:
        pdf_path = Path(tmp) / "doc.pdf"
        pdf_path.write_bytes(content)
        out_prefix = Path(tmp) / "page"
        try:
            subprocess.run(
                ["pdftoppm", "-jpeg", "-r", "200", str(pdf_path), str(out_prefix)],
                check=True, capture_output=True, timeout=60,
            )
        except (subprocess.CalledProcessError, subprocess.TimeoutExpired, FileNotFoundError) as exc:
            raise OCRFailedError(f"Could not rasterise PDF for OCR: {exc}") from exc

        image_files = sorted(Path(tmp).glob("page-*.jpg"))
        return [Image.open(f).copy() for f in image_files]


def _extract_from_image(content: bytes, settings) -> OCRResult:
    image = Image.open(io.BytesIO(content))
    text = _ocr_image(image, settings)
    return OCRResult(pages=[text], ocr_used=True, ocr_provider=settings.OCR_PROVIDER)


def _ocr_image(image: Image.Image, settings) -> str:
    """Run OCR on a PIL Image and return the extracted text string."""
    if settings.OCR_PROVIDER == "ocr_space" and settings.OCR_SPACE_API_KEY:
        try:
            return _ocr_via_ocr_space(image, settings)
        except Exception:  # noqa: BLE001
            logger.warning("OCR.Space failed, falling back to PaddleOCR")

    # --- PaddleOCR (primary local engine) ---
    try:
        return _ocr_via_paddle(image)
    except Exception as exc:  # noqa: BLE001
        logger.warning("PaddleOCR failed (%s), trying RapidOCR fallback", exc)
        try:
            return _ocr_via_rapidocr(image)
        except Exception as fallback_exc:  # noqa: BLE001
            raise OCRFailedError(
                f"OCR failed (PaddleOCR & RapidOCR): {exc} | {fallback_exc}"
            ) from exc


def _ocr_via_paddle(image: Image.Image) -> str:
    """Run PaddleOCR on a PIL image and return joined text."""
    engine = _get_paddle_engine()
    img_array = np.array(image.convert("RGB"))
    try:
        result = engine.ocr(img_array)
    except Exception as exc:  # noqa: BLE001
        raise OCRFailedError(f"PaddleOCR execution failed: {exc}") from exc
    if not result or result == [None]:
        return ""
    return _format_paddle_result(result)


def _format_paddle_result(result: list, line_threshold: float = 15.0) -> str:
    """
    Flatten PaddleOCR result structure into a plain-text string.

    PaddleOCR returns: list[list[tuple[bbox, (text, confidence)]]]
    We sort by Y-coordinate so reading order is preserved, then group
    words on the same horizontal line before joining.
    """
    items = []
    for page_res in result:
        if not page_res:
            continue
        for line in page_res:
            # line = [[[x0,y0],[x1,y1],[x2,y2],[x3,y3]], (text, score)]
            bbox, (text, _score) = line
            ys = [p[1] for p in bbox]
            xs = [p[0] for p in bbox]
            items.append((min(ys), min(xs), text))

    items.sort(key=lambda item: item[0])

    lines: list[str] = []
    current_line: list[tuple[float, str]] = []
    current_y: float | None = None

    for y, x, text in items:
        if current_y is None or abs(y - current_y) <= line_threshold:
            current_line.append((x, text))
            current_y = y if current_y is None else (
                (current_y * (len(current_line) - 1) + y) / len(current_line)
            )
        else:
            current_line.sort(key=lambda item: item[0])
            lines.append(" ".join(item[1] for item in current_line))
            current_line = [(x, text)]
            current_y = y

    if current_line:
        current_line.sort(key=lambda item: item[0])
        lines.append(" ".join(item[1] for item in current_line))

    return "\n".join(lines)


def _ocr_via_rapidocr(image: Image.Image) -> str:
    """Fallback OCR using RapidOCR (onnxruntime-based)."""
    from rapidocr_onnxruntime import RapidOCR

    ocr_engine = RapidOCR()
    res, _ = ocr_engine(np.array(image.convert("RGB")))
    if res:
        return _format_rapidocr_result(res)
    return ""


def _format_rapidocr_result(res: list, line_threshold: float = 15.0) -> str:
    """Group RapidOCR bounding boxes into horizontal lines (sorted by Y then X)."""
    items = []
    for box, text, _score in res:
        ys = [p[1] for p in box]
        xs = [p[0] for p in box]
        items.append((min(ys), min(xs), text))
    items.sort(key=lambda item: item[0])

    lines: list[str] = []
    current_line: list[tuple[float, str]] = []
    current_y: float | None = None

    for y, x, text in items:
        if current_y is None or abs(y - current_y) <= line_threshold:
            current_line.append((x, text))
            if current_y is None:
                current_y = y
            else:
                current_y = (current_y * (len(current_line) - 1) + y) / len(current_line)
        else:
            current_line.sort(key=lambda item: item[0])
            lines.append(" ".join(item[1] for item in current_line))
            current_line = [(x, text)]
            current_y = y

    if current_line:
        current_line.sort(key=lambda item: item[0])
        lines.append(" ".join(item[1] for item in current_line))

    return "\n".join(lines)


def _ocr_via_ocr_space(image: Image.Image, settings) -> str:
    import requests  # local import: optional dependency, only needed for this path

    buf = io.BytesIO()
    image.save(buf, format="JPEG")
    buf.seek(0)
    response = requests.post(
        "https://api.ocr.space/parse/image",
        files={"file": ("page.jpg", buf, "image/jpeg")},
        data={"apikey": settings.OCR_SPACE_API_KEY, "OCREngine": 2},
        timeout=30,
    )
    response.raise_for_status()
    payload = response.json()
    if payload.get("IsErroredOnProcessing"):
        raise RuntimeError(payload.get("ErrorMessage"))
    return "\n".join(r["ParsedText"] for r in payload.get("ParsedResults", []))
