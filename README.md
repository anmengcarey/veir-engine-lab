# VEIR Engine Lab — GTM Analysis Pipeline

Go-to-market analysis pipeline built for VEIR, a superconductor company. The goal is to identify the highest-priority data center and industrial construction projects in the US to target for early commercial engagement.

The pipeline converts raw proprietary project-index PDFs into a scored, enriched dataset ready for prioritization and outreach.

---

## Dataset Origin

The raw data comes from **Engine Lab** — a proprietary construction project intelligence database. VEIR receives periodic exports as two parallel sets of PDFs:

| File pattern | Content |
|---|---|
| `Engine Lab #.pdf` | Project index — one row per project with summary fields (project name, owner, location, TIV, status) |
| `Engine Lab Report #.pdf` | Detailed project report — one report per project with technical fields (capacity, building size, timelines, sector, SIC code) |

A total of 11 index files and 11 report files were parsed, yielding **1,048 raw project rows** before any filtering.

---

## Pipeline Overview

```
data/
  Engine Lab 1-11.pdf          ─┐
  Engine Lab Report 1-11.pdf   ─┘─► parse_engine_lab.py ──► engine_lab_output.csv (1,048 rows)
                                                                     │
                                              engine_lab_data_processing.ipynb
                                          (EDA · filtering · imputation · campus calc)
                                                                     │
                                                     engine_lab_filtered.csv (554 rows)
                                                                     │
                                                          enrich_gtm.py
                                                  (derived vars · LLM scoring · geo lookup)
                                                                     │
                                                       project_enriched.csv
                                                                     │
                                              join_filtered_enriched.ipynb
                                                                     │
                                                        project_joined.csv / .xlsx
```

---

## Step 1 — PDF Parsing (`scripts/parse_engine_lab.py`)

Each index PDF encodes projects in a fixed 3–4 row block structure per project. The parser detects block boundaries by scanning for `Industrial Manufacturing` rows and then reads the date row, project-ID row, and optional umbrella row in order, handling page-break orphan rows automatically.

Report PDFs contain multiple project reports per file. The parser groups pages by detecting `Capital PEC Report  Project ID:` headers, then extracts ~20 fields per project via regex.

Both sets are merged on `Project ID`. Where a field appears in both sources, the index value is preferred and the report value is used as a fallback. The result is written to `output/engine_lab_output.csv`.

---

## Step 2 — EDA, Filtering & Imputation (`notebooks/engine_lab_data_processing.ipynb`)

Starting from 1,048 raw rows, the notebook applies a sequence of filters and transformations to produce a clean, analysis-ready dataset.

### Filters applied (in order)

| Filter | Rows kept | Rationale |
|---|---|---|
| Kickoff slippage ≤ 60 months (or missing) | 1,033 | Projects with extreme historical slippage are unlikely to execute on schedule |
| Kick-Off date present and ≤ 2036 | 953 | Removes projects too far out to be actionable |
| Project Capacity ≥ 60 MW | **554** | Focuses beachhead on the top half by capacity — minimum scale for VEIR's product |

### Missing value imputation

Three key numeric variables — `New Building Size`, `Project Capacity`, and `Existing Building Size` — have partial coverage. They are imputed via **linear regression** using the remaining two as features along with `TIV (USD)`.

For each missing row:
- If the project's state has **≥ 50% missing** for the target variable, the regression is trained on the full national dataset.
- Otherwise, it is trained on within-state observations only.
- Feature subsets are tried from largest to smallest; the first subset with at least 2 training rows wins.

### Campus size calculation

Projects sharing the same `Umbrella Project ID` belong to the same physical campus and are built in sequential phases. For each phase, the cumulative campus footprint is computed:

```
IT_campus_space  = existing_building_size
                 + cumulative_sum(new_building_size for all prior phases)
                 + new_building_size (current phase)

campus_sqft      = IT_campus_space × (1 + grey_space_ratio[state])
campus_white_space_sqft = IT_campus_space
campus_grey_space_sqft  = IT_campus_space × grey_space_ratio[state]
```

Grey space ratios (18–25%, state-specific) account for mechanical rooms, power infrastructure, and circulation. Projects with no umbrella ID are treated as single-phase standalone campuses.

A `phase_index` (0-based) is also assigned by sorting projects within each umbrella by kick-off date.

---

## Step 3 — Enrichment (`scripts/enrich_gtm.py`)

Reads `engine_lab_filtered.csv` and appends three classes of variables.

### Calculated variables (no API calls)

Derived arithmetically from existing columns. Returns `NaN` if any required input is missing.

| Variable | Formula |
|---|---|
| `time_to_power_months` | Months from April 2026 to `Kick-Off + Duration`. Negative = already powered on. |
| `whitespace_power_density_w_sqft` | `Project Capacity (MW)` ÷ `campus_white_space_sqft` |
| `campus_power_density_w_sqft` | `Project Capacity (MW)` ÷ `campus_sqft` |
| `power_infra_disaggregation_score` | 0–10 composite: +3.3 if multi-phase, +3.3 if multi-project campus, +3.4 proportional to expansion sqft vs. 99th percentile |
| `cable_multiplicity_burden_score` | 0–10: estimated feeder count (`capacity / 20 MW`) scaled by phase, normalised to 99th percentile |
| `whitespace_congestion_burden_score` | 0–10: weighted sum of whitespace power density (×5), phase contribution (×0.5, capped 2.5), high-density sector flag (×2.5) |
| `resiliency_topology_complexity_score` | 0–10: contributions from umbrella project count (×3), phase (×0.4, capped 2), expansion sqft (×3), +2 if expansion project type |
| `future_readiness_pressure_score` | 0–10: expansion-to-campus ratio contributes up to 7 pts; phase normalised contributes up to 3 pts |
| `baseline_distribution_loss_mwh` | `Capacity (MW) × 0.04 × Duration (months)` — estimates MWh lost to a 4% transmission loss factor over build duration |

### LLM-scored variables (OpenAI `gpt-4o-mini` + web search)

Populated via the OpenAI Responses API with the `web_search_preview` tool enabled. API calls are **deduplicated before execution** to minimise cost — the model is called once per unique key and results are joined back to all matching rows.

| Variable | Dedup key | Scale | What the LLM searches for |
|---|---|---|---|
| `high_density_load_share_score` | (Owner Name, Sector, SIC Product) | 0–10 | Owner's known compute workload profile and facility specs |
| `high_density_load_share_explanation` | — | Text (≤20 words) | Plain-English justification |
| `foak_commercial_access_score` | Owner Name | 0–10 | Procurement history, vendor partnerships, innovation pilots |
| `foak_commercial_access_explanation` | — | Text (≤20 words) | Plain-English justification |
| `customer_type_label` | Owner Name | Category | Classifies as: `hyperscaler`, `neocloud`, `OEM`, `colo`, or `enterprise` |

### Geo-lookup variables (one call per unique city/state)

The model searches for local infrastructure and regulatory context for each unique `(City, State)` pair. Results are cached in `output/city_state_lookup.csv` and joined back on `(City, State)`.

| Variable | Scale | What is scored |
|---|---|---|
| `permitting_burden_index` | 0–10 | Speed and complexity of local permitting for large infrastructure |
| `hv_mv_readiness_gap_score` | 0–10 | Gap between existing HV/MV grid and what large data center loads require |
| `land_cost_proxy_score` | 0–10 | Industrial land cost in the area |
| `buildable_land_constraint_score` | 0–10 | Supply constraint on buildable land near the city |

---

## Step 4 — Join (`notebooks/join_filtered_enriched.ipynb`)

Joins `engine_lab_filtered.csv` and `project_enriched.csv` on the primary key columns (`Project ID`, `Project Name`, `City`, `State`) to produce the final analysis-ready dataset at `output/project_joined.csv` and `output/project_joined.xlsx`.

---

## Setup

**Requirements:** Python 3.9+

```bash
pip install pandas openpyxl pdfplumber python-dotenv openai scikit-learn numpy
```

**Environment:**

Copy `.env.example` to `.env` and fill in your key:

```bash
cp .env.example .env
# then edit .env:
OPENAI_API_KEY=sk-proj-...
```

The enrichment script requires an OpenAI account with the `web_search_preview` tool enabled (available on paid tiers).

**Run the pipeline:**

```bash
# 1. Parse PDFs → engine_lab_output.csv
python scripts/parse_engine_lab.py

# 2. EDA, filtering, imputation → engine_lab_filtered.csv
#    Open and run: notebooks/engine_lab_data_processing.ipynb

# 3. Enrich with derived vars + LLM scores → project_enriched.csv
python scripts/enrich_gtm.py

# 4. Final join → project_joined.csv / .xlsx
#    Open and run: notebooks/join_filtered_enriched.ipynb
```

---

## Repository Structure

```
veir-engine-lab/
├── data/                          # Raw Engine Lab PDFs (not in git)
├── scripts/
│   ├── parse_engine_lab.py        # PDF parser (step 1)
│   ├── enrich_gtm.py              # Enrichment pipeline (step 3)
│   └── websearch_test.py          # Verifies OpenAI web search access
├── notebooks/
│   ├── engine_lab_data_processing.ipynb   # EDA + filtering + imputation (step 2)
│   └── join_filtered_enriched.ipynb       # Final join (step 4)
├── output/                        # Generated CSVs and XLSX files (not in git)
│   ├── engine_lab_output.csv      # Raw parsed output (1,048 rows)
│   ├── engine_lab_filtered.csv    # After filtering (554 rows)
│   ├── project_enriched.csv       # LLM-enriched variables
│   ├── project_joined.csv         # Final joined dataset
│   ├── city_state_lookup.csv      # Geo scores cache
│   └── variable_definitions.md   # Auto-generated variable reference
├── logs/                          # Script run logs (not in git)
├── .env                           # Local secrets — never committed
├── .env.example                   # Template for required env vars
└── .gitignore
```

---

## Variable Reference

See [`output/variable_definitions.md`](output/variable_definitions.md) for the full variable dictionary (auto-regenerated each time `enrich_gtm.py` runs).
