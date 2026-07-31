"""
digital_extractor.py - Text extraction for digital (text-layer) PDFs.

Flow per PDF:
  1. Open with pdfplumber (primary) or PyMuPDF (fallback).
  2. For each of the first `max_pages` pages:
       a. Detect rotation using text-block geometry (height > width -> vertical).
       b. If rotated, apply correction in-memory before reading text.
       c. Extract text from the (corrected) page.
  3. Return combined text + a rotation summary.

This module is only for PDFs that have a real text layer.
For image-only (scanned) PDFs use scanned_extractor.py instead.
"""

from __future__ import annotations

import logging
from pathlib import Path

import re

logger = logging.getLogger(__name__)

# Minimum number of text characters on a page to consider it "digital"
DIGITAL_TEXT_MIN_CHARS = 30

# If more than this fraction of chars are inside (cid:N) sequences, treat as garbage
_CID_GARBAGE_THRESHOLD = 0.20

# Minimum meaningful chars per page - below this, the text layer is too sparse
# (e.g. only barcodes/page-numbers with all actual content in images)
_MIN_CHARS_PER_PAGE = 150


# ── CID garbage detection ─────────────────────────────────────────────────────

def _is_cid_garbage(text: str) -> bool:
    """
    Return True if the extracted text is predominantly unreadable garbage.

    Two patterns are detected:

    1. ``(cid:N)`` sequences - pdfplumber's representation of CID-encoded chars
       when the PDF font has no ToUnicode map.
    2. Non-printable Unicode control characters - PyMuPDF decodes the same
       broken fonts as raw codepoints (Unicode category 'Cc'/'Cs') instead of
       the ``(cid:N)`` text form.

    If either pattern accounts for more than _CID_GARBAGE_THRESHOLD of the
    non-whitespace content the text is considered unreadable and OCR should
    be used instead.
    """
    if not text:
        return False

    try:
        import unicodedata
    except ImportError:
        # If unicodedata is not available, just check for CID patterns
        cid_token_chars = sum(len(m.group()) for m in re.finditer(r'\(cid:\d+\)', text))
        total_nonspace = len(text.replace(" ", "").replace("\n", "").replace("\t", ""))
        if total_nonspace == 0:
            return False
        ratio = cid_token_chars / total_nonspace
        logger.debug(
            "[cid-check] Garbage ratio: %.1f%% (cid_tokens=%d / total=%d)",
            ratio * 100, cid_token_chars, total_nonspace,
        )
        return ratio > _CID_GARBAGE_THRESHOLD

    # Pattern 1: literal (cid:N) tokens (pdfplumber output)
    cid_token_chars = sum(len(m.group()) for m in re.finditer(r'\(cid:\d+\)', text))

    # Pattern 2: non-printable control characters (PyMuPDF output)
    control_chars = sum(
        1 for c in text
        if unicodedata.category(c) in ('Cc', 'Cs', 'Co')  # control / surrogate / private-use
        and c not in ('\n', '\r', '\t')                    # keep normal whitespace
    )

    total_nonspace = len(text.replace(" ", "").replace("\n", "").replace("\t", ""))
    if total_nonspace == 0:
        return False

    garbage_chars = cid_token_chars + control_chars
    ratio = garbage_chars / total_nonspace
    logger.debug(
        "[cid-check] Garbage ratio: %.1f%% (cid_tokens=%d, control=%d / total=%d)",
        ratio * 100, cid_token_chars, control_chars, total_nonspace,
    )
    return ratio > _CID_GARBAGE_THRESHOLD


# ── Sparse text detection ───────────────────────────────────────────────────

def _is_too_sparse(text: str, pages_read: int) -> bool:
    """
    Return True when the digital text layer contains too little content to be
    useful, even though it technically has some text (e.g. only barcodes,
    page numbers, or reference IDs).

    PDFs like ACORD insurance forms are sometimes saved with a thin text layer
    (barcodes, dates) while the actual form fields are image-based.  The text
    passes the CID check but is far too short to classify correctly.

    Threshold: fewer than _MIN_CHARS_PER_PAGE printable characters per page.
    """
    if pages_read <= 0:
        return False
    printable = sum(1 for c in text if c.isprintable() and c not in (' ', '\t'))
    chars_per_page = printable / pages_read
    logger.debug(
        "[sparse-check] %.0f printable chars/page (%d chars, %d pages)",
        chars_per_page, printable, pages_read,
    )
    return chars_per_page < _MIN_CHARS_PER_PAGE


# ── Rotation detection (text-block geometry) ──────────────────────────────────

def _detect_rotation_fitz(page) -> int:
    """
    Detect whether a PyMuPDF page needs rotation by analysing text-block shapes.

    If more text blocks are taller than wide the content is likely rotated 90 deg.

    Returns:
        90 if rotation is likely needed, 0 otherwise.
    """
    blocks = page.get_text("blocks")  # list of (x0,y0,x1,y1,text,...)
    vertical = 0
    horizontal = 0

    for block in blocks:
        x0, y0, x1, y1 = block[:4]
        width  = abs(x1 - x0)
        height = abs(y1 - y0)
        if height > width:
            vertical += 1
        else:
            horizontal += 1

    if vertical > horizontal and (vertical + horizontal) > 0:
        logger.debug("Rotation detected: vertical=%d horizontal=%d -> 90 deg", vertical, horizontal)
        return 90
    return 0


# ── pdfplumber extraction (primary) ───────────────────────────────────────────

def _format_page_to_markdown_table(page) -> str:
    """Format a digital PDF page into a coordinate-aligned Markdown table."""
    words = page.extract_words()
    if not words:
        return ""

    # Filter out page header metadata/titles (top < 40)
    words = [w for w in words if w["top"] >= 40]
    if not words:
        return ""

    # Sort words by top position, then by x0
    words.sort(key=lambda w: (w["top"], w["x0"]))

    # Group words into lines vertically using a tolerance of 3 points
    lines = []
    current_line = []
    last_top = None
    for w in words:
        if last_top is None:
            current_line.append(w)
            last_top = w["top"]
        elif abs(w["top"] - last_top) <= 3:
            current_line.append(w)
        else:
            current_line.sort(key=lambda x: x["x0"])
            lines.append(current_line)
            current_line = [w]
            last_top = w["top"]
    if current_line:
        current_line.sort(key=lambda x: x["x0"])
        lines.append(current_line)

    # We map segment centers to 8 horizontal column locations:
    # Column centers: 217.6 + i * 76.85 for i = 0 to 7
    def get_col_idx(x0: float) -> int:
        if x0 < 150:
            return -1
        idx = round((x0 - 217.6) / 76.85)
        return max(0, min(7, idx))

    formatted_rows = []
    max_col_used = 0

    for line in lines:
        # Merge words horizontally on each line with gap < 5.0 points
        segments = []
        current_seg = []
        for w in line:
            if not current_seg:
                current_seg.append(w)
            else:
                gap = w["x0"] - current_seg[-1]["x1"]
                if gap < 5.0:
                    current_seg.append(w)
                else:
                    segments.append(current_seg)
                    current_seg = [w]
        if current_seg:
            segments.append(current_seg)

        label_parts = []
        col_vals = {i: [] for i in range(8)}

        for seg in segments:
            seg_text = " ".join(sw["text"] for sw in seg)
            x0 = seg[0]["x0"]
            col_idx = get_col_idx(x0)
            if col_idx == -1:
                label_parts.append(seg_text)
            else:
                col_vals[col_idx].append(seg_text)
                max_col_used = max(max_col_used, col_idx)

        label = " ".join(label_parts).strip()
        row_vals = [" ".join(col_vals[i]).strip() for i in range(8)]
        formatted_rows.append((label, row_vals))

    # 1. Separate formatted_rows into header and body rows
    header_rows = []
    body_rows = []
    found_deductible = False

    for label, vals in formatted_rows:
        if "deductible" in label.lower() and "out of network" not in label.lower():
            found_deductible = True
        if not found_deductible:
            header_rows.append((label, vals))
        else:
            body_rows.append((label, vals))

    # Determine total columns to output (pairs of Current/Proposed)
    num_cols = 8
    if max_col_used < 2:
        num_cols = 2
    elif max_col_used < 4:
        num_cols = 4
    elif max_col_used < 6:
        num_cols = 6

    # 2. Consolidate vertical header rows for each column
    consolidated_headers = {i: [] for i in range(num_cols)}
    for label, vals in header_rows:
        for i in range(num_cols):
            val = vals[i].strip()
            # Skip empty, N/A, and standard status/placeholder values
            if val and val != "N/A":
                val_lower = val.lower()
                is_metadata = any(phrase in val_lower for phrase in (
                    "plan and rate comparison",
                    "policy period",
                    "quoted rates",
                    "quote id",
                    "resourcing edge",
                    "prepared for"
                ))
                if val_lower not in ("current", "proposed") and not is_metadata:
                    # Avoid duplicates
                    if not consolidated_headers[i] or consolidated_headers[i][-1] != val:
                        consolidated_headers[i].append(val)

    # Build markdown table output
    markdown_lines = []
    headers = ["Label"] + [f"Col {i+1}" for i in range(num_cols)]
    markdown_lines.append(" | ".join(headers))
    markdown_lines.append("|" + "|".join("---" for _ in headers) + "|")

    # Add consolidated Carrier row
    carrier_vals = []
    for i in range(num_cols):
        segs = consolidated_headers[i]
        carrier = segs[0] if segs else "N/A"
        carrier_vals.append(carrier)
    markdown_lines.append("Carrier | " + " | ".join(carrier_vals))

    # Add consolidated Plan Name & Details row
    details_vals = []
    for i in range(num_cols):
        segs = consolidated_headers[i]
        details = " ".join(segs[1:]) if len(segs) > 1 else "N/A"
        details_vals.append(details)
    markdown_lines.append("Plan Name & Details | " + " | ".join(details_vals))

    # Add remaining body rows
    for label, vals in body_rows:
        sliced_vals = vals[:num_cols]
        if any(v for v in sliced_vals) or label:
            row_str = f"{label} | " + " | ".join(v if v else "N/A" for v in sliced_vals)
            markdown_lines.append(row_str)

    return "\n".join(markdown_lines)


def _extract_with_pdfplumber(file_path: Path, max_pages: int) -> tuple[str, str]:
    """
    Extract text from a digital PDF using pdfplumber, formatted as Markdown tables.

    Rotation is applied via PyMuPDF in-memory before pdfplumber reads each page.

    Returns:
        (combined_text, error_message)
    """
    try:
        import fitz        # type: ignore
        import pdfplumber  # type: ignore
    except ImportError as exc:
        return "", f"Missing dependency: {exc}"

    pages_text: list[str] = []
    rotation_log: list[str] = []

    fitz_doc = fitz.open(str(file_path))

    with pdfplumber.open(str(file_path)) as plumber_doc:
        limit = min(max_pages, len(plumber_doc.pages)) if max_pages else len(plumber_doc.pages)

        for i in range(limit):
            fitz_page   = fitz_doc[i]
            plumber_page = plumber_doc.pages[i]

            angle = _detect_rotation_fitz(fitz_page)

            if angle != 0:
                fitz_page.set_rotation(angle)
                rotation_log.append(f"page {i+1}: rotated {angle} deg")
                logger.info("[digital] %s page %d -> rotated %d deg", file_path.name, i + 1, angle)

                rotated_bytes = fitz_doc.tobytes()
                import io
                with pdfplumber.open(io.BytesIO(rotated_bytes)) as rotated_doc:
                    page_text = _format_page_to_markdown_table(rotated_doc.pages[i])
            else:
                page_text = _format_page_to_markdown_table(plumber_page)

            pages_text.append(f"=== Page {i+1} ===\n{page_text}")

    fitz_doc.close()

    rotation_summary = (", ".join(rotation_log)) if rotation_log else "no rotation needed"
    combined = "\n\n".join(pages_text)
    return combined, rotation_summary


# ── PyMuPDF extraction (fallback) ─────────────────────────────────────────────

def _extract_with_fitz(file_path: Path, max_pages: int) -> tuple[str, str]:
    """
    Fallback extractor using PyMuPDF get_text().
    Also applies in-memory rotation correction before extracting.

    Returns:
        (combined_text, error_message)
    """
    try:
        import fitz  # type: ignore
    except ImportError:
        return "", "PyMuPDF (fitz) not installed."

    pages_text: list[str] = []
    rotation_log: list[str] = []

    doc = fitz.open(str(file_path))
    limit = min(max_pages, len(doc)) if max_pages else len(doc)

    for i in range(limit):
        page  = doc[i]
        angle = _detect_rotation_fitz(page)

        if angle != 0:
            page.set_rotation(angle)
            rotation_log.append(f"page {i+1}: rotated {angle} deg")
            logger.info("[digital-fitz] %s page %d -> rotated %d deg", file_path.name, i + 1, angle)

        page_text = page.get_text()
        pages_text.append(page_text)

    doc.close()

    rotation_summary = (", ".join(rotation_log)) if rotation_log else "no rotation needed"
    return "\n".join(pages_text), rotation_summary


# ── Public API ────────────────────────────────────────────────────────────────

def is_digital(file_path: Path, sample_pages: int = 2) -> bool:
    """
    Return True if the PDF has a real text layer (digital PDF).

    Reads the first `sample_pages` pages with PyMuPDF.  If total extracted
    text exceeds DIGITAL_TEXT_MIN_CHARS the PDF is treated as digital.

    Args:
        file_path:    Path to the PDF.
        sample_pages: How many pages to sample.

    Returns:
        True = digital (has text), False = scanned (image-only).
    """
    try:
        import fitz  # type: ignore

        doc   = fitz.open(str(file_path))
        limit = min(sample_pages, len(doc))
        total_chars = sum(len(doc[i].get_text()) for i in range(limit))
        doc.close()
        result = total_chars >= DIGITAL_TEXT_MIN_CHARS
        logger.debug(
            "[type-detect] %s -> %s (%d chars in first %d page(s))",
            file_path.name,
            "DIGITAL" if result else "SCANNED",
            total_chars,
            limit,
        )
        return result
    except Exception as exc:
        logger.warning("Type detection failed for %s: %s - assuming scanned.", file_path.name, exc)
        return False


def extract(file_path: Path, max_pages: int = 3) -> tuple[str, str, str]:
    """
    Extract text from a digital PDF (first `max_pages` pages).

    Rotation is auto-detected and corrected per page before extraction.
    If the extracted text is CID-encoded garbage (broken font ToUnicode map),
    automatically falls back to rostaing-ocr for proper text recognition.

    Args:
        file_path:  Path to a digital PDF.
        max_pages:  Maximum pages to read (default 3).

    Returns:
        ``(text, rotation_info, error)``
        - text:          Combined extracted text.
        - rotation_info: Human-readable rotation log (e.g. "page 1: rotated 90 deg").
        - error:         Non-empty string if a non-fatal problem occurred.
    """
    logger.info("[digital] Extracting: %s (max %d pages)", file_path.name, max_pages)

    # Determine how many pages will actually be read (needed for sparse check)
    try:
        import fitz as _fitz  # type: ignore
        _doc = _fitz.open(str(file_path))
        pages_read = min(max_pages, len(_doc)) if max_pages else len(_doc)
        _doc.close()
    except Exception:
        pages_read = max_pages or 3  # safe fallback

    def _needs_ocr(text: str, source: str) -> bool:
        """Return True and log a warning if text is CID garbage or too sparse."""
        if _is_cid_garbage(text):
            logger.warning(
                "[digital] %s - CID-encoded text detected (%s); falling back to OCR.",
                file_path.name, source,
            )
            return True
        if _is_too_sparse(text, pages_read):
            logger.warning(
                "[digital] %s - text layer too sparse (%d chars / %d pages) (%s); falling back to OCR.",
                file_path.name, len(text.strip()), pages_read, source,
            )
            return True
        return False

    # Primary: pdfplumber
    try:
        text, rotation_info = _extract_with_pdfplumber(file_path, max_pages)
        if text.strip() and not _needs_ocr(text, "pdfplumber"):
            return text, rotation_info, ""
    except Exception as exc:
        logger.warning("[digital] pdfplumber failed: %s - trying PyMuPDF.", exc)

    # Fallback: PyMuPDF
    try:
        text, rotation_info = _extract_with_fitz(file_path, max_pages)
        if text.strip() and not _needs_ocr(text, "PyMuPDF"):
            return text, rotation_info, "pdfplumber failed; used PyMuPDF fallback"
    except Exception as exc:
        logger.error("[digital] Both extractors failed: %s", exc)

    # OCR fallback: rostaing-ocr with auto-rotation for CID-encoded / sparse digital PDFs
    logger.info(
        "[digital] %s - switching to rostaing-ocr with auto-rotation (CID/sparse fallback).", file_path.name
    )
    try:
        # Try to import OCR fallback modules
        try:
            from schema_ocr import SchemaOCRExtractor
            ocr_extractor = SchemaOCRExtractor(str(file_path))
            ocr_text = ocr_extractor.extract_layout_text(save_debug_output=False)
            if ocr_text.strip():
                return ocr_text, "OCR auto-rotation applied", "CID font detected; used rostaing-ocr"
        except ImportError:
            logger.warning("[digital] rostaing-ocr not available for CID fallback")
    except Exception as exc:
        logger.error("[digital] rostaing-ocr fallback also failed: %s", exc)

    return "", "unknown", "All extractors failed (including OCR fallback)."

