"""Convert Scoring_Model_Methodology.md to a clean PDF using ReportLab."""
import re
from reportlab.lib.pagesizes import letter
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib.units import inch
from reportlab.lib import colors
from reportlab.platypus import (
    SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle,
    HRFlowable, Preformatted
)
from reportlab.lib.enums import TA_LEFT, TA_CENTER

MD_PATH = "/Users/careycao/VEIR Engine Lab/Scoring_Model_Methodology.md"
OUT_PATH = "/Users/careycao/VEIR Engine Lab/output/Scoring_Model_Methodology.pdf"

# ── Styles ──────────────────────────────────────────────────────────────────
base = getSampleStyleSheet()

def style(name, parent="Normal", **kw):
    s = ParagraphStyle(name, parent=base[parent], **kw)
    return s

S = {
    "h1": style("H1", "Heading1", fontSize=18, spaceAfter=6, textColor=colors.HexColor("#1a1a1a")),
    "h2": style("H2", "Heading2", fontSize=14, spaceBefore=16, spaceAfter=4, textColor=colors.HexColor("#1a1a1a")),
    "h3": style("H3", "Heading3", fontSize=12, spaceBefore=12, spaceAfter=3, textColor=colors.HexColor("#333333")),
    "h4": style("H4", "Heading4", fontSize=11, spaceBefore=8, spaceAfter=2, textColor=colors.HexColor("#444444"), italic=True),
    "body": style("Body", "Normal", fontSize=10, leading=15, spaceAfter=4),
    "code": style("Code", "Code", fontSize=9, leading=13, backColor=colors.HexColor("#f5f5f5"),
                  leftIndent=10, rightIndent=10, spaceBefore=4, spaceAfter=6),
    "bullet": style("Bullet", "Normal", fontSize=10, leading=14, leftIndent=18, bulletIndent=6, spaceAfter=2),
}

TABLE_STYLE = TableStyle([
    ("BACKGROUND",  (0,0), (-1,0),  colors.HexColor("#e8e8e8")),
    ("TEXTCOLOR",   (0,0), (-1,0),  colors.HexColor("#1a1a1a")),
    ("FONTNAME",    (0,0), (-1,0),  "Helvetica-Bold"),
    ("FONTSIZE",    (0,0), (-1,-1), 9),
    ("ROWBACKGROUNDS", (0,1), (-1,-1), [colors.white, colors.HexColor("#fafafa")]),
    ("GRID",        (0,0), (-1,-1), 0.5, colors.HexColor("#cccccc")),
    ("LEFTPADDING", (0,0), (-1,-1), 6),
    ("RIGHTPADDING",(0,0), (-1,-1), 6),
    ("TOPPADDING",  (0,0), (-1,-1), 4),
    ("BOTTOMPADDING",(0,0),(-1,-1), 4),
    ("VALIGN",      (0,0), (-1,-1), "TOP"),
    ("WORDWRAP",    (0,0), (-1,-1), True),
])

# ── Helpers ──────────────────────────────────────────────────────────────────
def escape(text):
    return text.replace("&","&amp;").replace("<","&lt;").replace(">","&gt;")

def inline_fmt(text):
    """Convert **bold** and `code` to ReportLab XML tags."""
    text = escape(text)
    text = re.sub(r"\*\*(.+?)\*\*", r"<b>\1</b>", text)
    text = re.sub(r"`(.+?)`", r'<font name="Courier" size="9">\1</font>', text)
    return text

# ── Parser ───────────────────────────────────────────────────────────────────
def parse_md(path):
    with open(path) as f:
        lines = f.readlines()

    story = []
    i = 0
    while i < len(lines):
        raw = lines[i].rstrip("\n")

        # HR
        if re.match(r"^---+$", raw.strip()):
            story.append(HRFlowable(width="100%", thickness=0.5, color=colors.HexColor("#cccccc")))
            story.append(Spacer(1, 4))
            i += 1; continue

        # Headings
        m = re.match(r"^(#{1,4})\s+(.*)", raw)
        if m:
            lvl = len(m.group(1))
            text = inline_fmt(m.group(2))
            key = f"h{min(lvl,4)}"
            story.append(Paragraph(text, S[key]))
            if lvl == 1:
                story.append(HRFlowable(width="100%", thickness=1.2, color=colors.HexColor("#333333")))
            i += 1; continue

        # Fenced code block
        if raw.strip().startswith("```"):
            code_lines = []
            i += 1
            while i < len(lines) and not lines[i].strip().startswith("```"):
                code_lines.append(lines[i].rstrip("\n"))
                i += 1
            i += 1  # skip closing ```
            story.append(Preformatted("\n".join(code_lines), S["code"]))
            story.append(Spacer(1, 4))
            continue

        # Table
        if "|" in raw and raw.strip().startswith("|"):
            table_lines = []
            while i < len(lines) and "|" in lines[i] and lines[i].strip().startswith("|"):
                table_lines.append(lines[i].rstrip("\n"))
                i += 1
            # filter separator rows
            rows = []
            for tl in table_lines:
                if re.match(r"^\|[-| :]+\|$", tl.strip()):
                    continue
                cells = [c.strip() for c in tl.strip().strip("|").split("|")]
                rows.append(cells)
            if rows:
                # Convert cell text with inline formatting (as plain text for Table)
                def cell(txt):
                    txt = txt.replace("**","").replace("`","")
                    return txt
                data = [[cell(c) for c in row] for row in rows]
                col_count = max(len(r) for r in data)
                # pad rows
                data = [r + [""]*(col_count - len(r)) for r in data]
                avail = 6.5 * inch
                col_w = avail / col_count
                t = Table(data, colWidths=[col_w]*col_count, repeatRows=1)
                t.setStyle(TABLE_STYLE)
                story.append(t)
                story.append(Spacer(1, 8))
            continue

        # Bullet
        m = re.match(r"^(\s*)[*\-]\s+(.*)", raw)
        if m:
            text = inline_fmt(m.group(2))
            indent = len(m.group(1))
            story.append(Paragraph(f"• {text}", S["bullet"]))
            i += 1; continue

        # Blank line
        if raw.strip() == "":
            story.append(Spacer(1, 4))
            i += 1; continue

        # Normal paragraph
        story.append(Paragraph(inline_fmt(raw.strip()), S["body"]))
        i += 1

    return story

# ── Build PDF ────────────────────────────────────────────────────────────────
doc = SimpleDocTemplate(
    OUT_PATH,
    pagesize=letter,
    leftMargin=0.9*inch, rightMargin=0.9*inch,
    topMargin=0.9*inch,  bottomMargin=0.9*inch,
    title="VEIR GTM Ranking Model — Methodology & Weight Reference",
    author="Engine Lab Team",
)
doc.build(parse_md(MD_PATH))
print(f"PDF saved: {OUT_PATH}")
