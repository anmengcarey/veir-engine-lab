"""
Engine Lab PDF Parser
=====================
Parses two types of PDFs:
  - "Engine Lab #.pdf"        → index/project-list files
  - "Engine Lab Report #.pdf" → detailed project report files

Outputs a merged CSV: engine_lab_output.csv
"""

import re
import os
import glob
import pandas as pd
import pdfplumber

DATA_DIR = os.path.join(os.path.dirname(__file__), "data")
OUTPUT_CSV  = os.path.join(os.path.dirname(__file__), "engine_lab_output.csv")
OUTPUT_XLSX = os.path.join(os.path.dirname(__file__), "engine_lab_output.xlsx")

# Pattern to detect an "industry" row (always starts a new project block)
INDUSTRY_RE = re.compile(r"^Industrial\s+Manufacturing$", re.IGNORECASE)
# Pattern to detect a date row  (DD-Mon-YYYY)
DATE_RE = re.compile(r"^\d{2}-[A-Za-z]{3}-\d{4}$")
# Pattern for Project ID (6-9 digit number starting with 3)
PROJECT_ID_RE = re.compile(r"^3\d{8}$")
# Pattern for Umbrella ID (4-6 digit number, smaller than project IDs)
UMBRELLA_ID_RE = re.compile(r"^\d{4,6}$")
# Pattern for TIV (starts with $)
TIV_RE = re.compile(r"^\$[\d,]+$")
# Pattern for count (1-3 digit number used in umbrella count)
COUNT_RE = re.compile(r"^\d{1,3}$")


def clean(text):
    if text is None:
        return ""
    return " ".join(str(text).split())


def strip_dollar(text):
    return clean(text).replace("$", "").replace(",", "")


# ---------------------------------------------------------------------------
# Parser 1 -- "Engine Lab #.pdf"  (index files)
# ---------------------------------------------------------------------------
#
# Each project occupies exactly 3 or 4 data rows (separated by blank rows):
#   Row A: col[1]=Industry          col[2]=Project Name   col[3]=TIV($)
#   Row B: col[1]=Date              col[2]=Owner Name     col[3]=City/State/Country
#   Row C: col[1]=Project ID (9dig) col[2]=Plant Name     col[3]=Status
#   Row D: col[1]=Umbrella ID       col[2]=Umbrella Name  col[3]=Count   (optional)
#
# Page breaks cause orphan rows at the top of the next page that belong to
# the previous project's Row D (umbrella row). We handle this by scanning
# strictly for INDUSTRY rows as block starters.

def _is_industry(val):
    return bool(INDUSTRY_RE.match(val))

def _is_date(val):
    return bool(DATE_RE.match(val))

def _is_project_id(val):
    return bool(PROJECT_ID_RE.match(val))

def _is_umbrella_id(val):
    # 4-6 digit number AND not a project ID
    return bool(UMBRELLA_ID_RE.match(val)) and not bool(PROJECT_ID_RE.match(val))


def parse_index_file(pdf_path):
    """Return list of dicts, one per project, from an index PDF."""

    # Collect all data rows from all pages
    all_data_rows = []

    with pdfplumber.open(pdf_path) as pdf:
        for page in pdf.pages:
            tables = page.extract_tables()
            if not tables:
                continue
            for table in tables:
                for row in table:
                    r = [clean(c) for c in row]
                    # Skip rows where every non-first column is empty
                    if all(v == "" for v in r[1:]):
                        continue
                    col1 = r[1] if len(r) > 1 else ""
                    # Skip known header strings
                    if col1 in ("Industry/Date/Project ID/Umbrella Project ID",
                                "Project Name/Owner Name/Plant Name/Umbrella Project Name",
                                "TIV(USD)/City,State,Country/Status/Umbrella Project Count"):
                        continue
                    # Skip PDF title rows
                    if re.match(r"Engine Lab \d+", col1) or col1 == "PROJECT INDEX":
                        continue
                    all_data_rows.append(r)

    # Parse flat list into project blocks.
    # A new project always starts with an INDUSTRY row.
    records = []
    i = 0
    n = len(all_data_rows)

    while i < n:
        row = all_data_rows[i]
        col1 = row[1] if len(row) > 1 else ""

        # A project block starts with an industry row
        if not _is_industry(col1):
            i += 1
            continue

        # --- Row A: Industry / Project Name / TIV ---
        industry = col1
        project_name = row[2] if len(row) > 2 else ""
        tiv_raw = row[3] if len(row) > 3 else ""
        tiv = strip_dollar(tiv_raw)
        i += 1

        # Skip blank rows
        while i < n and all_data_rows[i][1] == "":
            i += 1

        # --- Row B: Date / Owner Name / Location ---
        date = owner = location = ""
        if i < n and _is_date(all_data_rows[i][1]):
            b = all_data_rows[i]
            date = b[1]
            owner = b[2] if len(b) > 2 else ""
            location = b[3] if len(b) > 3 else ""
            i += 1
        else:
            # Unexpected layout -- skip this block
            continue

        # Skip blank rows
        while i < n and all_data_rows[i][1] == "":
            i += 1

        # --- Row C: Project ID / Plant Name / Status ---
        project_id = plant_name = status = ""
        if i < n and _is_project_id(all_data_rows[i][1]):
            c = all_data_rows[i]
            project_id = c[1]
            plant_name = c[2] if len(c) > 2 else ""
            status = c[3] if len(c) > 3 else ""
            i += 1

        # Skip blank rows
        while i < n and all_data_rows[i][1] == "":
            i += 1

        # --- Row D (optional): Umbrella ID / Umbrella Name / Count ---
        umbrella_id = umbrella_name = umbrella_count = ""
        if i < n and _is_umbrella_id(all_data_rows[i][1]):
            d = all_data_rows[i]
            col3 = d[3] if len(d) > 3 else ""
            if COUNT_RE.match(col3) or col3 == "":
                umbrella_id = d[1]
                umbrella_name = d[2] if len(d) > 2 else ""
                umbrella_count = col3
                i += 1

        # Parse location → City / State / Country
        city = state = country = ""
        loc_parts = [p.strip() for p in location.split("/")]
        if len(loc_parts) >= 3:
            city = loc_parts[0]
            state = loc_parts[1]
            country = " ".join(loc_parts[2:]).strip()
        elif len(loc_parts) == 2:
            city = loc_parts[0]
            state = loc_parts[1]

        records.append({
            "Source File": os.path.basename(pdf_path),
            "Industry": industry,
            "Date": date,
            "Project ID": project_id,
            "Umbrella Project ID": umbrella_id,
            "Project Name": clean(project_name),
            "Owner Name": owner,
            "Plant Name": plant_name,
            "Umbrella Project Name": umbrella_name,
            "TIV (USD)": tiv,
            "City": city,
            "State": state,
            "Country": country,
            "City, State, Country": location,
            "Status": status,
            "Umbrella Project Count": umbrella_count,
        })

    return records


# ---------------------------------------------------------------------------
# Parser 2 -- "Engine Lab Report #.pdf"  (detail files)
# ---------------------------------------------------------------------------

def _find(pattern, text, group=1, default=""):
    m = re.search(pattern, text, re.IGNORECASE | re.DOTALL)
    if m:
        return " ".join(m.group(group).split())
    return default


def parse_report_project_text(text):
    """Extract fields from the raw text of one project report page-group."""
    r = {}

    # Project ID
    r["Project ID"] = _find(r"Capital PEC Report\s+Project ID:\s*(\d+)", text)

    # Project Name
    r["Project Name (Report)"] = _find(
        r"Project Name\s+(.+?)(?:PEC Activity|Umbrella Project Name)", text)

    # Umbrella Project Name
    r["Umbrella Project Name (Report)"] = _find(
        r"Umbrella Project Name\s*(.+?)(?:Umbrella Project Id|Industry Code)", text)

    # Umbrella Project ID
    r["Umbrella Project ID (Report)"] = _find(
        r"[Uu]mbrella Project Id\s*(\d+)", text)

    # Umbrella Project Count
    r["Umbrella Project Count (Report)"] = _find(
        r"[Uu]mbrella Project Count\s*(\d+)", text)

    # Industry
    r["Industry (Report)"] = _find(
        r"Industry Code\s*\d+\s+([A-Za-z ]+?)(?:Project Type|TIV)", text)

    # Project Type
    r["Project Type"] = _find(
        r"Project Type\s+([\w ]+?)(?:TIV|SIC Code|\n)", text)

    # Sector
    r["Sector"] = _find(
        r"Sector\s+([\w /&]+?)(?:SIC Product|Status|\n)", text)

    # SIC Product  (no space before value, e.g. "SIC Product7374*0019 Hyperscale Data Center")
    r["SIC Product"] = _find(
        r"SIC Product\s*(\S[^\n]+?)(?:\n|Status)", text)

    # TIV
    r["TIV (USD) (Report)"] = _find(r"TIV \(USD\)\s+([\d,]+)", text)

    # Status
    r["Status (Report)"] = _find(
        r"\bStatus\s+(Active|Inactive|Complete|On Hold|Cancelled)\b", text)

    # Project Capacity  (value may be "Planned113 MW..." with no space after Planned)
    r["Project Capacity"] = _find(
        r"Project Capacity\s*(?:Planned\s*)?(.+?)(?:Plant Owner|Existing Building|\n)", text)

    # Existing Building Size
    r["Existing Building Size (Sq. Ft.)"] = _find(
        r"Existing Building Size \(Sq\. Ft\.\)\s+([\d,]+)\s*Sq\. Ft", text)

    # New Building Size
    r["New Building Size (Sq. Ft.)"] = _find(
        r"New Building Size \(Sq\. Ft\.\)\s+([\d,]+)\s*Sq\. Ft", text)

    # Plant Name
    r["Plant Name (Report)"] = _find(r"Plant Name\s+(.+?)\s+Unit Name", text)

    # Owner Name
    r["Owner Name (Report)"] = _find(r"Plant Owner\s+(.+?)\s+Plant Parent", text)

    # AFE date  (e.g. "AFE202610" -> "2026-10")
    m = re.search(r"\bAFE\s*(\d{4})(\d{2})\b", text)
    r["AFE date"] = f"{m.group(1)}-{m.group(2)}" if m else ""

    # Sub Bid Doc
    m = re.search(r"Sub Bid Doc\s*(\d{4})(\d{2})", text)
    r["Sub Bid Doc"] = f"{m.group(1)}-{m.group(2)}" if m else ""

    # Completion
    r["Completion"] = _find(r"Completion\s*(\d{2}-[A-Za-z]+-\d{4})", text)

    # Equip RFQ
    m = re.search(r"Equip RFQ\s*(\d{4})(\d{2})", text)
    r["Equip RFQ"] = f"{m.group(1)}-{m.group(2)}" if m else ""

    # Kick-Off
    m = re.search(r"Kick-?Off\s*(\d{4})(\d{2})", text)
    r["Kick-Off"] = f"{m.group(1)}-{m.group(2)}" if m else ""

    # Kickoff Slippage
    r["Kickoff Slippage"] = _find(r"Kickoff Slippage\s+(\d+\s*Months?)", text)

    # Duration
    r["Duration"] = _find(r"\bDuration\s+(\d+\s*Months?)", text)

    # Project Probability  (no space before value, e.g. "Project ProbabilityMedium (70-80%)")
    r["Project Probability"] = _find(
        r"Project Probability\s*(.+?)(?:\n|Scope)", text)

    # PEC Activity  (e.g. "PEC® ActivityEconomic Evaluation\n")
    # Match the inline form: "PEC® TimingP1 PEC® ActivityEconomic Evaluation"
    r["PEC Activity"] = _find(
        r"PEC\S+\s+Timing\S*\s+PEC\S+\s+Activity\s*(.+?)(?:\n|Project Probability)", text)

    return r


def parse_report_file(pdf_path):
    """
    A single Report PDF contains multiple project reports; a new project starts
    on pages containing "Capital PEC Report  Project ID:".
    """
    records = []

    with pdfplumber.open(pdf_path) as pdf:
        pages_text = [page.extract_text() or "" for page in pdf.pages]

    # Group pages by project
    project_groups = []
    current_pages = []
    for pt in pages_text:
        if re.search(r"Capital PEC Report\s+Project ID:", pt):
            if current_pages:
                project_groups.append("\n".join(current_pages))
            current_pages = [pt]
        else:
            current_pages.append(pt)
    if current_pages:
        project_groups.append("\n".join(current_pages))

    for group_text in project_groups:
        if not re.search(r"Capital PEC Report\s+Project ID:", group_text):
            continue
        rec = parse_report_project_text(group_text)
        rec["Source File (Report)"] = os.path.basename(pdf_path)
        records.append(rec)

    return records


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main():
    # --- Parse index files ---
    index_files = sorted(glob.glob(os.path.join(DATA_DIR, "Engine Lab [0-9]*.pdf")))
    all_index = []
    for f in index_files:
        print(f"Parsing index: {os.path.basename(f)}")
        try:
            recs = parse_index_file(f)
            print(f"  -> {len(recs)} projects")
            all_index.extend(recs)
        except Exception as e:
            print(f"  ERROR: {e}")

    df_index = pd.DataFrame(all_index)
    df_index["Project ID"] = df_index["Project ID"].astype(str).str.strip()

    # --- Parse report files ---
    report_files = sorted(glob.glob(os.path.join(DATA_DIR, "Engine Lab Report [0-9]*.pdf")))
    all_report = []
    for f in report_files:
        print(f"Parsing report: {os.path.basename(f)}")
        try:
            recs = parse_report_file(f)
            print(f"  -> {len(recs)} projects")
            all_report.extend(recs)
        except Exception as e:
            print(f"  ERROR: {e}")

    df_report = pd.DataFrame(all_report)
    df_report["Project ID"] = df_report["Project ID"].astype(str).str.strip()

    # De-duplicate report records (keep last = most recently parsed)
    df_report_dedup = df_report.drop_duplicates(subset=["Project ID"], keep="last")

    print(f"\nIndex rows: {len(df_index)}")
    print(f"Report rows (deduped): {len(df_report_dedup)}")

    # --- Merge on Project ID ---
    df_merged = pd.merge(df_index, df_report_dedup, on="Project ID", how="outer")
    print(f"Merged rows: {len(df_merged)}")

    # --- Coalesce overlapping columns: prefer index value, fall back to report ---
    def coalesce(df, primary, fallback):
        if fallback in df.columns and primary in df.columns:
            mask = df[primary].isna() | (df[primary].astype(str).str.strip() == "")
            df.loc[mask, primary] = df.loc[mask, fallback]
        return df

    df_merged = coalesce(df_merged, "Project Name",           "Project Name (Report)")
    df_merged = coalesce(df_merged, "Plant Name",             "Plant Name (Report)")
    df_merged = coalesce(df_merged, "Owner Name",             "Owner Name (Report)")
    df_merged = coalesce(df_merged, "Umbrella Project Name",  "Umbrella Project Name (Report)")
    df_merged = coalesce(df_merged, "Umbrella Project ID",    "Umbrella Project ID (Report)")
    df_merged = coalesce(df_merged, "Umbrella Project Count", "Umbrella Project Count (Report)")
    df_merged = coalesce(df_merged, "TIV (USD)",              "TIV (USD) (Report)")
    df_merged = coalesce(df_merged, "Status",                 "Status (Report)")

    # Drop now-redundant helper columns
    drop_cols = [
        "Project Name (Report)", "Plant Name (Report)", "Owner Name (Report)",
        "Umbrella Project Name (Report)", "Umbrella Project ID (Report)",
        "Umbrella Project Count (Report)", "TIV (USD) (Report)",
        "Status (Report)", "Industry (Report)",
    ]
    df_merged.drop(columns=[c for c in drop_cols if c in df_merged.columns], inplace=True)

    # --- Define final column order ---
    final_columns = [
        "Source File",
        "Industry",
        "Date",
        "Project ID",
        "Umbrella Project ID",
        "Project Name",
        "Owner Name",
        "Plant Name",
        "Umbrella Project Name",
        "TIV (USD)",
        "City",
        "State",
        "Country",
        "City, State, Country",
        "Status",
        "Umbrella Project Count",
        # Report-specific fields
        "Source File (Report)",
        "Project Type",
        "Sector",
        "SIC Product",
        "Project Capacity",
        "Existing Building Size (Sq. Ft.)",
        "New Building Size (Sq. Ft.)",
        "AFE date",
        "Sub Bid Doc",
        "Completion",
        "Equip RFQ",
        "Kick-Off",
        "Kickoff Slippage",
        "Duration",
        "Project Probability",
        "PEC Activity",
    ]

    present = [c for c in final_columns if c in df_merged.columns]
    extras  = [c for c in df_merged.columns if c not in present]
    df_out  = df_merged[present + extras].copy()

    df_out.to_csv(OUTPUT_CSV, index=False)
    df_out.to_excel(OUTPUT_XLSX, index=False, engine="openpyxl")
    print(f"\nDone. {len(df_out)} rows written to:\n  {OUTPUT_CSV}\n  {OUTPUT_XLSX}")

    # Fill-rate summary
    print(f"\nColumn fill rates ({len(df_out.columns)} columns):")
    for col in df_out.columns:
        filled = df_out[col].astype(str).str.strip().replace("nan", "").ne("").sum()
        pct = 100 * filled / len(df_out) if len(df_out) > 0 else 0
        print(f"  {col:<48} {filled:>5} / {len(df_out)}  ({pct:.0f}%)")


if __name__ == "__main__":
    main()
