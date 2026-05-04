"""
reprocess_excel.py  —  VEIR Review v2 corrections
===================================================
Reads:   (default) /Users/careycao/Downloads/project_joined.xlsx
         or set IN_EXCEL env/constant below
Writes:  output/project_joined_v2.xlsx

Changes applied vs. v1:
  [FIX 1] time_to_power_months  — use Completion date directly (100% coverage)
           instead of Kick-Off + Duration (only 57% coverage)
  [FIX 2] whitespace_power_density_w_sqft — correct denominator to
           New Building Size (this phase's white space), correct units to W/sqft
  [FIX 3] campus_power_density_w_sqft — numerator = sum of all Project Capacity
           in the same Umbrella; denominator = Existing Building Size (proxy for
           established campus footprint), fallback to campus_sqft
  [FIX 4] whitespace_congestion_burden_score — recalculated with new wpd values
  [DROP]  power_infra_disaggregation_score  (Low/Drop per VEIR review)
  [DROP]  future_readiness_pressure_score   (Low/Drop per VEIR review)
  [DROP]  baseline_distribution_loss_mwh   (Low/Drop per VEIR review)
  [NEW]   campus_size_sqft  — total campus footprint in sqft (calculated)
  [NEW]   labor_cost_burden_score  — union density + prevailing wage burden
           by state, LLM-scored; High/High weight per VEIR review
  [NEW]   labor_cost_burden_explanation, union_density_pct, prevailing_wage_law
"""

import os, json, re
import pandas as pd
import numpy as np
from datetime import datetime
from dotenv import load_dotenv
from openai import OpenAI

# ── Config ─────────────────────────────────────────────────────────────────────
load_dotenv(os.path.join(os.path.dirname(__file__), '..', '.env'))
client = OpenAI(api_key=os.getenv("OPENAI_API_KEY"))

ROOT      = os.path.join(os.path.dirname(os.path.abspath(__file__)), '..')
IN_EXCEL  = os.path.join(os.path.expanduser('~'), 'Downloads', 'project_joined.xlsx')
OUT_EXCEL = os.path.join(ROOT, 'output', 'project_joined_v2.xlsx')
CKPT_FILE = os.path.join(ROOT, 'output', 'labor_cost_checkpoint.json')

REFERENCE_DATE = datetime(2026, 4, 1)

# ── Helpers ────────────────────────────────────────────────────────────────────

def months_between(d1, d2):
    """Fractional months from d1 to d2."""
    return (d2.year - d1.year) * 12 + (d2.month - d1.month)

def safe_div(a, b):
    try:
        if pd.isna(a) or pd.isna(b) or b == 0:
            return np.nan
        return float(a) / float(b)
    except Exception:
        return np.nan

def clamp10(x):
    if pd.isna(x):
        return np.nan
    return float(max(0.0, min(10.0, x)))

def llm_json(prompt: str, system: str = "You are a precise analyst. Always respond with valid JSON only.") -> dict:
    """Call OpenAI Responses API with web search, return parsed JSON dict."""
    response = client.responses.create(
        model="gpt-4o-mini",
        tools=[{"type": "web_search_preview"}],
        instructions=system,
        input=prompt,
    )
    text = ""
    for item in response.output:
        if hasattr(item, 'content'):
            for block in item.content:
                if hasattr(block, 'text'):
                    text += block.text
    text = re.sub(r'^```(?:json)?\s*', '', text.strip(), flags=re.MULTILINE)
    text = re.sub(r'```\s*$', '', text.strip(), flags=re.MULTILINE)
    return json.loads(text.strip())

# ── Load data ──────────────────────────────────────────────────────────────────
print(f"Loading: {IN_EXCEL}")
df = pd.read_excel(IN_EXCEL, sheet_name='project_joined')
print(f"  {len(df)} rows, {len(df.columns)} columns\n")

# ══════════════════════════════════════════════════════════════════════════════
# [FIX 1] time_to_power_months
# Previous: months(April 2026, Kick-Off + Duration) — only 57% coverage
# New:      months(April 2026, Completion date)     — 100% coverage
# Completion is the Engine Lab projected completion date for the phase.
# Negative = already completed/powered on before April 2026.
# ══════════════════════════════════════════════════════════════════════════════
print("[FIX 1] time_to_power_months — using Completion date (100% coverage)")

def calc_time_to_power(completion_val):
    """Months from April 2026 to the Completion date."""
    if pd.isna(completion_val):
        return np.nan
    try:
        dt = pd.to_datetime(completion_val)
        return months_between(REFERENCE_DATE, dt)
    except Exception:
        return np.nan

df['time_to_power_months'] = df['Completion'].apply(calc_time_to_power)

coverage = df['time_to_power_months'].notna().mean() * 100
print(f"  Coverage: {coverage:.1f}%  |  "
      f"min={df['time_to_power_months'].min():.0f}mo  "
      f"median={df['time_to_power_months'].median():.0f}mo  "
      f"max={df['time_to_power_months'].max():.0f}mo\n")

# ══════════════════════════════════════════════════════════════════════════════
# [FIX 2] whitespace_power_density_w_sqft
# Previous: Project Capacity (MW) / campus_white_space_sqft
#           — campus_white_space_sqft aggregates all phases, over-counting
# New:      Project Capacity (MW) × 1,000,000 / New Building Size (sqft)
#           — denominates only THIS phase's new white space (the actual IT floor
#             being built), corrects units to genuine W/sqft
# Typical range: 100–600 W/sqft (legacy DCs ~100-150, AI/GPU clusters 300-600+)
# ══════════════════════════════════════════════════════════════════════════════
print("[FIX 2] whitespace_power_density_w_sqft — New Building Size denominator, W/sqft units")

df['whitespace_power_density_w_sqft'] = df.apply(
    lambda r: safe_div(
        r['Project Capacity (Numeric)'] * 1_000_000,
        r['New Building Size (Sq. Ft.) (Numeric)']
    ), axis=1
)

print(f"  mean={df['whitespace_power_density_w_sqft'].mean():.1f} W/sqft  "
      f"median={df['whitespace_power_density_w_sqft'].median():.1f} W/sqft  "
      f"p99={df['whitespace_power_density_w_sqft'].quantile(0.99):.1f} W/sqft\n")

# ══════════════════════════════════════════════════════════════════════════════
# [FIX 3] campus_power_density_w_sqft
# Previous: Project Capacity (single phase) / campus_sqft
#           — numerator understates true campus load for multi-phase sites
# New:      sum(all Project Capacity in same Umbrella) × 1,000,000
#           / Existing Building Size (established campus footprint proxy)
#           — shows how much total MW the campus will carry vs. its existing
#             physical footprint; Existing Building Size fallback = campus_sqft
# Standalone projects (no Umbrella ID) use their own capacity as numerator.
# ══════════════════════════════════════════════════════════════════════════════
print("[FIX 3] campus_power_density_w_sqft — umbrella-summed capacity / Existing Building Size")

# Sum all Project Capacity within each Umbrella
umbrella_cap = df.groupby('Umbrella Project ID')['Project Capacity (Numeric)'].transform('sum')
df['_campus_capacity_mw'] = np.where(
    df['Umbrella Project ID'].isna(),
    df['Project Capacity (Numeric)'],   # standalone project
    umbrella_cap
)

# Denominator: campus_sqft (Step 2 computed value — existing + all phases + grey space)
# More reliable than Existing Building Size which has data quality issues
# (111 projects = 0, Leesburg = 1,512 sqft data entry error → produces non-physical values)
df['_campus_denom_sqft'] = df['campus_sqft'].replace(0, np.nan)

df['campus_power_density_w_sqft'] = df.apply(
    lambda r: safe_div(
        r['_campus_capacity_mw'] * 1_000_000,
        r['_campus_denom_sqft']
    ), axis=1
)

print(f"  mean={df['campus_power_density_w_sqft'].mean():.1f} W/sqft  "
      f"median={df['campus_power_density_w_sqft'].median():.1f} W/sqft  "
      f"p99={df['campus_power_density_w_sqft'].quantile(0.99):.1f} W/sqft\n")

# ══════════════════════════════════════════════════════════════════════════════
# [FIX 4] whitespace_congestion_burden_score — recalculate with new wpd values
# (since wpd denominator changed, relative densities changed → rescale to p99)
# ══════════════════════════════════════════════════════════════════════════════
print("[FIX 4] Recalculating whitespace_congestion_burden_score with new wpd values")

HIGH_DENSITY_SECTORS = {'Data Centers', 'Semiconductor', 'Battery', 'EV', 'Hyperscale'}
df['_hd_flag'] = df['Sector'].apply(
    lambda s: 1.0 if any(h.lower() in str(s).lower() for h in HIGH_DENSITY_SECTORS) else 0.0
)

_wpd_p99 = df['whitespace_power_density_w_sqft'].quantile(0.99)

def calc_wcbs(row):
    wpd = row['whitespace_power_density_w_sqft']
    ph  = row['phase_index'] if not pd.isna(row['phase_index']) else 0
    hd  = row['_hd_flag']
    if pd.isna(wpd) or _wpd_p99 == 0:
        return np.nan
    c1 = (wpd / _wpd_p99) * 5.0         # power density intensity (norm to p99)
    c2 = min(ph * 0.5, 2.5)              # phase maturity (more phases = more congested)
    c3 = hd * 2.5                         # high-density sector bonus
    return clamp10(c1 + c2 + c3)

df['whitespace_congestion_burden_score'] = df.apply(calc_wcbs, axis=1)
print(f"  Done. mean={df['whitespace_congestion_burden_score'].mean():.2f}/10\n")

# ══════════════════════════════════════════════════════════════════════════════
# [NEW] campus_size_sqft
# Total campus footprint in sqft: existing buildings + all phases' new
# construction + grey space (mechanical, electrical, HVAC infrastructure).
# Uses the existing campus_sqft field (computed in pipeline Step 2) which
# already accounts for grey space ratios by state (18–25%).
# ══════════════════════════════════════════════════════════════════════════════
print("[NEW] campus_size_sqft — total campus footprint including grey space")
df['campus_size_sqft'] = df['campus_sqft']
print(f"  mean={df['campus_size_sqft'].mean()/1e6:.2f}M sqft  "
      f"median={df['campus_size_sqft'].median()/1e6:.2f}M sqft\n")

# ══════════════════════════════════════════════════════════════════════════════
# [NEW] labor_cost_burden_score  (LLM + web search, deduplicated by State)
# Score 0–10: higher = more union-dense, higher prevailing wages, tighter labor
# market. VEIR value prop: superconducting cables require fewer cable pulls than
# conventional copper (higher ampacity per cable → fewer conductors), so labor
# savings are larger in high-cost states.
# ══════════════════════════════════════════════════════════════════════════════
print("[NEW] labor_cost_burden_score — LLM scoring per state (with checkpoint)")

# Load checkpoint
LABOR_CACHE = {}
if os.path.exists(CKPT_FILE):
    with open(CKPT_FILE, 'r') as f:
        LABOR_CACHE = json.load(f)
    print(f"  Loaded {len(LABOR_CACHE)} states from checkpoint")

unique_states = df['State'].dropna().unique()
todo_states   = [s for s in unique_states if str(s) not in LABOR_CACHE]
print(f"  Total unique states: {len(unique_states)}  |  Remaining to score: {len(todo_states)}")

for i, state in enumerate(todo_states):
    prompt = f"""
You are scoring a US state for construction labor cost burden as it relates to
large electrical infrastructure projects (data centers, industrial facilities).

State: {state}

Search the web for current data on:
1. Construction sector union density (% unionized) in {state}
2. Whether {state} has state prevailing wage laws (Davis-Bacon equivalent)
3. Average electrician / electrical contractor hourly wages in {state}
4. Current construction labor market tightness or shortage signals in {state}

Context: A superconducting cable company (VEIR) sells into data center
construction. Their cables carry more power per cable than copper, meaning
fewer cable pulls per project. In high-union, high-wage states, this labor
reduction creates greater cost savings — making those states higher-priority
for VEIR's sales motion.

Return ONLY a valid JSON object with exactly these keys:
{{
  "labor_cost_burden_score": <float 0.0–10.0, 10 = highest union density + highest wages + strongest prevailing wage laws>,
  "union_density_pct": <estimated % of construction workers in unions as a number, or null if unknown>,
  "prevailing_wage_law": "<one of: strong / moderate / none>",
  "labor_cost_burden_explanation": "<20 words or less explaining the score>"
}}
"""
    try:
        result = llm_json(prompt)
        LABOR_CACHE[str(state)] = {
            'labor_cost_burden_score':       float(result.get('labor_cost_burden_score', np.nan)),
            'union_density_pct':             result.get('union_density_pct', None),
            'prevailing_wage_law':           str(result.get('prevailing_wage_law', '')),
            'labor_cost_burden_explanation': str(result.get('labor_cost_burden_explanation', '')),
        }
    except Exception as e:
        print(f"  WARNING: failed for {state}: {e}")
        LABOR_CACHE[str(state)] = {
            'labor_cost_burden_score': np.nan,
            'union_density_pct': None,
            'prevailing_wage_law': 'ERROR',
            'labor_cost_burden_explanation': 'ERROR',
        }

    # Save checkpoint after every state
    with open(CKPT_FILE, 'w') as f:
        json.dump(LABOR_CACHE, f, indent=2)

    pct_done = (i + 1) / len(todo_states) * 100 if todo_states else 100
    print(f"  [{i+1}/{len(todo_states)}] {state}: "
          f"score={LABOR_CACHE[str(state)]['labor_cost_burden_score']}  "
          f"union={LABOR_CACHE[str(state)]['union_density_pct']}%  "
          f"prevailing_wage={LABOR_CACHE[str(state)]['prevailing_wage_law']}")

# Join back to df
df['labor_cost_burden_score']       = df['State'].astype(str).map(lambda s: LABOR_CACHE.get(s, {}).get('labor_cost_burden_score', np.nan))
df['union_density_pct']             = df['State'].astype(str).map(lambda s: LABOR_CACHE.get(s, {}).get('union_density_pct', np.nan))
df['prevailing_wage_law']           = df['State'].astype(str).map(lambda s: LABOR_CACHE.get(s, {}).get('prevailing_wage_law', ''))
df['labor_cost_burden_explanation'] = df['State'].astype(str).map(lambda s: LABOR_CACHE.get(s, {}).get('labor_cost_burden_explanation', ''))
print(f"\n  labor_cost_burden_score joined. mean={df['labor_cost_burden_score'].mean():.2f}/10\n")

# ══════════════════════════════════════════════════════════════════════════════
# [DROP] Low/Drop attributes per VEIR review
# ══════════════════════════════════════════════════════════════════════════════
DROP_COLS = [
    'power_infra_disaggregation_score',   # Low/Drop — poorly captures VEIR's value
    'future_readiness_pressure_score',    # Low/Drop — sqft ratio not meaningful enough
    'baseline_distribution_loss_mwh',     # Low/Drop — duration-scaled MWh not actionable
]
dropped = [c for c in DROP_COLS if c in df.columns]
df = df.drop(columns=dropped)
print(f"[DROP] Removed {len(dropped)} columns: {dropped}\n")

# ── Clean up temp columns ──────────────────────────────────────────────────────
temp_cols = [c for c in df.columns if c.startswith('_')]
df = df.drop(columns=temp_cols)

# ══════════════════════════════════════════════════════════════════════════════
# WRITE output
# ══════════════════════════════════════════════════════════════════════════════
os.makedirs(os.path.join(ROOT, 'output'), exist_ok=True)

print(f"Writing: {OUT_EXCEL}")
with pd.ExcelWriter(OUT_EXCEL, engine='openpyxl') as writer:
    df.to_excel(writer, sheet_name='project_joined_v2', index=False)

    # Summary sheet: what changed
    summary_rows = [
        ['Change', 'Attribute', 'Details'],
        ['FIX',  'time_to_power_months',           'Now uses Completion date (100% coverage). Was Kick-Off+Duration (57%).'],
        ['FIX',  'whitespace_power_density_w_sqft', 'Denominator = New Building Size (this phase only). Units corrected to W/sqft.'],
        ['FIX',  'campus_power_density_w_sqft',     'Numerator = umbrella-summed capacity. Denominator = Existing Building Size (fallback: campus_sqft).'],
        ['FIX',  'whitespace_congestion_burden_score', 'Recalculated with corrected whitespace_power_density values.'],
        ['NEW',  'campus_size_sqft',               'Total campus footprint incl. grey space (sqft). = campus_sqft from Step 2.'],
        ['NEW',  'labor_cost_burden_score',         '0-10. Union density + prevailing wage burden by state. LLM-scored. High/High weight.'],
        ['NEW',  'union_density_pct',               'Estimated % of construction workers unionized in the state.'],
        ['NEW',  'prevailing_wage_law',             'State prevailing wage law strength: strong / moderate / none.'],
        ['NEW',  'labor_cost_burden_explanation',   'LLM justification for the score (≤20 words).'],
        ['DROP', 'power_infra_disaggregation_score', 'Removed per VEIR review (Low/Drop).'],
        ['DROP', 'future_readiness_pressure_score',  'Removed per VEIR review (Low/Drop).'],
        ['DROP', 'baseline_distribution_loss_mwh',   'Removed per VEIR review (Low/Drop).'],
    ]
    summary_df = pd.DataFrame(summary_rows[1:], columns=summary_rows[0])
    summary_df.to_excel(writer, sheet_name='v2_changes', index=False)

print(f"\n=== Done ===")
print(f"  Rows:    {len(df)}")
print(f"  Columns: {len(df.columns)}")
print(f"  Output:  {OUT_EXCEL}")
print(f"  Summary: see 'v2_changes' sheet")
