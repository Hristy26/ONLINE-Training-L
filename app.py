"""
app.py — Training Transcript + LIUNA Certificate Generator
Multi-page Streamlit application.

Pages:
  📤  Upload & Process
  👥  Preview Workers
  📄  Generate PDFs
  🔍  Batch Lookup
  ✏️  Export CSV
  🏆  LIUNA Certificates
  ⚙️  Settings

All shared processing / PDF-building logic lives in utils.py.
LIUNA certificate drawing lives in liuna_cert_generator.py.
"""

import io
import re

import pandas as pd
import streamlit as st

from utils import (
    COURSE_KEYWORDS,
    build_clean_csv,
    build_person_pdf,
    build_preview_html,
    build_zip,
    merge_pdfs,
    parse_email_list,
    process_files,
)
from liuna_cert_generator import (
    load_csv_from_text,
    generate_pdfs_to_zip,
    generate_pdfs_merged,
)

# ── Page config ───────────────────────────────────────────────────────────────
st.set_page_config(
    page_title="Training & Certificate Generator",
    page_icon="📋",
    layout="wide",
)

# ── Global CSS ────────────────────────────────────────────────────────────────
st.markdown("""
<style>
@import url('https://fonts.googleapis.com/css2?family=DM+Sans:wght@300;400;500;600&family=DM+Mono:wght@400;500&display=swap');

html, body, [class*="css"] { font-family: 'DM Sans', sans-serif; }

[data-testid="stSidebar"] {
    background: #1B3A6B !important;
    min-width: 230px !important;
    max-width: 230px !important;
}
[data-testid="stSidebar"] * { color: #fff !important; }

.sidebar-logo {
    padding: 28px 20px 16px;
    border-bottom: 1px solid rgba(255,255,255,0.12);
    margin-bottom: 10px;
}
.sidebar-logo h1 { font-size: 1rem; font-weight: 700; color: #fff !important; margin: 0 0 3px; }
.sidebar-logo p  { font-size: 0.72rem; color: #C9A84C !important; margin: 0; }

.nav-section-label {
    font-size: 0.65rem; font-weight: 700; letter-spacing: 1.5px;
    text-transform: uppercase; color: rgba(255,255,255,0.35) !important;
    padding: 14px 20px 4px;
}
.nav-item {
    display: flex; align-items: center; gap: 10px;
    padding: 10px 20px; border-radius: 0 8px 8px 0;
    margin: 2px 8px 2px 0; font-size: 0.875rem; font-weight: 500;
    color: rgba(255,255,255,0.7) !important; border-left: 3px solid transparent;
}
.nav-item.active {
    background: rgba(201,168,76,0.18); color: #fff !important;
    border-left-color: #C9A84C; font-weight: 600;
}

.stApp { background: #F7F6F2; }
.block-container { padding-top: 2rem !important; max-width: 960px; }

.page-header {
    background: #1B3A6B; border-radius: 14px;
    padding: 28px 32px 22px; margin-bottom: 24px;
    position: relative; overflow: hidden;
}
.page-header::before {
    content: ''; position: absolute; top: -30px; right: -30px;
    width: 140px; height: 140px;
    background: rgba(201,168,76,0.14); border-radius: 50%;
}
.page-header h2 { color: #fff; font-size: 1.4rem; font-weight: 700; margin: 0 0 4px; }
.page-header p  { color: #C9A84C; font-size: 0.85rem; margin: 0; }

.stat-row { display: flex; gap: 12px; margin: 16px 0; }
.stat-box {
    flex: 1; background: #fff; border-radius: 10px;
    padding: 16px; text-align: center; border: 1px solid #E8E4DB;
}
.stat-num   { font-size: 2rem; font-weight: 700; color: #1B3A6B; font-family: 'DM Mono', monospace; line-height: 1; }
.stat-label { font-size: 0.72rem; color: #999; margin-top: 4px; text-transform: uppercase; letter-spacing: 0.5px; }

.worker-row {
    display: flex; align-items: center; border-radius: 8px;
    padding: 9px 14px; margin: 3px 0; font-size: 0.86rem;
    border-left: 4px solid transparent;
}
.worker-row.pass { background: #F0FFF4; border-left-color: #2E7D32; }
.worker-row.prog { background: #FFF8F0; border-left-color: #E65100; }
.worker-name  { font-weight: 600; flex: 1; color: #1a1a1a; }
.worker-email { font-size: 0.78rem; color: #888; margin-left: 6px; }
.worker-ssn   { font-size: 0.76rem; color: #bbb; margin-left: 10px; font-family: 'DM Mono', monospace; }
.badge        { font-size: 0.72rem; font-weight: 700; padding: 2px 9px; border-radius: 20px; margin-left: 10px; white-space: nowrap; }
.badge-pass   { background: #C8E6C9; color: #1B5E20; }
.badge-prog   { background: #FFE0B2; color: #BF360C; }

.section-label {
    font-size: 0.72rem; font-weight: 700; text-transform: uppercase;
    letter-spacing: 1px; color: #999; margin: 20px 0 8px;
}
.upload-hint {
    background: #fff; border: 2px dashed #C9A84C; border-radius: 12px;
    padding: 18px 22px; text-align: center; color: #777;
    font-size: 0.84rem; margin-bottom: 8px;
}
.match-chip {
    display: inline-block; background: #E8F5E9; color: #2E7D32;
    border-radius: 20px; padding: 2px 10px;
    font-size: 0.76rem; font-weight: 600; margin: 3px 4px 3px 0;
}
.nomatch-chip {
    display: inline-block; background: #FFF3E0; color: #E65100;
    border-radius: 20px; padding: 2px 10px;
    font-size: 0.76rem; font-weight: 600; margin: 3px 4px 3px 0;
}
.info-card {
    background: #fff; border: 1px solid #E8E4DB; border-radius: 10px;
    padding: 16px 20px; margin-bottom: 14px;
}
.info-card h4 { margin: 0 0 6px; color: #1B3A6B; font-size: 0.95rem; }
.info-card p  { margin: 0; color: #666; font-size: 0.83rem; line-height: 1.6; }

/* Transcript preview */
.preview-wrap { font-family: 'DM Sans', Arial, sans-serif; border: 1px solid #ddd; border-radius: 10px; overflow: hidden; box-shadow: 0 4px 20px rgba(0,0,0,0.08); }
.preview-hdr  { background: #1B3A6B; padding: 22px 26px; text-align: center; }
.preview-hdr h3 { color: #fff; font-size: 1.1rem; font-weight: 800; margin: 0 0 2px; letter-spacing: 2px; }
.preview-hdr p  { color: #C9A84C; font-size: 0.78rem; margin: 0; }
.preview-meta { display: grid; grid-template-columns: 1.4fr 1.8fr 1fr; border-bottom: 1px solid #e0e0e0; }
.preview-cell { padding: 11px 16px; border-right: 1px solid #e0e0e0; }
.preview-cell:last-child { border-right: none; }
.preview-cell .lbl { font-size: 0.65rem; font-weight: 700; color: #aaa; text-transform: uppercase; letter-spacing: 0.8px; margin-bottom: 3px; }
.preview-cell .val { font-size: 0.88rem; color: #222; font-weight: 600; word-break: break-all; }
.preview-sec-hdr { background: #1B3A6B; color: #fff; font-size: 0.72rem; font-weight: 700; letter-spacing: 1.5px; padding: 7px 16px; text-transform: uppercase; }
.preview-course-row { display: grid; grid-template-columns: 2fr 0.85fr 1.1fr 1.2fr; padding: 9px 16px; border-bottom: 1px solid #eee; align-items: center; font-size: 0.83rem; }
.preview-course-row.pass-row { background: #F0FFF4; border-left: 3px solid #2E7D32; }
.preview-course-row.prog-row { background: #FFF8F0; border-left: 3px solid #E65100; }
.cname { font-weight: 600; color: #1a1a1a; }
.cpass { color: #2E7D32; font-weight: 700; font-size: 0.78rem; }
.cprog { color: #E65100; font-weight: 700; font-size: 0.78rem; }
.cdate { color: #666; font-size: 0.76rem; line-height: 1.4; }
.preview-footer { text-align: center; padding: 10px; font-size: 0.72rem; color: #bbb; border-top: 1px solid #eee; font-style: italic; background: #fafafa; }
</style>
""", unsafe_allow_html=True)


# ── Navigation items ──────────────────────────────────────────────────────────
NAV_ITEMS = [
    ("📤", "Upload & Process"),
    ("👥", "Preview Workers"),
    ("📄", "Generate PDFs"),
    ("🔍", "Batch Lookup"),
    ("✏️", "Export CSV"),
    ("🏆", "LIUNA Certificates"),
    ("⚙️", "Settings"),
]

# ── Session state defaults ────────────────────────────────────────────────────
for key, default in [
    ("people",    []),
    ("courses",   []),
    ("use_color", True),
]:
    if key not in st.session_state:
        st.session_state[key] = default


def require_data() -> bool:
    """Show a warning and return False when no transcript data has been loaded."""
    if not st.session_state.people:
        st.warning("⬆️ No data loaded yet — go to **Upload & Process** first.")
        return False
    return True


# ── Sidebar ───────────────────────────────────────────────────────────────────
with st.sidebar:
    st.markdown("""
    <div class="sidebar-logo">
        <h1>📋 Transcript Generator</h1>
        <p>Construction Workforce Safety</p>
    </div>
    <div class="nav-section-label">Navigation</div>
    """, unsafe_allow_html=True)

    page = st.radio(
        "nav",
        [label for _, label in NAV_ITEMS],
        label_visibility="collapsed",
        key="nav_radio",
    )

    # Render nav items with active highlight
    nav_html = "".join(
        f'<div class="nav-item {"active" if page == label else ""}">{icon}&nbsp;&nbsp;{label}</div>'
        for icon, label in NAV_ITEMS
    )
    st.markdown(nav_html, unsafe_allow_html=True)

    # Loaded-data summary
    if st.session_state.people:
        ppl      = st.session_state.people
        crs      = st.session_state.courses
        passed_n = sum(1 for p in ppl if any("pass" in c["status"].lower() for c in p["courses"]))
        st.markdown(f"""
        <div style="padding:16px 12px 0;">
          <div style="background:rgba(255,255,255,0.08);border-radius:10px;padding:14px 16px;">
            <div style="font-size:0.62rem;color:rgba(255,255,255,0.4);text-transform:uppercase;letter-spacing:1px;margin-bottom:10px;">Loaded Data</div>
            <div style="display:flex;justify-content:space-between;margin-bottom:6px;">
              <span style="color:rgba(255,255,255,0.6);font-size:0.8rem;">Workers</span>
              <span style="color:#fff;font-weight:700;font-family:'DM Mono',monospace;">{len(ppl)}</span>
            </div>
            <div style="display:flex;justify-content:space-between;margin-bottom:6px;">
              <span style="color:rgba(255,255,255,0.6);font-size:0.8rem;">Courses</span>
              <span style="color:#fff;font-weight:700;font-family:'DM Mono',monospace;">{len(crs)}</span>
            </div>
            <div style="display:flex;justify-content:space-between;">
              <span style="color:rgba(255,255,255,0.6);font-size:0.8rem;">Passed</span>
              <span style="color:#C9A84C;font-weight:700;font-family:'DM Mono',monospace;">{passed_n}</span>
            </div>
          </div>
        </div>
        """, unsafe_allow_html=True)


# ── Preview modal ─────────────────────────────────────────────────────────────
@st.dialog("Transcript Preview", width="large")
def show_preview_modal(person: dict, use_color: bool) -> None:
    st.markdown(build_preview_html(person), unsafe_allow_html=True)
    st.markdown("")
    pdf_bytes = build_person_pdf(person, use_color=use_color)
    safe_name = re.sub(r"[^\w\-]", "_", person["name"] or "transcript")
    st.download_button(
        "⬇️ Download this transcript as PDF",
        data=pdf_bytes,
        file_name=f"{safe_name}.pdf",
        mime="application/pdf",
        use_container_width=True,
        type="primary",
    )


# ── Worker row renderer ───────────────────────────────────────────────────────
def render_worker_row(person: dict, use_color: bool, key_prefix: str = "") -> None:
    """Render one worker row with an optional 👁 preview button."""
    is_pass   = any("pass" in c["status"].lower() for c in person["courses"])
    row_cls   = "pass" if is_pass else "prog"
    badge_cls = "badge-pass" if is_pass else "badge-prog"
    badge_txt = "PASSED"      if is_pass else "IN PROGRESS"
    ssn_part  = (
        f'<span class="worker-ssn">· ••••{person["ssn4"]}</span>'
        if person.get("ssn4") else ""
    )

    col_card, col_btn = st.columns([7, 1])
    with col_card:
        st.markdown(f"""
        <div class="worker-row {row_cls}">
            <span class="worker-name">{person['name']}</span>
            <span class="worker-email">{person['email']}</span>
            {ssn_part}
            <span class="badge {badge_cls}">{badge_txt}</span>
        </div>""", unsafe_allow_html=True)
    with col_btn:
        if st.button("👁", key=f"{key_prefix}prev_{person['email']}",
                     use_container_width=True, help=f"Preview {person['name']}"):
            show_preview_modal(person, use_color)


# ══════════════════════════════════════════════════════════════════════════════
# ── Page: Upload & Process ────────────────────────────────────────────────────
# ══════════════════════════════════════════════════════════════════════════════
if page == "Upload & Process":
    st.markdown("""
    <div class="page-header">
        <h2>📤 Upload &amp; Process</h2>
        <p>Drop one or more CSV exports — each file is treated as a separate course</p>
    </div>""", unsafe_allow_html=True)

    st.markdown(
        '<div class="upload-hint">Supported columns: Name · Email · Course result · '
        'Finished · Started · Last 4 digits of Social</div>',
        unsafe_allow_html=True,
    )

    uploaded_files = st.file_uploader(
        "Upload CSV files", type=["csv"],
        accept_multiple_files=True, label_visibility="collapsed",
    )

    if uploaded_files:
        with st.spinner("Processing files…"):
            people, courses = process_files(uploaded_files)
            st.session_state.people  = people
            st.session_state.courses = courses

        passed = sum(1 for p in people if any("pass" in c["status"].lower() for c in p["courses"]))
        st.markdown(f"""
        <div class="stat-row">
            <div class="stat-box"><div class="stat-num">{len(people)}</div><div class="stat-label">Workers</div></div>
            <div class="stat-box"><div class="stat-num">{len(courses)}</div><div class="stat-label">Courses</div></div>
            <div class="stat-box"><div class="stat-num">{passed}</div><div class="stat-label">Passed</div></div>
            <div class="stat-box"><div class="stat-num">{len(people) - passed}</div><div class="stat-label">In Progress</div></div>
        </div>""", unsafe_allow_html=True)

        st.success(f"✅ Loaded {len(uploaded_files)} file(s). Use the sidebar to navigate.")

        st.markdown('<div class="section-label">Detected Courses</div>', unsafe_allow_html=True)
        for i, c in enumerate(courses, 1):
            st.markdown(f"**{i}.** {c}")
    else:
        st.markdown("""
        <div class="info-card">
            <h4>How it works</h4>
            <p>
                1. Upload one or more CSV files from your training platform.<br>
                2. Each file is auto-detected as a course from its filename or columns.<br>
                3. Workers are matched across files by email address.<br>
                4. Navigate via sidebar to preview, generate PDFs, batch lookup, or export.
            </p>
        </div>
        <div class="info-card">
            <h4>Course keyword detection</h4>
            <p>
                <b>asbestos</b> → Asbestos Awareness &nbsp;·&nbsp;
                <b>covid</b> → COVID-19 for the Construction Workforce<br>
                <b>lead</b> → Lead Awareness Worker &nbsp;·&nbsp;
                <b>hazard</b> → Hazard Communication
            </p>
        </div>""", unsafe_allow_html=True)


# ══════════════════════════════════════════════════════════════════════════════
# ── Page: Preview Workers ─────────────────────────────────────────────────────
# ══════════════════════════════════════════════════════════════════════════════
elif page == "Preview Workers":
    st.markdown("""
    <div class="page-header">
        <h2>👥 Preview Workers</h2>
        <p>Green rows = passed · Orange rows = in progress · Click 👁 to preview transcript</p>
    </div>""", unsafe_allow_html=True)

    if not require_data():
        st.stop()

    people    = st.session_state.people
    use_color = st.session_state.use_color

    col_search, col_filter = st.columns([3, 1])
    with col_search:
        search_q = st.text_input("Search", placeholder="🔎  Search by name or email…",
                                 label_visibility="collapsed")
    with col_filter:
        status_filter = st.selectbox("Status", ["All", "Passed", "In Progress"],
                                     label_visibility="collapsed")

    filtered = people
    if search_q:
        q        = search_q.lower()
        filtered = [p for p in filtered if q in p["name"].lower() or q in p["email"].lower()]
    if status_filter == "Passed":
        filtered = [p for p in filtered if any("pass" in c["status"].lower() for c in p["courses"])]
    elif status_filter == "In Progress":
        filtered = [p for p in filtered if not any("pass" in c["status"].lower() for c in p["courses"])]

    st.markdown(f'<div class="section-label">{len(filtered)} worker(s) shown</div>',
                unsafe_allow_html=True)

    for person in filtered:
        render_worker_row(person, use_color, key_prefix="wp_")


# ══════════════════════════════════════════════════════════════════════════════
# ── Page: Generate PDFs ───────────────────────────────────────────────────────
# ══════════════════════════════════════════════════════════════════════════════
elif page == "Generate PDFs":
    st.markdown("""
    <div class="page-header">
        <h2>📄 Generate PDFs</h2>
        <p>Download transcripts for all workers — merged or as individual files in a ZIP</p>
    </div>""", unsafe_allow_html=True)

    if not require_data():
        st.stop()

    people = st.session_state.people
    total  = len(people)

    st.markdown('<div class="section-label">PDF Color Mode</div>', unsafe_allow_html=True)
    color_toggle = st.checkbox(
        "🖨️ Color PDFs (uncheck for grayscale / print-friendly)",
        value=st.session_state.use_color,
    )
    st.session_state.use_color = color_toggle

    st.markdown('<div class="section-label">Download Options</div>', unsafe_allow_html=True)
    col1, col2 = st.columns(2)

    with col1:
        st.markdown("""<div class="info-card"><h4>📄 Merged PDF</h4>
        <p>All workers in one multi-page PDF, sorted alphabetically.</p></div>""",
                    unsafe_allow_html=True)
        if st.button(f"Build Merged PDF ({total} workers)", use_container_width=True, type="primary"):
            with st.spinner(f"Building {total} transcripts…"):
                merged = merge_pdfs([build_person_pdf(p, use_color=color_toggle) for p in people])
            st.download_button(
                "⬇️ Download All_Transcripts.pdf",
                data=merged, file_name="All_Transcripts.pdf",
                mime="application/pdf", use_container_width=True,
            )

    with col2:
        st.markdown("""<div class="info-card"><h4>🗂 Individual ZIP</h4>
        <p>One PDF per worker, named by employee, packaged into a ZIP.</p></div>""",
                    unsafe_allow_html=True)
        if st.button("Package Individual PDFs (ZIP)", use_container_width=True):
            with st.spinner("Packaging…"):
                zip_bytes = build_zip(people, use_color=color_toggle)
            st.download_button(
                "⬇️ Download Transcripts.zip",
                data=zip_bytes, file_name="Transcripts.zip",
                mime="application/zip", use_container_width=True,
            )


# ══════════════════════════════════════════════════════════════════════════════
# ── Page: Batch Lookup ────────────────────────────────────────────────────────
# ══════════════════════════════════════════════════════════════════════════════
elif page == "Batch Lookup":
    st.markdown("""
    <div class="page-header">
        <h2>🔍 Batch Lookup</h2>
        <p>Paste or upload a list of emails — only matched workers get transcripts</p>
    </div>""", unsafe_allow_html=True)

    if not require_data():
        st.stop()

    people          = st.session_state.people
    people_by_email = {p["email"].lower(): p for p in people}
    use_color       = st.session_state.use_color

    tab1, tab2   = st.tabs(["✏️ Paste Emails", "📁 Upload File"])
    batch_emails = []

    with tab1:
        raw_input = st.text_area(
            "Emails", height=160,
            placeholder="jane.doe@example.com\njohn.smith@example.com\n…",
            label_visibility="collapsed",
        )
        if raw_input.strip():
            batch_emails = parse_email_list(raw_input)
            if batch_emails:
                st.caption(f"Parsed **{len(batch_emails)}** valid email(s).")

    with tab2:
        email_file = st.file_uploader("Upload .txt or .csv", type=["txt", "csv"],
                                       key="batch_email_file")
        if email_file:
            batch_emails = parse_email_list(email_file.read().decode("utf-8", errors="ignore"))
            st.caption(f"Parsed **{len(batch_emails)}** valid email(s).")

    if batch_emails:
        matched   = [people_by_email[e] for e in batch_emails if e in people_by_email]
        unmatched = [e for e in batch_emails if e not in people_by_email]

        chips = (
            "".join(f'<span class="match-chip">✓ {p["email"]}</span>' for p in matched) +
            "".join(f'<span class="nomatch-chip">✗ {e}</span>'         for e in unmatched)
        )
        st.markdown(f"""
        <div style="margin:8px 0 14px;">
            <strong style="font-size:0.85rem;color:#1B3A6B;">
                {len(matched)} matched · {len(unmatched)} not found
            </strong><br><br>{chips}
        </div>""", unsafe_allow_html=True)

        if unmatched:
            with st.expander(f"⚠️ {len(unmatched)} email(s) not found"):
                for e in unmatched:
                    st.markdown(f"- `{e}`")

        if matched:
            st.markdown('<div class="section-label">Matched Workers</div>', unsafe_allow_html=True)
            for person in matched:
                render_worker_row(person, use_color, key_prefix="bl_")

            st.markdown('<div class="section-label">Download Batch Results</div>',
                        unsafe_allow_html=True)
            bcol1, bcol2 = st.columns(2)

            with bcol1:
                if st.button(f"📄 Merged PDF ({len(matched)} workers)",
                              use_container_width=True, type="primary"):
                    with st.spinner("Building transcripts…"):
                        batch_merged = merge_pdfs(
                            [build_person_pdf(p, use_color=use_color) for p in matched]
                        )
                    st.download_button(
                        "⬇️ Download Batch_Transcripts.pdf",
                        data=batch_merged, file_name="Batch_Transcripts.pdf",
                        mime="application/pdf", use_container_width=True,
                    )

            with bcol2:
                if st.button(f"🗂 Individual ZIP ({len(matched)} PDFs)", use_container_width=True):
                    with st.spinner("Packaging…"):
                        zip_bytes = build_zip(matched, use_color=use_color)
                    st.download_button(
                        "⬇️ Download Batch_Transcripts.zip",
                        data=zip_bytes, file_name="Batch_Transcripts.zip",
                        mime="application/zip", use_container_width=True,
                    )
        else:
            st.warning("None of the entered emails matched any workers in the uploaded CSVs.")


# ══════════════════════════════════════════════════════════════════════════════
# ── Page: Export CSV ──────────────────────────────────────────────────────────
# ══════════════════════════════════════════════════════════════════════════════
elif page == "Export CSV":
    st.markdown("""
    <div class="page-header">
        <h2>✏️ Export CSV</h2>
        <p>A clean, fully-structured export — preview below before downloading</p>
    </div>""", unsafe_allow_html=True)

    if not require_data():
        st.stop()

    people = st.session_state.people

    st.markdown("""<div class="info-card"><h4>Exported Fields</h4>
    <p><b>Name</b> · <b>Email</b> · <b>SSN Last 4</b> · <b>Course</b> · <b>Status</b> ·
    <b>Started Date</b> · <b>Completion Date</b> · <b>Passed</b> (Yes / No)</p>
    </div>""", unsafe_allow_html=True)

    preview_rows = [
        {
            "Name":            p["name"],
            "Email":           p["email"],
            "SSN Last 4":      p.get("ssn4") or "",
            "Course":          c["course"],
            "Status":          c["status"],
            "Started Date":    c.get("started_date") or "",
            "Completion Date": c.get("completion_date") or "",
            "Passed":          "Yes" if "pass" in c["status"].lower() else "No",
        }
        for p in people
        for c in p["courses"]
    ]

    st.markdown('<div class="section-label">Data Preview</div>', unsafe_allow_html=True)
    st.dataframe(pd.DataFrame(preview_rows), use_container_width=True, height=340)

    total_rows = len(preview_rows)
    st.markdown(
        f'<div class="section-label">{total_rows} rows · {len(people)} workers · '
        f'{len(st.session_state.courses)} courses</div>',
        unsafe_allow_html=True,
    )

    st.download_button(
        "⬇️ Download combined.csv",
        data=build_clean_csv(people),
        file_name="combined.csv",
        mime="text/csv",
        use_container_width=True,
        type="primary",
    )


# ══════════════════════════════════════════════════════════════════════════════
# ── Page: LIUNA Certificates ──────────────────────────────────────────────────
# ══════════════════════════════════════════════════════════════════════════════
elif page == "LIUNA Certificates":
    st.markdown("""
    <div class="page-header">
        <h2>🏆 LIUNA Certificates</h2>
        <p>Upload a LIUNA class-information CSV and generate landscape completion certificates</p>
    </div>""", unsafe_allow_html=True)

    st.markdown("""
    <div class="info-card">
        <h4>CSV Format</h4>
        <p>
            No header row. Columns are read by position:<br>
            <b>Col 2</b> = Class name &nbsp;·&nbsp;
            <b>Col 7</b> = Hours &nbsp;·&nbsp;
            <b>Col 10</b> = Completion date &nbsp;·&nbsp;
            <b>Col 11</b> = Member ID &nbsp;·&nbsp;
            <b>Col 12</b> = Last name &nbsp;·&nbsp;
            <b>Col 13</b> = First name
        </p>
    </div>""", unsafe_allow_html=True)

    liuna_file = st.file_uploader(
        "Upload LIUNA CSV", type=["csv"], key="liuna_csv",
        label_visibility="collapsed",
    )

    st.markdown('<div class="section-label">Organization Details</div>', unsafe_allow_html=True)
    col_a, col_b = st.columns(2)
    with col_a:
        org_name  = st.text_input("Organization name",  value="LIUNA Training of Michigan")
        org_addr  = st.text_input("Street address",     value="11155 Beardslee Road")
        org_city  = st.text_input("City, State ZIP",    value="Perry, MI 48872")
    with col_b:
        org_phone = st.text_input("Phone",              value="(517) 625-4919")
        dir_name  = st.text_input("Director full name", value="")
        dir_title = st.text_input("Director title",     value="Director")

    if liuna_file:
        raw_text = liuna_file.read().decode("utf-8-sig", errors="ignore")
        try:
            groups = load_csv_from_text(raw_text)
        except Exception as exc:
            st.error(f"Failed to parse CSV: {exc}")
            st.stop()

        total_students = len(groups)
        total_certs    = sum(len(g["certs"]) for g in groups.values())

        st.markdown(f"""
        <div class="stat-row">
            <div class="stat-box"><div class="stat-num">{total_students}</div><div class="stat-label">Students</div></div>
            <div class="stat-box"><div class="stat-num">{total_certs}</div><div class="stat-label">Certificates</div></div>
        </div>""", unsafe_allow_html=True)

        with st.expander("👥 Preview students"):
            for mid, group in groups.items():
                cert_count = len(group["certs"])
                st.markdown(
                    f"**{group['name']}** &nbsp;<span style='color:#999;font-size:0.8em'>"
                    f"· {mid} · {cert_count} cert{'s' if cert_count > 1 else ''}</span>",
                    unsafe_allow_html=True,
                )

        st.markdown('<div class="section-label">Download Certificates</div>', unsafe_allow_html=True)
        lcol1, lcol2 = st.columns(2)

        org_kwargs = dict(
            org_name=org_name, org_addr=org_addr,
            org_city=org_city,  org_phone=org_phone,
            dir_name=dir_name,  dir_title=dir_title,
        )

        with lcol1:
            st.markdown("""<div class="info-card"><h4>📄 Merged PDF</h4>
            <p>All students in one PDF, one certificate per page.</p></div>""",
                        unsafe_allow_html=True)
            if st.button(f"Build Merged PDF ({total_certs} certificates)",
                          use_container_width=True, type="primary"):
                with st.spinner("Generating certificates…"):
                    merged_bytes = generate_pdfs_merged(groups, **org_kwargs)
                st.download_button(
                    "⬇️ Download LIUNA_Certificates.pdf",
                    data=merged_bytes, file_name="LIUNA_Certificates.pdf",
                    mime="application/pdf", use_container_width=True,
                )

        with lcol2:
            st.markdown("""<div class="info-card"><h4>🗂 Individual ZIP</h4>
            <p>One PDF per student (multi-page if multiple courses), packaged in a ZIP.</p></div>""",
                        unsafe_allow_html=True)
            if st.button(f"Package Individual PDFs ({total_students} students)",
                          use_container_width=True):
                with st.spinner("Packaging…"):
                    zip_bytes = generate_pdfs_to_zip(groups, **org_kwargs)
                st.download_button(
                    "⬇️ Download LIUNA_Certificates.zip",
                    data=zip_bytes, file_name="LIUNA_Certificates.zip",
                    mime="application/zip", use_container_width=True,
                )
    else:
        st.markdown("""
        <div class="upload-hint">⬆️ Upload a LIUNA class-information CSV above to get started</div>
        """, unsafe_allow_html=True)


# ══════════════════════════════════════════════════════════════════════════════
# ── Page: Settings ────────────────────────────────────────────────────────────
# ══════════════════════════════════════════════════════════════════════════════
elif page == "Settings":
    st.markdown("""
    <div class="page-header">
        <h2>⚙️ Settings</h2>
        <p>PDF output options, course keyword detection, and app information</p>
    </div>""", unsafe_allow_html=True)

    st.markdown('<div class="section-label">PDF Color Mode</div>', unsafe_allow_html=True)
    use_color = st.checkbox(
        "🖨️ Color PDFs (uncheck for grayscale / print-friendly)",
        value=st.session_state.use_color,
    )
    st.session_state.use_color = use_color

    st.markdown('<div class="section-label">Course Keyword Detection</div>', unsafe_allow_html=True)
    st.markdown("""<div class="info-card"><h4>How course names are auto-detected</h4>
    <p>Keywords are matched against the uploaded filename and column headers.
    If no keyword matches, the filename is used as the course name.</p>
    </div>""", unsafe_allow_html=True)

    kw_df = pd.DataFrame([
        {"Keyword (filename / columns)": k, "Detected Course Name": v}
        for k, v in COURSE_KEYWORDS.items()
    ])
    st.dataframe(kw_df, use_container_width=True, hide_index=True)

    st.markdown('<div class="section-label">About</div>', unsafe_allow_html=True)
    st.markdown("""<div class="info-card"><h4>Training &amp; Certificate Generator</h4>
    <p>
        Built for Construction Workforce Safety Training.<br>
        Upload CSV exports → auto-detect courses → generate printable PDF transcripts.<br>
        Workers are matched across multiple course files by email address.<br>
        LIUNA certificates are generated separately from the class-information CSV.<br><br>
        <b>Requires:</b> Streamlit 1.32+ · reportlab · pypdf · pandas
    </p></div>""", unsafe_allow_html=True)
