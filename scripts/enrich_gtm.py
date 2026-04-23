"""
enrich_gtm.py
Go-to-market enrichment pipeline for superconductor company analysis.
Reads:  output/engine_lab_filtered.csv
Writes: output/project_enriched.csv
        output/city_state_lookup.csv
        output/variable_definitions.md
"""

import os, json, re, math
import pandas as pd
import numpy as np
from datetime import datetime
from dotenv import load_dotenv
from openai import OpenAI

# ── Config ────────────────────────────────────────────────────────────────────
load_dotenv(os.path.join(os.path.dirname(__file__), '..', '.env'))
client = OpenAI(api_key=os.getenv("OPENAI_API_KEY"))

BASE   = os.path.dirname(os.path.abspath(__file__))
ROOT   = os.path.join(BASE, '..')
IN_CSV = os.path.join(ROOT, 'output', 'engine_lab_filtered.csv')
OUT_ENRICHED  = os.path.join(ROOT, 'output', 'project_enriched.csv')
OUT_LOOKUP    = os.path.join(ROOT, 'output', 'city_state_lookup.csv')
OUT_VARDEFS   = os.path.join(ROOT, 'output', 'variable_definitions.md')

REFERENCE_DATE = datetime(2026, 4, 1)   # April 2026 baseline

# ── Helpers ───────────────────────────────────────────────────────────────────

def parse_duration_months(val):
    """'13 Months' → 13.0, else NaN"""
    if pd.isna(val):
        return np.nan
    m = re.search(r'(\d+(?:\.\d+)?)', str(val))
    return float(m.group(1)) if m else np.nan

def parse_kickoff(val):
    """'2029-04' → datetime, else NaT"""
    try:
        return pd.to_datetime(str(val), format='%Y-%m')
    except Exception:
        return pd.NaT

def months_between(d1, d2):
    """Fractional months from d1 to d2."""
    return (d2.year - d1.year) * 12 + (d2.month - d1.month)

def safe_div(a, b):
    try:
        if pd.isna(a) or pd.isna(b) or b == 0:
            return np.nan
        return a / b
    except Exception:
        return np.nan

def clamp10(x):
    """Clamp a value to [0, 10]."""
    if pd.isna(x):
        return np.nan
    return float(max(0.0, min(10.0, x)))

def llm_json(prompt: str, system: str = "You are a precise analyst. Always respond with valid JSON only.") -> dict:
    """Call OpenAI Responses API with web search, parse JSON from response."""
    response = client.responses.create(
        model="gpt-4o-mini",
        tools=[{"type": "web_search_preview"}],
        instructions=system,
        input=prompt,
    )
    # Extract text from response output items
    text = ""
    for item in response.output:
        if hasattr(item, 'content'):
            for block in item.content:
                if hasattr(block, 'text'):
                    text += block.text
    # Strip markdown fences if present
    text = re.sub(r'^```(?:json)?\s*', '', text.strip(), flags=re.MULTILINE)
    text = re.sub(r'```\s*$', '', text.strip(), flags=re.MULTILINE)
    return json.loads(text.strip())


# ── Load data ─────────────────────────────────────────────────────────────────
print("Loading input data...")
df = pd.read_csv(IN_CSV)
print(f"  {len(df)} rows, {len(df.columns)} columns loaded.")

# ── Primary key columns ───────────────────────────────────────────────────────
PK = ['Project ID', 'Project Name', 'City', 'State']

# ══════════════════════════════════════════════════════════════════════════════
# BLOCK 1 — Calculated variables (no API calls)
# ══════════════════════════════════════════════════════════════════════════════
print("\n[1/4] Calculating derived variables...")

# Parse kick-off and duration
df['_kickoff_dt']  = df['Kick-Off'].apply(parse_kickoff)
df['_duration_mo'] = df['Duration'].apply(parse_duration_months)

# time_to_power_months: months from April 2026 to (kickoff + duration)
def calc_time_to_power(row):
    ko = row['_kickoff_dt']
    dur = row['_duration_mo']
    if pd.isna(ko) or pd.isna(dur):
        return np.nan
    power_on = ko + pd.DateOffset(months=int(dur))
    return months_between(REFERENCE_DATE, power_on)

df['time_to_power_months'] = df.apply(calc_time_to_power, axis=1)

# whitespace_power_density_w_sqft
df['whitespace_power_density_w_sqft'] = df.apply(
    lambda r: safe_div(r['Project Capacity (Numeric)'], r['campus_white_space_sqft']), axis=1)

# campus_power_density_w_sqft
df['campus_power_density_w_sqft'] = df.apply(
    lambda r: safe_div(r['Project Capacity (Numeric)'], r['campus_sqft']), axis=1)

# power_infra_disaggregation_score (0–10)
# Components: phase_index > 1 (0/3.3), Umbrella Project Count > 1 (0/3.3), total_campus_expansion_sqft normalised (0–3.4)
_exp_p99 = df['total_campus_expansion_sqft'].quantile(0.99)
def calc_pids(row):
    c1 = 3.3 if (not pd.isna(row['phase_index']) and row['phase_index'] > 1) else 0.0
    c2 = 3.3 if (not pd.isna(row['Umbrella Project Count']) and row['Umbrella Project Count'] > 1) else 0.0
    exp = row['total_campus_expansion_sqft']
    c3 = 3.4 * min(float(exp) / _exp_p99, 1.0) if not pd.isna(exp) and _exp_p99 > 0 else 0.0
    return clamp10(c1 + c2 + c3)
df['power_infra_disaggregation_score'] = df.apply(calc_pids, axis=1)

# cable_multiplicity_burden_score (0–10)
# Estimated feeder count ~ capacity/20 MW per feeder, scaled by phase_index, normalised against p99
_cap_p99 = df['Project Capacity (Numeric)'].quantile(0.99)
_sqft_p99 = df['campus_sqft'].quantile(0.99)
def calc_cmbs(row):
    cap  = row['Project Capacity (Numeric)']
    sqft = row['campus_sqft']
    ph   = row['phase_index'] if not pd.isna(row['phase_index']) else 1
    if pd.isna(cap) or pd.isna(sqft):
        return np.nan
    feeder_est = (cap / 20.0) * (1 + ph * 0.1)
    norm = feeder_est / ((_cap_p99 / 20.0) * 1.5)   # normalise
    return clamp10(norm * 10)
df['cable_multiplicity_burden_score'] = df.apply(calc_cmbs, axis=1)

# high-density sector flag (used in congestion score)
HIGH_DENSITY_SECTORS = {'Data Centers', 'Semiconductor', 'Battery', 'EV', 'Hyperscale'}
df['_high_density_flag'] = df['Sector'].apply(
    lambda s: 1.0 if any(h.lower() in str(s).lower() for h in HIGH_DENSITY_SECTORS) else 0.0)

# whitespace_congestion_burden_score (0–10)
_wpd_p99 = df['whitespace_power_density_w_sqft'].quantile(0.99)
def calc_wcbs(row):
    wpd = row['whitespace_power_density_w_sqft']
    ph  = row['phase_index'] if not pd.isna(row['phase_index']) else 0
    hd  = row['_high_density_flag']
    if pd.isna(wpd) or _wpd_p99 == 0:
        return np.nan
    c1 = (wpd / _wpd_p99) * 5.0
    c2 = min(ph * 0.5, 2.5)
    c3 = hd * 2.5
    return clamp10(c1 + c2 + c3)
df['whitespace_congestion_burden_score'] = df.apply(calc_wcbs, axis=1)

# resiliency_topology_complexity_score (0–10)
_upc_p99 = df['Umbrella Project Count'].quantile(0.99)
EXPANSION_TYPES = {'Plant Expansion', 'Expansion'}
def calc_rtcs(row):
    upc = row['Umbrella Project Count'] if not pd.isna(row['Umbrella Project Count']) else 0
    ph  = row['phase_index'] if not pd.isna(row['phase_index']) else 0
    exp = row['total_campus_expansion_sqft'] if not pd.isna(row['total_campus_expansion_sqft']) else 0
    pt  = str(row['Project Type'])
    c1 = min(float(upc) / max(_upc_p99, 1), 1.0) * 3.0
    c2 = min(ph * 0.4, 2.0)
    c3 = min(float(exp) / max(_exp_p99, 1), 1.0) * 3.0
    c4 = 2.0 if any(e.lower() in pt.lower() for e in EXPANSION_TYPES) else 0.0
    return clamp10(c1 + c2 + c3 + c4)
df['resiliency_topology_complexity_score'] = df.apply(calc_rtcs, axis=1)

# future_readiness_pressure_score (0–10)
def calc_frps(row):
    exp  = row['total_campus_expansion_sqft']
    sqft = row['campus_sqft']
    ph   = row['phase_index']
    if pd.isna(exp) or pd.isna(sqft) or pd.isna(ph) or sqft == 0:
        return np.nan
    ratio = float(exp) / float(sqft)   # 0–∞, typically 0–1+
    ph_norm = min(float(ph) / 10.0, 1.0)
    raw = (min(ratio, 1.0) * 7.0) + (ph_norm * 3.0)
    return clamp10(raw)
df['future_readiness_pressure_score'] = df.apply(calc_frps, axis=1)

# baseline_distribution_loss_mwh
df['baseline_distribution_loss_mwh'] = df.apply(
    lambda r: r['Project Capacity (Numeric)'] * 0.04 * r['_duration_mo']
              if not pd.isna(r['_duration_mo']) and not pd.isna(r['Project Capacity (Numeric)'])
              else np.nan, axis=1)

print("  Calculated variables done.")

# ══════════════════════════════════════════════════════════════════════════════
# BLOCK 2 — LLM: high_density_load_share_score
# Deduplicate on (Owner Name, Sector, SIC Product)
# ══════════════════════════════════════════════════════════════════════════════
print("\n[2/4] LLM scoring — high_density_load_share_score ...")
print(f"  Unique (Owner, Sector, SIC) keys: {df[['Owner Name','Sector','SIC Product']].drop_duplicates().shape[0]}")

HDLS_CACHE = {}   # (owner, sector, sic) → {score, explanation}
unique_hdls = df[['Owner Name','Sector','SIC Product']].drop_duplicates().reset_index(drop=True)

for i, row in unique_hdls.iterrows():
    key = (str(row['Owner Name']), str(row['Sector']), str(row['SIC Product']))
    prompt = f"""
You are scoring a data center / industrial project owner for compute density workload profile.

Owner: {key[0]}
Sector: {key[1]}
SIC Product: {key[2]}

Search the web for typical workload type and compute density for this owner and project profile.
Return ONLY a JSON object with these exact keys:
{{
  "high_density_load_share_score": <integer 0-10, where 10 = extremely high density AI/HPC workloads>,
  "high_density_load_share_explanation": "<20 words or less describing workload density>"
}}
"""
    try:
        result = llm_json(prompt)
        HDLS_CACHE[key] = {
            'high_density_load_share_score': result.get('high_density_load_share_score', np.nan),
            'high_density_load_share_explanation': result.get('high_density_load_share_explanation', '')
        }
    except Exception as e:
        print(f"  WARNING: HDLS failed for {key[0]}: {e}")
        HDLS_CACHE[key] = {'high_density_load_share_score': np.nan, 'high_density_load_share_explanation': 'ERROR'}
    if (i + 1) % 10 == 0 or (i + 1) == len(unique_hdls):
        print(f"  [{i+1}/{len(unique_hdls)}] high_density_load_share batch complete")

# Join back
df['_hdls_key'] = list(zip(df['Owner Name'].astype(str), df['Sector'].astype(str), df['SIC Product'].astype(str)))
df['high_density_load_share_score']       = df['_hdls_key'].map(lambda k: HDLS_CACHE.get(k, {}).get('high_density_load_share_score', np.nan))
df['high_density_load_share_explanation'] = df['_hdls_key'].map(lambda k: HDLS_CACHE.get(k, {}).get('high_density_load_share_explanation', ''))
print("  high_density_load_share_score joined to all rows.")

# ══════════════════════════════════════════════════════════════════════════════
# BLOCK 3 — LLM: foak_commercial_access_score
# Deduplicate on Owner Name
# ══════════════════════════════════════════════════════════════════════════════
print("\n[3/4] LLM scoring — foak_commercial_access_score ...")
print(f"  Unique Owner Name keys: {df['Owner Name'].nunique()}")

FOAK_CACHE = {}   # owner → {score, explanation, customer_type_label}
unique_owners = df['Owner Name'].dropna().unique()

for i, owner in enumerate(unique_owners):
    prompt = f"""
You are scoring a company for its openness to first-of-a-kind (FOAK) infrastructure vendors.

Company: {owner}
Context: This company is building large-scale data center or industrial facilities.

Search the web for this company's procurement behavior, vendor partnerships, and innovation appetite.
Return ONLY a JSON object with these exact keys:
{{
  "foak_commercial_access_score": <integer 0-10, where 10 = very open to novel vendors>,
  "foak_commercial_access_explanation": "<20 words or less>",
  "customer_type_label": "<one of: hyperscaler / neocloud / OEM / colo / enterprise>"
}}
"""
    try:
        result = llm_json(prompt)
        FOAK_CACHE[str(owner)] = {
            'foak_commercial_access_score':       result.get('foak_commercial_access_score', np.nan),
            'foak_commercial_access_explanation': result.get('foak_commercial_access_explanation', ''),
            'customer_type_label':                result.get('customer_type_label', '')
        }
    except Exception as e:
        print(f"  WARNING: FOAK failed for {owner}: {e}")
        FOAK_CACHE[str(owner)] = {'foak_commercial_access_score': np.nan, 'foak_commercial_access_explanation': 'ERROR', 'customer_type_label': ''}
    if (i + 1) % 10 == 0 or (i + 1) == len(unique_owners):
        print(f"  [{i+1}/{len(unique_owners)}] foak_commercial_access batch complete")

# Join back
df['foak_commercial_access_score']       = df['Owner Name'].astype(str).map(lambda o: FOAK_CACHE.get(o, {}).get('foak_commercial_access_score', np.nan))
df['foak_commercial_access_explanation'] = df['Owner Name'].astype(str).map(lambda o: FOAK_CACHE.get(o, {}).get('foak_commercial_access_explanation', ''))
df['customer_type_label']               = df['Owner Name'].astype(str).map(lambda o: FOAK_CACHE.get(o, {}).get('customer_type_label', ''))
print("  foak_commercial_access_score joined to all rows.")

# ══════════════════════════════════════════════════════════════════════════════
# BLOCK 4 — Geo lookup: city_state_lookup.csv
# One API call per unique (City, State) pair
# ══════════════════════════════════════════════════════════════════════════════
print("\n[4/4] Geo lookup — city_state_lookup.csv ...")
unique_geo = df[['City','State']].drop_duplicates().reset_index(drop=True)
print(f"  Unique (City, State) pairs: {len(unique_geo)}")

GEO_CACHE = {}   # (city, state) → {permitting_burden_index, hv_mv_readiness_gap_score, ...}
geo_rows  = []

for i, grow in unique_geo.iterrows():
    city  = str(grow['City'])
    state = str(grow['State'])
    key   = (city, state)
    prompt = f"""
You are scoring a US city/state location for infrastructure development.

City: {city}
State: {state}

Search the web for relevant data on permitting speed, high-voltage grid infrastructure, land costs, and buildable land availability.
Return ONLY a JSON object with these exact keys:
{{
  "permitting_burden_index": <float 0-10, 10 = extremely burdensome permitting>,
  "hv_mv_readiness_gap_score": <float 0-10, 10 = major gap in HV/MV grid readiness>,
  "land_cost_proxy_score": <float 0-10, 10 = extremely high land cost>,
  "buildable_land_constraint_score": <float 0-10, 10 = severely constrained buildable land>,
  "geo_score_summary": "<one sentence explaining how this city-state pair received its scores>"
}}
"""
    try:
        result = llm_json(prompt)
        entry = {
            'City':  city,
            'State': state,
            'permitting_burden_index':        result.get('permitting_burden_index', np.nan),
            'hv_mv_readiness_gap_score':      result.get('hv_mv_readiness_gap_score', np.nan),
            'land_cost_proxy_score':          result.get('land_cost_proxy_score', np.nan),
            'buildable_land_constraint_score':result.get('buildable_land_constraint_score', np.nan),
            'geo_score_summary':              result.get('geo_score_summary', '')
        }
        GEO_CACHE[key] = entry
        geo_rows.append(entry)
    except Exception as e:
        print(f"  WARNING: Geo failed for {city}, {state}: {e}")
        entry = {'City': city, 'State': state,
                 'permitting_burden_index': np.nan, 'hv_mv_readiness_gap_score': np.nan,
                 'land_cost_proxy_score': np.nan, 'buildable_land_constraint_score': np.nan,
                 'geo_score_summary': 'ERROR'}
        GEO_CACHE[key] = entry
        geo_rows.append(entry)
    if (i + 1) % 10 == 0 or (i + 1) == len(unique_geo):
        print(f"  [{i+1}/{len(unique_geo)}] geo lookup batch complete")

# Save city_state_lookup.csv
lookup_df = pd.DataFrame(geo_rows)
lookup_df.to_csv(OUT_LOOKUP, index=False)
print(f"  Saved: {OUT_LOOKUP}")

# Join geo scores back to main df
df['_geo_key'] = list(zip(df['City'].astype(str), df['State'].astype(str)))
for col in ['permitting_burden_index','hv_mv_readiness_gap_score','land_cost_proxy_score','buildable_land_constraint_score']:
    df[col] = df['_geo_key'].map(lambda k: GEO_CACHE.get(k, {}).get(col, np.nan))

# ══════════════════════════════════════════════════════════════════════════════
# WRITE project_enriched.csv
# ══════════════════════════════════════════════════════════════════════════════
print("\nWriting project_enriched.csv ...")

DERIVED_COLS = [
    'time_to_power_months',
    'whitespace_power_density_w_sqft',
    'campus_power_density_w_sqft',
    'power_infra_disaggregation_score',
    'cable_multiplicity_burden_score',
    'whitespace_congestion_burden_score',
    'resiliency_topology_complexity_score',
    'future_readiness_pressure_score',
    'baseline_distribution_loss_mwh',
    'high_density_load_share_score',
    'high_density_load_share_explanation',
    'foak_commercial_access_score',
    'foak_commercial_access_explanation',
    'customer_type_label',
    'permitting_burden_index',
    'hv_mv_readiness_gap_score',
    'land_cost_proxy_score',
    'buildable_land_constraint_score',
]

out_cols = PK + DERIVED_COLS
enriched = df[out_cols].copy()
enriched.to_csv(OUT_ENRICHED, index=False)
print(f"  Saved: {OUT_ENRICHED}  ({len(enriched)} rows, {len(enriched.columns)} columns)")

# ══════════════════════════════════════════════════════════════════════════════
# WRITE variable_definitions.md
# ══════════════════════════════════════════════════════════════════════════════
print("\nWriting variable_definitions.md ...")

VAR_DEFS = """# Variable Definitions — Engine Lab GTM Enrichment

## Primary Key Columns
| Variable | Description |
|---|---|
| Project ID | Unique project identifier from source data |
| Project Name | Full project name |
| City | Project city |
| State | Project state |

---

## Calculated Variables
*Derived directly from existing columns. Returns NA if any required input is missing.*

| Variable | Formula / Logic |
|---|---|
| `time_to_power_months` | Months from April 2026 to projected power-on date. Power-on = Kick-Off date + Duration (months). Negative values mean the project powers on before April 2026. |
| `whitespace_power_density_w_sqft` | `Project Capacity (Numeric)` ÷ `campus_white_space_sqft`. Measures how intensely the usable white-space floor area is loaded per MW. |
| `campus_power_density_w_sqft` | `Project Capacity (Numeric)` ÷ `campus_sqft`. Measures total campus power density including grey space. |
| `power_infra_disaggregation_score` | 0–10 composite. +3.3 if `phase_index > 1` (multi-phase project), +3.3 if `Umbrella Project Count > 1` (campus shared with other projects), +3.4 proportional to `total_campus_expansion_sqft` vs. 99th-percentile value. Higher = more disaggregated power infrastructure. |
| `cable_multiplicity_burden_score` | 0–10. Estimated feeder count = `Project Capacity / 20 MW` scaled by `phase_index`. Normalised against 99th-percentile capacity. Higher = more feeder cables required, greater cabling burden. |
| `whitespace_congestion_burden_score` | 0–10 composite. Weighted sum of whitespace power density (normalised, ×5), `phase_index` contribution (×0.5, capped at 2.5), and high-density sector flag (×2.5). |
| `resiliency_topology_complexity_score` | 0–10 composite. Weighted contributions from `Umbrella Project Count` (×3), `phase_index` (×0.4, capped 2), `total_campus_expansion_sqft` (×3), and +2 if Project Type is an expansion. Higher = more complex resiliency topology. |
| `future_readiness_pressure_score` | 0–10. `(total_campus_expansion_sqft / campus_sqft)` contributes up to 7 points; `phase_index / 10` contributes up to 3 points. Higher = greater expansion pressure relative to current campus size. |
| `baseline_distribution_loss_mwh` | `Project Capacity (Numeric) × 0.04 × Duration (months)`. Estimates total MWh lost to distribution inefficiency over the build duration assuming a 4% transmission loss factor. |

---

## LLM-Scored Variables
*Populated via OpenAI Responses API (gpt-4o-mini) with web search enabled. Deduplicated before calling to minimise API cost.*

| Variable | Dedup Key | Scale | Description |
|---|---|---|---|
| `high_density_load_share_score` | (Owner Name, Sector, SIC Product) | 0–10 | How high-density the owner's compute workloads are (10 = extreme AI/HPC density). Scored by searching for the owner's known workload profile and facility specs. |
| `high_density_load_share_explanation` | — | Text | ≤20-word plain-English justification for the score above. |
| `foak_commercial_access_score` | Owner Name | 0–10 | How open the owner is to procuring from first-of-a-kind or novel infrastructure vendors (10 = very open). Scored by searching for procurement history, partnerships, and innovation pilots. |
| `foak_commercial_access_explanation` | — | Text | ≤20-word plain-English justification for the score above. |
| `customer_type_label` | Owner Name | Category | One of: `hyperscaler`, `neocloud`, `OEM`, `colo`, `enterprise`. Classifies the owner's market position. |

---

## Geo-Lookup Variables
*Populated via OpenAI Responses API with web search. One call per unique (City, State) pair. Results stored in `city_state_lookup.csv` and joined on (City, State).*

| Variable | Scale | Description |
|---|---|---|
| `permitting_burden_index` | 0–10 | How burdensome the local permitting process is for large infrastructure projects (10 = extremely slow/complex). |
| `hv_mv_readiness_gap_score` | 0–10 | Gap between current HV/MV grid infrastructure and what large-scale data center or industrial loads require (10 = major gap). |
| `land_cost_proxy_score` | 0–10 | Proxy for industrial land cost in the area (10 = extremely expensive). |
| `buildable_land_constraint_score` | 0–10 | How constrained the supply of buildable land is near the city (10 = severely constrained). |
"""

with open(OUT_VARDEFS, 'w', encoding='utf-8') as f:
    f.write(VAR_DEFS)
print(f"  Saved: {OUT_VARDEFS}")

print("\n=== Pipeline complete ===")
print(f"  project_enriched.csv    -> {OUT_ENRICHED}")
print(f"  city_state_lookup.csv   -> {OUT_LOOKUP}")
print(f"  variable_definitions.md -> {OUT_VARDEFS}")
