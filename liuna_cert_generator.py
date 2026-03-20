"""
LIUNA Certificate Generator
============================
Reads a CSV (no header row), generates one PDF per student containing
all their course certificates. Certificates are grouped by Member ID.

CSV column layout (0-indexed):
  2  = Class name
  7  = Hours completed
  10 = Completion date
  11 = Member ID
  12 = Last name
  13 = First name

Usage:
  python liuna_cert_generator.py --csv ClassInformation.csv \
      --director "Jane Smith" \
      --title "Director" \
      --org "LIUNA Training of Michigan" \
      --address "11155 Beardslee Road" \
      --city "Perry, MI 48872" \
      --phone "(517) 625-4919" \
      --output ./certificates
"""

import argparse
import csv
import os
import re
import sys
import textwrap
from collections import defaultdict
from datetime import datetime
from pathlib import Path

from reportlab.lib.pagesizes import landscape, letter
from reportlab.lib.units import inch
from reportlab.pdfgen import canvas as rl_canvas
from reportlab.lib import colors


# ── Column indices (0-based) ────────────────────────────────────────────────
COL_CLASS_NAME = 2
COL_HOURS      = 7
COL_DATE_END   = 10
COL_MEMBER_ID  = 11
COL_LAST_NAME  = 12
COL_FIRST_NAME = 13


# ── Helpers ──────────────────────────────────────────────────────────────────

def to_title_case(s: str) -> str:
    return s.lower().title()


def fmt_date(raw: str) -> str:
    """Convert 'Friday, January 30, 2026' or 'January 30, 2026' -> 'January 30, 2026'."""
    if not raw:
        return ""
    # Strip leading weekday if present: "Friday, January 30, 2026"
    cleaned = re.sub(r"^[A-Za-z]+,\s*", "", raw.strip())
    for fmt in ("%B %d, %Y", "%m/%d/%Y", "%Y-%m-%d"):
        try:
            dt = datetime.strptime(cleaned, fmt)
            return dt.strftime("%B %d, %Y")
        except ValueError:
            continue
    return raw  # fall back to raw string


def get_name(row: list) -> str:
    first = row[COL_FIRST_NAME].strip() if len(row) > COL_FIRST_NAME else ""
    last  = row[COL_LAST_NAME].strip()  if len(row) > COL_LAST_NAME  else ""
    return to_title_case(f"{first} {last}".strip()) or "Unknown"


def safe_filename(name: str, member_id: str) -> str:
    safe = re.sub(r"[^A-Za-z0-9_\-]", "_", f"{name}_{member_id}")
    return f"cert_{safe}.pdf"


# ── CSV loading ──────────────────────────────────────────────────────────────

def load_csv(filepath: str) -> dict:
    """
    Parse CSV, group rows by Member ID.
    Returns dict: { member_id: { 'name': str, 'mid': str, 'certs': [...] } }
    """
    groups = defaultdict(lambda: {"name": "", "mid": "", "certs": []})

    with open(filepath, newline="", encoding="utf-8-sig") as f:
        reader = csv.reader(f)
        for row in reader:
            if not row:
                continue
            # Pad row if it's shorter than expected
            while len(row) <= max(COL_CLASS_NAME, COL_HOURS, COL_DATE_END,
                                   COL_MEMBER_ID, COL_LAST_NAME, COL_FIRST_NAME):
                row.append("")

            mid = row[COL_MEMBER_ID].strip()
            if not mid:
                continue

            name  = get_name(row)
            cls   = to_title_case(row[COL_CLASS_NAME].strip())
            date  = row[COL_DATE_END].strip()
            hours = row[COL_HOURS].strip()

            groups[mid]["name"] = name
            groups[mid]["mid"]  = mid
            groups[mid]["certs"].append({
                "name":  name,
                "cls":   cls,
                "date":  date,
                "hours": hours,
                "mid":   mid,
            })

    return dict(groups)


# ── Certificate drawing ──────────────────────────────────────────────────────

PAGE_W, PAGE_H = landscape(letter)   # 792 x 612 pt  (11 x 8.5 in)

# Colours
BLACK      = colors.HexColor("#1A1A1A")
DARK_GRAY  = colors.HexColor("#444444")
MID_GRAY   = colors.HexColor("#888888")
LIGHT_GRAY = colors.HexColor("#AAAAAA")
PALE_GRAY  = colors.HexColor("#CCCCCC")
RULE_GRAY  = colors.HexColor("#CCCCCC")
WHITE      = colors.white


def draw_cert(c: rl_canvas.Canvas,
              name: str, cls: str, date: str, hours: str, member_id: str,
              dir_name: str, dir_title: str,
              org_name: str, org_addr: str, org_city: str, org_phone: str):
    """Draw a single certificate page onto canvas `c`."""

    W, H = PAGE_W, PAGE_H
    cx   = W / 2

    # White background
    c.setFillColor(WHITE)
    c.rect(0, 0, W, H, fill=1, stroke=0)

    # ── Outer double border ──────────────────────────────────────────────
    c.setStrokeColor(BLACK)
    c.setLineWidth(2.5)
    c.rect(14, 14, W - 28, H - 28, fill=0, stroke=1)
    c.setLineWidth(0.75)
    c.rect(23, 23, W - 46, H - 46, fill=0, stroke=1)

    # ── Organization header ──────────────────────────────────────────────
    c.setFillColor(BLACK)
    c.setFont("Times-Bold", 20)
    c.drawCentredString(cx, H - 55, (org_name or "LIUNA Training of Michigan").upper())

    c.setFont("Helvetica", 11)
    c.setFillColor(DARK_GRAY)
    c.drawCentredString(cx, H - 72, (org_addr or "").upper())
    c.drawCentredString(cx, H - 86, (org_city or "").upper())

    # Rule under header
    c.setStrokeColor(BLACK)
    c.setLineWidth(0.75)
    c.line(55, H - 98, W - 55, H - 98)

    # ── "DECLARES THAT" ──────────────────────────────────────────────────
    c.setFont("Times-Italic", 12)
    c.setFillColor(MID_GRAY)
    c.drawCentredString(cx, H - 130, "DECLARES THAT")

    # ── Recipient name ───────────────────────────────────────────────────
    c.setFont("Times-Bold", 38)
    c.setFillColor(BLACK)
    c.drawCentredString(cx, H - 178, name or "Recipient Name")

    # Underline name
    name_w = c.stringWidth(name or "Recipient Name", "Times-Bold", 38)
    c.setStrokeColor(LIGHT_GRAY)
    c.setLineWidth(1)
    c.line(cx - name_w / 2, H - 184, cx + name_w / 2, H - 184)

    # ── "ON [DATE]" ──────────────────────────────────────────────────────
    c.setFont("Times-Italic", 13)
    c.setFillColor(MID_GRAY)
    c.drawCentredString(cx, H - 218, f"ON {fmt_date(date).upper()}")

    # ── Class name ───────────────────────────────────────────────────────
    c.setFont("Times-Bold", 24)
    c.setFillColor(BLACK)
    c.drawCentredString(cx, H - 258, (cls or "Course Name").upper())

    # ── Hours line ───────────────────────────────────────────────────────
    c.setFont("Helvetica", 13)
    c.setFillColor(DARK_GRAY)
    if hours:
        try:
            hours_fmt = f"{float(hours):.2f}"
        except ValueError:
            hours_fmt = hours
        hours_str = f"COMPLETED {hours_fmt} HOURS OF TRAINING"
    else:
        hours_str = "COMPLETED TRAINING"
    c.drawCentredString(cx, H - 288, hours_str)

    # Light rule
    c.setStrokeColor(RULE_GRAY)
    c.setLineWidth(0.75)
    c.line(55, H - 306, W - 55, H - 306)

    # ── Two-column signature area ────────────────────────────────────────
    # Left: Student Number | Right: Director
    sig_y      = H - 390          # baseline of the signature line
    col_w      = 190              # width of each signature line
    gap        = 60               # gap between columns
    total_w    = col_w * 2 + gap
    left_x     = cx - total_w / 2
    right_x    = left_x + col_w + gap
    left_cx    = left_x  + col_w / 2
    right_cx   = right_x + col_w / 2

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

    # ── Disclaimer ───────────────────────────────────────────────────────
    disclaimer = (
        f"The {org_name or 'LIUNA Training of Michigan'} is not, and should not be construed as, "
        "a substitute for an employer's obligation under OSHA or EPA to provide employees with "
        "safety training specific to the nature of the employee's job and pertinent to the actual "
        "equipment and machinery with which the employee will be working while in the contractor's employment."
    )

    c.setFont("Helvetica", 7)
    c.setFillColor(PALE_GRAY)

    # Manual word-wrap for reportlab
    max_w   = W - 110
    words   = disclaimer.split()
    lines   = []
    line    = ""
    for word in words:
        test = f"{line} {word}".strip()
        if c.stringWidth(test, "Helvetica", 7) > max_w and line:
            lines.append(line)
            line = word
        else:
            line = test
    if line:
        lines.append(line)

    disc_y = 60 + (len(lines) - 1) * 11
    for i, ln in enumerate(lines):
        c.drawCentredString(cx, disc_y - i * 11, ln)

    # ── Phone ────────────────────────────────────────────────────────────
    c.setFont("Helvetica", 8)
    c.setFillColor(LIGHT_GRAY)
    c.drawCentredString(cx, 36, org_phone or "")


# ── PDF generation ───────────────────────────────────────────────────────────

def generate_pdfs(groups: dict, output_dir: str,
                  dir_name: str, dir_title: str,
                  org_name: str, org_addr: str, org_city: str, org_phone: str):
    Path(output_dir).mkdir(parents=True, exist_ok=True)
    total = len(groups)

    for i, (mid, group) in enumerate(groups.items(), 1):
        fname    = safe_filename(group["name"], mid)
        out_path = os.path.join(output_dir, fname)

        c = rl_canvas.Canvas(out_path, pagesize=landscape(letter))

        for j, cert in enumerate(group["certs"]):
            if j > 0:
                c.showPage()
            draw_cert(
                c,
                name       = cert["name"],
                cls        = cert["cls"],
                date       = cert["date"],
                hours      = cert["hours"],
                member_id  = cert["mid"],
                dir_name   = dir_name,
                dir_title  = dir_title,
                org_name   = org_name,
                org_addr   = org_addr,
                org_city   = org_city,
                org_phone  = org_phone,
            )

        c.save()
        print(f"  [{i}/{total}] {fname}  ({len(group['certs'])} cert{'s' if len(group['certs']) > 1 else ''})")

    print(f"\nDone — {total} PDF{'s' if total != 1 else ''} saved to: {output_dir}")


# ── CLI entry point ──────────────────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser(
        description="Generate LIUNA completion certificates from a CSV file."
    )
    parser.add_argument("--csv",       required=True,  help="Path to CSV file (no header row)")
    parser.add_argument("--director",  default="",     help="Director's full name")
    parser.add_argument("--title",     default="Director", help="Director's title")
    parser.add_argument("--org",       default="LIUNA Training of Michigan", help="Organization name")
    parser.add_argument("--address",   default="11155 Beardslee Road",       help="Street address")
    parser.add_argument("--city",      default="Perry, MI 48872",            help="City, State ZIP")
    parser.add_argument("--phone",     default="(517) 625-4919",             help="Phone number")
    parser.add_argument("--output",    default="./certificates",             help="Output directory")
    args = parser.parse_args()

    if not os.path.isfile(args.csv):
        print(f"Error: CSV file not found: {args.csv}", file=sys.stderr)
        sys.exit(1)

    print(f"Loading CSV: {args.csv}")
    groups = load_csv(args.csv)
    print(f"Found {len(groups)} unique student(s) across {sum(len(g['certs']) for g in groups.values())} row(s)\n")
    print(f"Generating PDFs into: {args.output}")

    generate_pdfs(
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
