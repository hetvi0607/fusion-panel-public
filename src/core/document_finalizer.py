"""
Turns a generated DOCX (invoice / AMC / offer letter) into a client-ready,
stamped PDF in one step.

Replaces the manual workflow of: open in Google Drive -> convert to PDF ->
download -> open in Preview -> add stamp & signature -> save.

Conversion is done locally with headless LibreOffice ('soffice'), and the
company stamp + signature images (configured in Settings) are overlaid near
the bottom-right corner of the PDF using PyMuPDF.
"""
import os
import shutil
import subprocess
import tempfile
import logging

import fitz  # PyMuPDF

logger = logging.getLogger(__name__)

_POINTS_PER_INCH = 72

_SOFFICE_CANDIDATES = [
    "soffice",
    "libreoffice",
    "/opt/homebrew/bin/soffice",
    "/Applications/LibreOffice.app/Contents/MacOS/soffice",
]


class FinalizeError(RuntimeError):
    """Raised when DOCX->PDF conversion or stamping fails."""


def _find_soffice():
    for candidate in _SOFFICE_CANDIDATES:
        if os.sep in candidate:
            if os.path.isfile(candidate):
                return candidate
            continue
        found = shutil.which(candidate)
        if found:
            return found
    raise FinalizeError(
        "LibreOffice ('soffice') was not found on this Mac. Install it with "
        "'brew install --cask libreoffice' to enable stamped PDF export."
    )


def convert_docx_to_pdf(docx_path: str, output_dir: str = None) -> str:
    """Convert a DOCX file to PDF using headless LibreOffice.

    Returns the absolute path to the produced PDF.
    """
    docx_path = os.path.abspath(docx_path)
    if not os.path.isfile(docx_path):
        raise FinalizeError(f"Document not found: {docx_path}")

    output_dir = os.path.abspath(output_dir or os.path.dirname(docx_path))
    os.makedirs(output_dir, exist_ok=True)
    soffice = _find_soffice()

    # A private profile dir avoids clashing with a real LibreOffice instance
    # that may already be running (and lets multiple conversions run safely).
    with tempfile.TemporaryDirectory(prefix="soffice-profile-") as profile_dir:
        cmd = [
            soffice,
            "--headless",
            "--norestore",
            f"-env:UserInstallation=file://{profile_dir}",
            "--convert-to", "pdf",
            "--outdir", output_dir,
            docx_path,
        ]
        try:
            result = subprocess.run(
                cmd, capture_output=True, text=True, timeout=120,
            )
        except subprocess.TimeoutExpired as exc:
            raise FinalizeError("LibreOffice conversion timed out.") from exc

        if result.returncode != 0:
            raise FinalizeError(
                "LibreOffice conversion failed: "
                f"{(result.stderr or result.stdout or '').strip()}"
            )

    base_name = os.path.splitext(os.path.basename(docx_path))[0]
    pdf_path = os.path.join(output_dir, f"{base_name}.pdf")
    if not os.path.isfile(pdf_path):
        raise FinalizeError("PDF conversion did not produce an output file.")
    return pdf_path


def _image_width_height(path: str, target_width_pt: float):
    """Return (width_pt, height_pt) for an image scaled to target_width_pt,
    preserving its aspect ratio."""
    pix = fitz.Pixmap(path)
    try:
        if not pix.width:
            return target_width_pt, target_width_pt
        ratio = pix.height / pix.width
    finally:
        pix = None
    return target_width_pt, target_width_pt * ratio


def stamp_pdf(pdf_path: str, output_path: str, branding: dict) -> str:
    """Overlay the configured stamp and signature images onto a PDF.

    branding keys used: stamp_path, signature_path, stamp_width_in,
    signature_width_in, margin_right_in, margin_bottom_in, gap_in,
    target_page ("first" or "last"). Missing/blank paths are skipped.
    If neither image is configured, the PDF is copied through unchanged.
    """
    stamp_path = branding.get("stamp_path") or ""
    signature_path = branding.get("signature_path") or ""
    has_stamp = bool(stamp_path) and os.path.isfile(stamp_path)
    has_signature = bool(signature_path) and os.path.isfile(signature_path)

    if not has_stamp and not has_signature:
        shutil.copyfile(pdf_path, output_path)
        return output_path

    doc = fitz.open(pdf_path)
    try:
        page_index = 0 if branding.get("target_page") == "first" else len(doc) - 1
        page = doc[page_index]

        margin_right = branding.get("margin_right_in", 0.6) * _POINTS_PER_INCH
        margin_bottom = branding.get("margin_bottom_in", 0.6) * _POINTS_PER_INCH
        gap = branding.get("gap_in", 0.1) * _POINTS_PER_INCH

        page_right = page.rect.width - margin_right
        page_bottom = page.rect.height - margin_bottom

        # Signature sits to the left, stamp sits closer to the corner —
        # both bottom-aligned, side by side near the bottom-right corner.
        stamp_w = stamp_h = 0.0
        if has_stamp:
            stamp_width_pt = branding.get("stamp_width_in", 1.3) * _POINTS_PER_INCH
            stamp_w, stamp_h = _image_width_height(stamp_path, stamp_width_pt)

        cursor_right = page_right
        if has_signature:
            signature_width_pt = (
                branding.get("signature_width_in", 1.6) * _POINTS_PER_INCH
            )
            sig_w, sig_h = _image_width_height(signature_path, signature_width_pt)
            if has_stamp:
                cursor_right = page_right - stamp_w - gap
            sig_rect = fitz.Rect(
                cursor_right - sig_w, page_bottom - sig_h,
                cursor_right, page_bottom,
            )
            page.insert_image(sig_rect, filename=signature_path, overlay=True)

        if has_stamp:
            stamp_rect = fitz.Rect(
                page_right - stamp_w, page_bottom - stamp_h,
                page_right, page_bottom,
            )
            page.insert_image(stamp_rect, filename=stamp_path, overlay=True)

        doc.save(output_path)
    finally:
        doc.close()
    return output_path


def finalize_to_pdf(docx_path: str, branding: dict, output_dir: str = None) -> str:
    """Convert a DOCX document to a final, stamped PDF ready to send.

    Returns the absolute path to the stamped PDF (named
    "<original-name>_signed.pdf" alongside the source document).
    """
    output_dir = os.path.abspath(output_dir or os.path.dirname(docx_path))
    raw_pdf_path = convert_docx_to_pdf(docx_path, output_dir=output_dir)
    base_name = os.path.splitext(os.path.basename(docx_path))[0]
    final_path = os.path.join(output_dir, f"{base_name}_signed.pdf")
    try:
        stamp_pdf(raw_pdf_path, final_path, branding)
    finally:
        # The unstamped intermediate PDF isn't useful to keep around.
        if raw_pdf_path != final_path and os.path.isfile(raw_pdf_path):
            os.remove(raw_pdf_path)
    return final_path
