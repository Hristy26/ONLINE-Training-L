"""
liuna_cert_generator.py — LIUNA Completion Certificate Generator
================================================================
Generates one PDF per student containing all their course certificates.
Certificates are grouped by Member ID.

Can be used two ways:
  1. As a CLI script:
       python liuna_cert_generator.py --csv ClassInformation.csv \\
           --director "Jane Smith" --title "Director" \\
           --org "LIUNA Training of Michigan" \\
           --address "11155 Beardslee Road" --city "Perry, MI 48872" \\
           --phone "(517) 625-4919" --output ./certificates

  2. As a library imported by app.py (Streamlit UI):
       from liuna_cert_generator import load_csv_from_text, generate_pdfs_to_zip, generate_pdfs_merged

CSV column layout (0-indexed, no header row):
  2  = Class name
  7  = Hours completed
  10 = Completion date
  11 = Member ID
  12 = Last name
  13 = First name
"""

import argparse
import csv
import io
import os
import re
import sys
import zipfile
from collections import defaultdict
from datetime import datetime
from pathlib import Path

from pypdf import PdfWriter, PdfReader
from reportlab.lib import colors
from reportlab.lib.pagesizes import landscape, letter
from reportlab.lib.units import inch
from reportlab.pdfgen import canvas as rl_canvas
from reportlab.platypus import Paragraph, SimpleDocTemplate
from reportlab.lib.styles import ParagraphStyle
from reportlab.lib.enums import TA_CENTER


# ── Column indices (0-based) ──────────────────────────────────────────────────
COL_CLASS_NAME = 2
COL_HOURS      = 7
COL_DATE_END   = 10
COL_MEMBER_ID  = 11
COL_LAST_NAME  = 12
COL_FIRST_NAME = 13

REQUIRED_COLS  = max(COL_CLASS_NAME, COL_HOURS, COL_DATE_END,
                     COL_MEMBER_ID, COL_LAST_NAME, COL_FIRST_NAME)

# ── Colours ───────────────────────────────────────────────────────────────────
BLACK      = colors.HexColor("#1A1A1A")
DARK_GRAY  = colors.HexColor("#444444")
MID_GRAY   = colors.HexColor("#888888")
LIGHT_GRAY = colors.HexColor("#AAAAAA")
PALE_GRAY  = colors.HexColor("#CCCCCC")
RULE_GRAY  = colors.HexColor("#CCCCCC")
WHITE      = colors.white

# ── Page dimensions (landscape letter) ───────────────────────────────────────
PAGE_W, PAGE_H = landscape(letter)   # 792 × 612 pt


# ── Helpers ───────────────────────────────────────────────────────────────────

def to_title_case(s: str) -> str:
    return s.lower().title()


def fmt_date(raw: str) -> str:
    """
    Normalise a date string to 'Month DD, YYYY'.
    Strips a leading weekday ('Friday, January 30, 2026' → 'January 30, 2026').
    Returns the original string on parse failure instead of silently swallowing it.
    """
    if not raw:
        return ""
    cleaned = re.sub(r"^[A-Za-z]+,\s*", "", raw.strip())
    for fmt in ("%B %d, %Y", "%m/%d/%Y", "%Y-%m-%d"):
        try:
            return datetime.strptime(cleaned, fmt).strftime("%B %d, %Y")
        except ValueError:
            continue
    # Return as-is so the caller can see the unparseable value
    return raw


def safe_filename(name: str, member_id: str) -> str:
    safe = re.sub(r"[^A-Za-z0-9_\-]", "_", f"{name}_{member_id}")
    return f"cert_{safe}.pdf"


def _pad_row(row: list) -> list:
    """Ensure a CSV row has at least REQUIRED_COLS + 1 entries."""
    while len(row) <= REQUIRED_COLS:
        row.append("")
    return row


def _validate_row(row: list) -> list[str]:
    """Return a list of warning strings for missing critical fields."""
    warnings = []
    if not row[COL_MEMBER_ID].strip():
        warnings.append("Missing Member ID — row skipped")
    if not row[COL_CLASS_NAME].strip():
        warnings.append(f"Member {row[COL_MEMBER_ID]}: missing class name")
    if not row[COL_DATE_END].strip():
        warnings.append(f"Member {row[COL_MEMBER_ID]}: missing completion date")
    return warnings


# ── CSV loading ───────────────────────────────────────────────────────────────

def _parse_rows(reader) -> tuple[dict, list[str]]:
    """
    Core parsing logic shared by load_csv() and load_csv_from_text().

    Returns:
        groups   — { member_id: { 'name': str, 'mid': str, 'certs': [...] } }
        warnings — list of non-fatal warning strings
    """
    groups:   dict       = defaultdict(lambda: {"name": "", "mid": "", "certs": []})
    warnings: list[str]  = []

    for row in reader:
        if not row:
            continue
        row = _pad_row(row)

        row_warnings = _validate_row(row)
        warnings.extend(row_warnings)
        if any("row skipped" in w for w in row_warnings):
            continue

        mid        = row[COL_MEMBER_ID].strip()
        first_name = row[COL_FIRST_NAME].strip()
        last_name  = row[COL_LAST_NAME].strip()
        name       = to_title_case(f"{first_name} {last_name}".strip()) or "Unknown"
        cls        = to_title_case(row[COL_CLASS_NAME].strip())
        date       = row[COL_DATE_END].strip()
        hours      = row[COL_HOURS].strip()

        groups[mid]["name"] = name
        groups[mid]["mid"]  = mid
        groups[mid]["certs"].append({
            "name":  name,
            "cls":   cls,
            "date":  date,
            "hours": hours,
            "mid":   mid,
        })

    return dict(groups), warnings


def load_csv(filepath: str) -> tuple[dict, list[str]]:
    """Load LIUNA CSV from a file path. Returns (groups, warnings)."""
    with open(filepath, newline="", encoding="utf-8-sig") as f:
        return _parse_rows(csv.reader(f))


def load_csv_from_text(text: str) -> dict:
    """
    Load LIUNA CSV from an in-memory string (used by the Streamlit UI).
    Raises ValueError if no valid students are found.
    Returns groups dict only (warnings are silently ignored in UI context).
    """
    reader          = csv.reader(text.splitlines())
    groups, warnings = _parse_rows(reader)
    if not groups:
        raise ValueError("No valid student records found in the uploaded CSV.")
    return groups


# ── Certificate drawing ───────────────────────────────────────────────────────

def _draw_wrapped_text(c: rl_canvas.Canvas,
                       text: str, font: str, size: int,
                       fill_color, cx: float, y: float,
                       max_width: float, line_height: float) -> None:
    """Draw word-wrapped centred text using ReportLab's canvas."""
    c.setFont(font, size)
    c.setFillColor(fill_color)
    words = text.split()
    lines, line = [], ""
    for word in words:
        test = f"{line} {word}".strip()
        if c.stringWidth(test, font, size) > max_width and line:
            lines.append(line)
            line = word
        else:
            line = test
    if line:
        lines.append(line)

    # Centre the block vertically around the given y
    top_y = y + ((len(lines) - 1) * line_height) / 2
    for i, ln in enumerate(lines):
        c.drawCentredString(cx, top_y - i * line_height, ln)


def draw_cert(
    c: rl_canvas.Canvas,
    name: str, cls: str, date: str, hours: str, member_id: str,
    dir_name: str, dir_title: str,
    org_name: str, org_addr: str, org_city: str, org_phone: str,
) -> None:
    """Draw a single certificate page onto canvas `c`."""
    W, H = PAGE_W, PAGE_H
    cx   = W / 2

    # White background
    c.setFillColor(WHITE)
    c.rect(0, 0, W, H, fill=1, stroke=0)

    # ── Outer double border ───────────────────────────────────────────────
    c.setStrokeColor(BLACK)
    c.setLineWidth(2.5)
    c.rect(14, 14, W - 28, H - 28, fill=0, stroke=1)
    c.setLineWidth(0.75)
    c.rect(23, 23, W - 46, H - 46, fill=0, stroke=1)

    # ── Organization header ───────────────────────────────────────────────
    c.setFillColor(BLACK)
    c.setFont("Times-Bold", 20)
    c.drawCentredString(cx, H - 55, (org_name or "LIUNA Training of Michigan").upper())

    c.setFont("Helvetica", 11)
    c.setFillColor(DARK_GRAY)
    c.drawCentredString(cx, H - 72, (org_addr or "").upper())
    c.drawCentredString(cx, H - 86, (org_city or "").upper())

    c.setStrokeColor(BLACK)
    c.setLineWidth(0.75)
    c.line(55, H - 98, W - 55, H - 98)

    # ── "DECLARES THAT" ───────────────────────────────────────────────────
    c.setFont("Times-Italic", 12)
    c.setFillColor(MID_GRAY)
    c.drawCentredString(cx, H - 130, "DECLARES THAT")

    # ── Recipient name ────────────────────────────────────────────────────
    c.setFont("Times-Bold", 38)
    c.setFillColor(BLACK)
    c.drawCentredString(cx, H - 178, name or "Recipient Name")

    name_w = c.stringWidth(name or "Recipient Name", "Times-Bold", 38)
    c.setStrokeColor(LIGHT_GRAY)
    c.setLineWidth(1)
    c.line(cx - name_w / 2, H - 184, cx + name_w / 2, H - 184)

    # ── "ON [DATE]" ───────────────────────────────────────────────────────
    c.setFont("Times-Italic", 13)
    c.setFillColor(MID_GRAY)
    c.drawCentredString(cx, H - 218, f"ON {fmt_date(date).upper()}")

    # ── Class name ────────────────────────────────────────────────────────
    c.setFont("Times-Bold", 24)
    c.setFillColor(BLACK)
    c.drawCentredString(cx, H - 258, (cls or "Course Name").upper())

    # ── Hours line ────────────────────────────────────────────────────────
    c.setFont("Helvetica", 13)
    c.setFillColor(DARK_GRAY)
    if hours:
        try:
            hours_str = f"COMPLETED {float(hours):.2f} HOURS OF TRAINING"
        except ValueError:
            hours_str = f"COMPLETED {hours} HOURS OF TRAINING"
    else:
        hours_str = "COMPLETED TRAINING"
    c.drawCentredString(cx, H - 288, hours_str)

    c.setStrokeColor(RULE_GRAY)
    c.setLineWidth(0.75)
    c.line(55, H - 306, W - 55, H - 306)

    # ── Signature area ────────────────────────────────────────────────────
    sig_y   = H - 390
    col_w   = 190
    gap     = 60
    total_w = col_w * 2 + gap
    left_x  = cx - total_w / 2
    right_x = left_x + col_w + gap
    left_cx = left_x  + col_w / 2
    right_cx= right_x + col_w / 2

    c.setStrokeColor(BLACK)
    c.setLineWidth(1)

    # Left: Student Number
    c.line(left_x, sig_y, left_x + col_w, sig_y)
    c.setFont("Times-Bold", 12)
    c.setFillColor(BLACK)
    c.drawCentredString(left_cx, sig_y + 10, member_id or "—")
    c.setFont("Helvetica", 10)
    c.setFillColor(DARK_GRAY)
    c.drawCentredString(left_cx, sig_y - 14, "STUDENT NUMBER")

    # Right: Director
    c.line(right_x, sig_y, right_x + col_w, sig_y)
    c.setFont("Times-Bold", 12)
    c.setFillColor(BLACK)
    c.drawCentredString(right_cx, sig_y + 10, dir_name or "Director Name")
    c.setFont("Helvetica", 10)
    c.setFillColor(DARK_GRAY)
    c.drawCentredString(right_cx, sig_y - 14, (dir_title or "DIRECTOR").upper())

    # ── Disclaimer (word-wrapped) ─────────────────────────────────────────
    disclaimer = (
        f"The {org_name or 'LIUNA Training of Michigan'} is not, and should not be construed as, "
        "a substitute for an employer's obligation under OSHA or EPA to provide employees with "
        "safety training specific to the nature of the employee's job and pertinent to the actual "
        "equipment and machinery with which the employee will be working while in the contractor's employment."
    )
    _draw_wrapped_text(
        c, disclaimer,
        font="Helvetica", size=7, fill_color=PALE_GRAY,
        cx=cx, y=56, max_width=W - 110, line_height=11,
    )

    # ── Phone ─────────────────────────────────────────────────────────────
    c.setFont("Helvetica", 8)
    c.setFillColor(LIGHT_GRAY)
    c.drawCentredString(cx, 36, org_phone or "")


# ── Per-student PDF builder ───────────────────────────────────────────────────

def build_student_pdf(group: dict,
                      org_name: str, org_addr: str, org_city: str, org_phone: str,
                      dir_name: str, dir_title: str) -> bytes:
    """Render all certificates for one student into a single PDF. Returns bytes."""
    buf = io.BytesIO()
    c   = rl_canvas.Canvas(buf, pagesize=landscape(letter))
    for i, cert in enumerate(group["certs"]):
        if i > 0:
            c.showPage()
        draw_cert(
            c,
            name      = cert["name"],
            cls       = cert["cls"],
            date      = cert["date"],
            hours     = cert["hours"],
            member_id = cert["mid"],
            dir_name  = dir_name,
            dir_title = dir_title,
            org_name  = org_name,
            org_addr  = org_addr,
            org_city  = org_city,
            org_phone = org_phone,
        )
    c.save()
    buf.seek(0)
    return buf.read()


# ── Bulk output helpers (used by Streamlit UI) ────────────────────────────────

def generate_pdfs_to_zip(groups: dict,
                          org_name: str = "", org_addr: str = "",
                          org_city: str = "", org_phone: str = "",
                          dir_name: str = "", dir_title: str = "Director") -> bytes:
    """Package one PDF per student into a ZIP archive. Returns bytes."""
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as zf:
        for mid, group in groups.items():
            pdf_bytes = build_student_pdf(
                group,
                org_name=org_name, org_addr=org_addr,
                org_city=org_city,  org_phone=org_phone,
                dir_name=dir_name,  dir_title=dir_title,
            )
            fname = safe_filename(group["name"], mid)
            zf.writestr(fname, pdf_bytes)
    buf.seek(0)
    return buf.read()


def generate_pdfs_merged(groups: dict,
                          org_name: str = "", org_addr: str = "",
                          org_city: str = "", org_phone: str = "",
                          dir_name: str = "", dir_title: str = "Director") -> bytes:
    """Merge all student PDFs into one PDF. Returns bytes."""
    writer = PdfWriter()
    for mid, group in groups.items():
        pdf_bytes = build_student_pdf(
            group,
            org_name=org_name, org_addr=org_addr,
            org_city=org_city,  org_phone=org_phone,
            dir_name=dir_name,  dir_title=dir_title,
        )
        reader = PdfReader(io.BytesIO(pdf_bytes))
        for page in reader.pages:
            writer.add_page(page)
    out = io.BytesIO()
    writer.write(out)
    out.seek(0)
    return out.read()


# ── CLI output helper ─────────────────────────────────────────────────────────

def generate_pdfs_to_disk(groups: dict, output_dir: str,
                           org_name: str, org_addr: str, org_city: str, org_phone: str,
                           dir_name: str, dir_title: str) -> None:
    """Write one PDF file per student to output_dir. Prints progress."""
    Path(output_dir).mkdir(parents=True, exist_ok=True)
    total = len(groups)
    for i, (mid, group) in enumerate(groups.items(), 1):
        fname    = safe_filename(group["name"], mid)
        out_path = os.path.join(output_dir, fname)
        pdf_bytes = build_student_pdf(
            group,
            org_name=org_name, org_addr=org_addr,
            org_city=org_city,  org_phone=org_phone,
            dir_name=dir_name,  dir_title=dir_title,
        )
        with open(out_path, "wb") as f:
            f.write(pdf_bytes)
        cert_count = len(group["certs"])
        print(f"  [{i}/{total}] {fname}  ({cert_count} cert{'s' if cert_count > 1 else ''})")
    print(f"\nDone — {total} PDF{'s' if total != 1 else ''} saved to: {output_dir}")


# ── CLI entry point ───────────────────────────────────────────────────────────

def main() -> None:
    parser = argparse.ArgumentParser(
        description="Generate LIUNA completion certificates from a CSV file."
    )
    parser.add_argument("--csv",      required=True,                              help="Path to CSV (no header row)")
    parser.add_argument("--director", default="",                                 help="Director's full name")
    parser.add_argument("--title",    default="Director",                         help="Director's title")
    parser.add_argument("--org",      default="LIUNA Training of Michigan",       help="Organization name")
    parser.add_argument("--address",  default="11155 Beardslee Road",             help="Street address")
    parser.add_argument("--city",     default="Perry, MI 48872",                  help="City, State ZIP")
    parser.add_argument("--phone",    default="(517) 625-4919",                   help="Phone number")
    parser.add_argument("--output",   default="./certificates",                   help="Output directory")
    args = parser.parse_args()

    if not os.path.isfile(args.csv):
        print(f"Error: CSV file not found: {args.csv}", file=sys.stderr)
        sys.exit(1)

    print(f"Loading CSV: {args.csv}")
    groups, warnings = load_csv(args.csv)

    if warnings:
        print(f"\n⚠️  {len(warnings)} warning(s):")
        for w in warnings:
            print(f"   {w}")
        print()

    total_certs = sum(len(g["certs"]) for g in groups.values())
    print(f"Found {len(groups)} unique student(s) across {total_certs} row(s)\n")
    print(f"Generating PDFs into: {args.output}")

    generate_pdfs_to_disk(
        groups,
        output_dir = args.output,
        dir_name   = args.director,
        dir_title  = args.title,
        org_name   = args.org,
        org_addr   = args.address,
        org_city   = args.city,
        org_phone  = args.phone,
    )


if __name__ == "__main__":
    main()
