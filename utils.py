"""
utils.py — Shared utilities for Training Transcript Generator + LIUNA Certificate Generator
"""

import io
import re
import zipfile

import pandas as pd
from reportlab.lib import colors
from reportlab.lib.enums import TA_CENTER, TA_LEFT
from reportlab.lib.pagesizes import letter
from reportlab.lib.styles import ParagraphStyle
from reportlab.lib.units import inch
from reportlab.platypus import (
    HRFlowable,
    Paragraph,
    SimpleDocTemplate,
    Spacer,
    Table,
    TableStyle,
)
from pypdf import PdfWriter, PdfReader


# ── Course keyword detection ──────────────────────────────────────────────────

COURSE_KEYWORDS: dict[str, str] = {
    "asbestos": "Asbestos Awareness",
    "covid":    "COVID-19 for the Construction Workforce",
    "lead":     "Lead Awareness Worker",
    "hazard":   "Hazard Communication",
}


def detect_course(filename: str, df: pd.DataFrame) -> str:
    """Return a human-readable course name inferred from filename or column headers."""
    fn = filename.lower()
    for kw, name in COURSE_KEYWORDS.items():
        if kw in fn:
            return name
    cols = " ".join(df.columns).lower()
    for kw, name in COURSE_KEYWORDS.items():
        if kw in cols:
            return name
    return filename.replace(".csv", "").replace("_", " ").strip()


# ── Date helper ───────────────────────────────────────────────────────────────

def clean_date(raw: str) -> str | None:
    """
    Normalise a date string to MM/DD/YYYY.
    Returns None for empty / placeholder values.
    """
    if not raw or raw in ("-", "nan", "Not finished yet"):
        return None
    try:
        return pd.to_datetime(raw).strftime("%m/%d/%Y")
    except Exception:
        return raw  # return as-is rather than silently dropping


# ── CSV processing ────────────────────────────────────────────────────────────

def process_files(uploaded_files) -> tuple[list[dict], list[str]]:
    """
    Parse one or more CSV uploads.
    Workers are keyed by e-mail address so they are de-duplicated across files.

    Returns:
        people        — list of person dicts sorted alphabetically by name
        course_names  — ordered list of unique course names detected
    """
    people: dict[str, dict] = {}
    course_names_seen: list[str] = []

    for uf in uploaded_files:
        df = pd.read_csv(uf, encoding="utf-8-sig")
        course_name = detect_course(uf.name, df)
        if course_name not in course_names_seen:
            course_names_seen.append(course_name)

        cols = list(df.columns)

        # Locate SSN column — the column immediately after "last 4 digits … social"
        ssn_col: str | None = None
        for i, c in enumerate(cols):
            if "last 4 digits" in c.lower() and "social" in c.lower():
                if i + 1 < len(cols):
                    ssn_col = cols[i + 1]
                break

        for _, row in df.iterrows():
            name  = str(row.get("Name",  "")).strip()
            email = str(row.get("Email", "")).strip()
            if not email or email == "nan":
                continue

            key      = email.lower()
            result   = str(row.get("Course result", "")).strip()
            finished = str(row.get("Finished", "")).strip()
            started  = str(row.get("Started",  "")).strip()

            ssn: str | None = None
            if ssn_col:
                raw_ssn = str(row.get(ssn_col, "")).strip()
                if raw_ssn and raw_ssn not in ("-", "nan"):
                    ssn = raw_ssn

            if key not in people:
                people[key] = {"name": name, "email": email, "ssn4": None, "courses": []}
            if name and name != "-":
                people[key]["name"] = name
            if ssn and not people[key]["ssn4"]:
                people[key]["ssn4"] = ssn

            people[key]["courses"].append({
                "course":          course_name,
                "status":          result,
                "completion_date": clean_date(finished),
                "started_date":    clean_date(started),
            })

    return (
        sorted(people.values(), key=lambda x: x["name"].lower()),
        course_names_seen,
    )


# ── PDF builder ───────────────────────────────────────────────────────────────

def build_person_pdf(person: dict, use_color: bool = True) -> bytes:
    """Render a single training-transcript PDF and return raw bytes."""

    # ── Colour palette ────────────────────────────────────────────────────
    if use_color:
        NAVY      = colors.HexColor("#1B3A6B")
        GOLD      = colors.HexColor("#C9A84C")
        GREEN_DK  = colors.HexColor("#2E7D32")
        GREEN_LT  = colors.HexColor("#E8F5E9")
        ORANGE_DK = colors.HexColor("#E65100")
        ORANGE_LT = colors.HexColor("#FFF3E0")
    else:
        NAVY      = colors.black
        GOLD      = colors.HexColor("#888888")
        GREEN_DK  = colors.black
        GREEN_LT  = colors.HexColor("#F5F5F5")
        ORANGE_DK = colors.black
        ORANGE_LT = colors.HexColor("#EEEEEE")

    GRAY_LT = colors.HexColor("#F5F5F5")
    GRAY_BD = colors.HexColor("#DDDDDD")
    WHITE   = colors.white
    TEXT    = colors.HexColor("#2C2C2C")

    # ── Styles ────────────────────────────────────────────────────────────
    def S(name: str, **kw) -> ParagraphStyle:
        return ParagraphStyle(name, **kw)

    title_s       = S("t",  fontName="Helvetica-Bold",    fontSize=20, textColor=WHITE,                      alignment=TA_CENTER)
    sub_s         = S("s",  fontName="Helvetica-Oblique", fontSize=10, textColor=GOLD,                       alignment=TA_CENTER)
    label_s       = S("l",  fontName="Helvetica-Bold",    fontSize=8,  textColor=NAVY)
    value_s       = S("v",  fontName="Helvetica",         fontSize=9,  textColor=TEXT)
    sec_s         = S("se", fontName="Helvetica-Bold",    fontSize=10, textColor=WHITE,                      alignment=TA_LEFT)
    course_s      = S("c",  fontName="Helvetica-Bold",    fontSize=10, textColor=TEXT)
    status_pass_s = S("sp", fontName="Helvetica-Bold",    fontSize=9,  textColor=GREEN_DK)
    status_prog_s = S("so", fontName="Helvetica-Bold",    fontSize=9,  textColor=ORANGE_DK)
    date_s        = S("d",  fontName="Helvetica",         fontSize=9,  textColor=colors.HexColor("#666666"))
    footer_s      = S("f",  fontName="Helvetica-Oblique", fontSize=8,  textColor=colors.HexColor("#999999"), alignment=TA_CENTER)

    buf = io.BytesIO()
    doc = SimpleDocTemplate(
        buf, pagesize=letter,
        leftMargin=0.65 * inch, rightMargin=0.65 * inch,
        topMargin=0.5  * inch, bottomMargin=0.65 * inch,
    )

    story = []

    # ── Header banner ─────────────────────────────────────────────────────
    header_table = Table(
        [[Paragraph("TRAINING TRANSCRIPT", title_s)],
         [Paragraph("Construction Workforce Safety Training", sub_s)]],
        colWidths=[7.2 * inch],
    )
    header_table.setStyle(TableStyle([
        ("BACKGROUND",    (0, 0), (-1, -1), NAVY),
        ("TOPPADDING",    (0, 0), (-1, -1), 18),
        ("BOTTOMPADDING", (0, -1), (-1, -1), 18),
        ("LEFTPADDING",   (0, 0), (-1, -1), 20),
        ("RIGHTPADDING",  (0, 0), (-1, -1), 20),
    ]))
    story.append(header_table)
    story.append(Spacer(1, 16))

    # ── Worker info block ─────────────────────────────────────────────────
    name_display = person["name"] or person["email"]
    ssn_val      = f"\u2022\u2022\u2022\u2022 {person['ssn4']}" if person.get("ssn4") else "\u2014"

    info_data = [
        [Paragraph("EMPLOYEE",     label_s), Paragraph("EMAIL ADDRESS", label_s), Paragraph("SSN \u2014 LAST 4", label_s)],
        [Paragraph(name_display,   value_s), Paragraph(person["email"], value_s), Paragraph(ssn_val,             value_s)],
    ]
    info_table = Table(info_data, colWidths=[2.2 * inch, 3.3 * inch, 1.7 * inch])
    info_table.setStyle(TableStyle([
        ("BACKGROUND",    (0, 0), (-1, 0), GRAY_LT),
        ("BACKGROUND",    (0, 1), (-1, 1), WHITE),
        ("BOX",           (0, 0), (-1, -1), 0.5, GRAY_BD),
        ("INNERGRID",     (0, 0), (-1, -1), 0.5, GRAY_BD),
        ("TOPPADDING",    (0, 0), (-1, -1), 8),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 8),
        ("LEFTPADDING",   (0, 0), (-1, -1), 10),
        ("RIGHTPADDING",  (0, 0), (-1, -1), 10),
    ]))
    story.append(info_table)
    story.append(Spacer(1, 18))

    # ── Section header ────────────────────────────────────────────────────
    sec_table = Table([[Paragraph("COURSE COMPLETIONS", sec_s)]], colWidths=[7.2 * inch])
    sec_table.setStyle(TableStyle([
        ("BACKGROUND",    (0, 0), (-1, -1), NAVY),
        ("TOPPADDING",    (0, 0), (-1, -1), 8),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 8),
        ("LEFTPADDING",   (0, 0), (-1, -1), 12),
    ]))
    story.append(sec_table)
    story.append(Spacer(1, 4))

    # ── Course rows ───────────────────────────────────────────────────────
    for course in person["courses"]:
        is_pass      = "pass" in course["status"].lower()
        row_bg       = GREEN_LT if is_pass else ORANGE_LT
        status_s     = status_pass_s if is_pass else status_prog_s
        status_label = course["status"] or "\u2014"
        comp_date    = course["completion_date"] or "\u2014"
        start_date   = course["started_date"] or "\u2014"

        row_data = [[
            Paragraph(course["course"], course_s),
            Paragraph(status_label,     status_s),
            Paragraph(f"Started: {start_date}",    date_s),
            Paragraph(f"Completed: {comp_date}",   date_s),
        ]]
        row_table = Table(row_data, colWidths=[2.9 * inch, 1.1 * inch, 1.5 * inch, 1.7 * inch])
        row_table.setStyle(TableStyle([
            ("BACKGROUND",    (0, 0), (-1, -1), row_bg),
            ("TOPPADDING",    (0, 0), (-1, -1), 10),
            ("BOTTOMPADDING", (0, 0), (-1, -1), 10),
            ("LEFTPADDING",   (0, 0), (-1, -1), 10),
            ("RIGHTPADDING",  (0, 0), (-1, -1), 6),
            ("BOX",           (0, 0), (-1, -1), 0.3, GRAY_BD),
        ]))
        story.append(row_table)
        story.append(Spacer(1, 2))

    # ── Footer ────────────────────────────────────────────────────────────
    story.append(Spacer(1, 20))
    story.append(HRFlowable(width="100%", thickness=0.5, color=GOLD))
    story.append(Spacer(1, 6))
    story.append(Paragraph(
        "Generated by Training Transcript Generator \u00b7 Construction Workforce Safety Training",
        footer_s,
    ))

    doc.build(story)
    buf.seek(0)
    return buf.read()


# ── PDF merger ────────────────────────────────────────────────────────────────

def merge_pdfs(pdf_bytes_list: list[bytes]) -> bytes:
    """Merge a list of PDF byte-strings into a single PDF."""
    writer = PdfWriter()
    for pdf_bytes in pdf_bytes_list:
        reader = PdfReader(io.BytesIO(pdf_bytes))
        for page in reader.pages:
            writer.add_page(page)
    out = io.BytesIO()
    writer.write(out)
    out.seek(0)
    return out.read()


# ── ZIP builder ───────────────────────────────────────────────────────────────

def build_zip(people: list[dict], use_color: bool = True) -> bytes:
    """Package one PDF per person into a ZIP archive, returned as bytes."""
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as zf:
        for person in people:
            pdf_bytes = build_person_pdf(person, use_color=use_color)
            safe_name = re.sub(r"[^\w\-]", "_", person["name"] or "transcript")
            zf.writestr(f"{safe_name}.pdf", pdf_bytes)
    buf.seek(0)
    return buf.read()


# ── CSV export ────────────────────────────────────────────────────────────────

def build_clean_csv(people: list[dict]) -> str:
    """Return a well-quoted CSV string covering all workers and courses."""
    rows = []
    for person in people:
        for course in person["courses"]:
            rows.append({
                "Name":            person["name"],
                "Email":           person["email"],
                "SSN Last 4":      person.get("ssn4") or "",
                "Course":          course["course"],
                "Status":          course["status"],
                "Started Date":    course.get("started_date") or "",
                "Completion Date": course.get("completion_date") or "",
                "Passed":          "Yes" if "pass" in course["status"].lower() else "No",
            })
    return pd.DataFrame(rows, columns=[
        "Name", "Email", "SSN Last 4", "Course", "Status",
        "Started Date", "Completion Date", "Passed",
    ]).to_csv(index=False)


# ── Email parser ──────────────────────────────────────────────────────────────

def parse_email_list(raw_text: str) -> list[str]:
    """Extract and deduplicate valid e-mail addresses from free-form text."""
    raw    = raw_text.replace(",", "\n")
    emails = [e.strip().lower() for e in raw.splitlines() if e.strip()]
    valid  = [e for e in emails if re.match(r"^[\w\.\+\-]+@[\w\-]+\.[a-z]{2,}$", e)]
    return list(dict.fromkeys(valid))  # deduplicate, preserve order


# ── HTML transcript preview ───────────────────────────────────────────────────

def build_preview_html(person: dict) -> str:
    """Return an HTML string that visually mimics the PDF transcript layout."""
    name_display = person["name"] or person["email"]
    ssn_display  = f"\u2022\u2022\u2022\u2022 {person['ssn4']}" if person.get("ssn4") else "\u2014"

    rows_html = ""
    for course in person["courses"]:
        status   = course["status"] or "\u2014"
        comp     = course["completion_date"] or "\u2014"
        start    = course["started_date"] or "\u2014"
        is_pass  = "pass" in status.lower()
        row_cls  = "pass-row" if is_pass else "prog-row"
        stat_cls = "cpass"    if is_pass else "cprog"
        rows_html += f"""
        <div class="preview-course-row {row_cls}">
            <div class="cname">{course['course']}</div>
            <div class="{stat_cls}">{status}</div>
            <div class="cdate">Started<br>{start}</div>
            <div class="cdate">Completed<br>{comp}</div>
        </div>"""

    return f"""
    <div class="preview-wrap">
        <div class="preview-hdr">
            <h3>TRAINING TRANSCRIPT</h3>
            <p>Construction Workforce Safety Training</p>
        </div>
        <div class="preview-meta">
            <div class="preview-cell">
                <div class="lbl">Employee</div>
                <div class="val">{name_display}</div>
            </div>
            <div class="preview-cell">
                <div class="lbl">Email</div>
                <div class="val">{person['email']}</div>
            </div>
            <div class="preview-cell">
                <div class="lbl">SSN Last 4</div>
                <div class="val">{ssn_display}</div>
            </div>
        </div>
        <div class="preview-sec-hdr">Course Completions</div>
        {rows_html}
        <div class="preview-footer">
            Generated by Training Transcript Generator \u00b7 Construction Workforce Safety Training
        </div>
    </div>"""
