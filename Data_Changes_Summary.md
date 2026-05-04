# VEIR Engine Lab — Data & Attribute Changes Summary
**Version:** project_joined_v2.xlsx
**Prepared for:** Internal review + VEIR presentation

---

## Background

We started with raw Engine Lab construction project data (**1,048 projects**), filtered down to **554 projects** that meet VEIR's minimum criteria:
- Capacity ≥ 60 MW (large enough for VEIR's product to matter)
- Kick-off date ≤ 2036 (actionable timeline)
- No extreme historical schedule slippage

Each project was then enriched with ~18 attributes to help score and rank which projects are the best fit for VEIR's commercial engagement.

---

## What the Attributes Are Measuring

The attributes fall into four categories:

### Category 1 — Timing
| Attribute | What it means |
|---|---|
| `time_to_power_months` | How many months from today (April 2026) until this project is expected to be energized. Lower = more urgent for VEIR to engage now. |

### Category 2 — Power Density (inside the building)
| Attribute | What it means |
|---|---|
| `whitespace_power_density_w_sqft` | How many watts are packed into each square foot of this building's new server floor space. High = high-density compute (AI/GPU workloads) → VEIR's cables carry more power per cable, saving space and cabling cost. |
| `whitespace_congestion_burden_score` | 0–10 composite score of how congested the white space is, accounting for power density, number of phases, and sector type. |

### Category 3 — Campus Scale (outside the building)
| Attribute | What it means |
|---|---|
| `campus_power_density_w_sqft` | Total power the entire campus will consume (all phases combined) divided by total campus footprint. Shows how power-intensive the full site is — relevant for VEIR's campus-level cable routing. |
| `campus_size_sqft` | Total physical footprint of the campus in square feet, including building space and infrastructure (mechanical, electrical, HVAC). |
| `cable_multiplicity_burden_score` | Estimated number of feeder cables needed. More feeders = greater complexity = bigger benefit from VEIR's high-ampacity cables (fewer cables needed). |
| `resiliency_topology_complexity_score` | How complex the campus power topology is, based on number of phases, expansion type, and campus size. |

### Category 4 — Commercial Viability
| Attribute | What it means |
|---|---|
| `high_density_load_share_score` | 0–10. How likely the owner runs high-density AI/HPC workloads (10 = confirmed GPU cluster operator). LLM-scored via web search by owner name + sector. |
| `foak_commercial_access_score` | 0–10. How open this owner is to buying from first-of-a-kind vendors like VEIR (10 = strong history of innovation pilots and novel vendor partnerships). LLM-scored. |
| `customer_type_label` | Classifies the owner as: hyperscaler / neocloud / colo / enterprise / OEM. VEIR's current stage is better suited for non-hyperscalers. |

### Category 5 — Location Factors
| Attribute | What it means |
|---|---|
| `permitting_burden_index` | 0–10. How difficult local permitting is for large infrastructure. High = slower approvals = more time for VEIR to get into the conversation early. |
| `hv_mv_readiness_gap_score` | 0–10. Gap between existing grid infrastructure and what this data center needs. High = more infrastructure work needed = more opportunity for VEIR. |
| `land_cost_proxy_score` | 0–10. Industrial land cost in the area. |
| `buildable_land_constraint_score` | 0–10. How constrained developable land is near the project. |
| `labor_cost_burden_score` | 0–10. Union density + prevailing wage strength in the state. **High = more valuable for VEIR** — because VEIR's cables require fewer cable pulls than conventional copper, so labor savings are larger in high-cost, high-union states. |
| `union_density_pct` | Estimated % of construction workers who are unionized in the state. |
| `prevailing_wage_law` | Whether the state has strong / moderate / no prevailing wage laws. |

---

## Changes Made in v2 (Based on VEIR Manager Review)

### Change 1 — `time_to_power_months`: Fixed coverage from 57% → 100%

**Original method:** Months from April 2026 to (Kick-Off date + Duration)
**Problem:** 43% of projects had no Duration value in the database, making the metric useless for nearly half the dataset. Projects with missing Duration were excluded, biasing results toward further-out projects (2034+).
**Fix:** Use the `Completion` date directly, which is populated for 100% of projects. This is the actual projected completion date for each phase, and requires no Duration.
**Result:** Every project now has a time_to_power value. Range is 47–143 months from April 2026.

---

### Change 2 — `whitespace_power_density_w_sqft`: Fixed denominator + corrected units

**Original method:** Project Capacity ÷ `campus_white_space_sqft`
**Problem:** `campus_white_space_sqft` accumulated floor area across *all phases* of the campus — not just the building being built. This diluted the density for expansion projects, making Phase 5 look the same density as Phase 1 even though each phase is identically sized.
**Fix (per VEIR review):** Use `New Building Size` as the denominator — the square footage of just *this phase's* new server floor being built.
**Also fixed:** Units corrected to true W/sqft (multiply MW by 1,000,000).
**Result:** Median 246 W/sqft, which aligns with industry benchmarks (standard DCs: 100–200 W/sqft; AI/GPU clusters: 300–600+ W/sqft).

---

### Change 3 — `campus_power_density_w_sqft`: Fixed numerator + fixed denominator

**Original method:** Single project capacity ÷ campus total sqft
**Problem (numerator):** Only counted one phase's capacity — if a campus has 10 phases each at 100 MW, it showed 100 MW instead of the true 1,000 MW campus load.
**Problem (denominator):** Used `Existing Building Size`, which had data quality issues — 111 greenfield campuses had 0 sqft (no existing buildings), and Leesburg Spring Valley had a data entry error of 1,512 sqft (roughly the size of an apartment) instead of the real ~1.5M sqft, producing a completely non-physical result of **378,442 W/sqft**.
**Fix:**
- Numerator: sum all Project Capacity values within the same Umbrella (full campus load)
- Denominator: `campus_sqft`, a clean value computed in the pipeline from all phases + grey space ratios, with no data quality issues

**Result:** Median 208 W/sqft, max 9,950 W/sqft (large multi-phase campuses). No non-physical outliers.

---

### Change 4 — Dropped 3 Low-Value Attributes

Per VEIR manager review (rated Low/Drop):

| Dropped Attribute | Why |
|---|---|
| `power_infra_disaggregation_score` | Redundant with campus density metrics; not clearly tied to VEIR's value prop |
| `future_readiness_pressure_score` | The sqft expansion ratio was not meaningful enough to differentiate projects |
| `baseline_distribution_loss_mwh` | Duration-scaled MWh figure was not actionable for GTM prioritization |

---

### Change 5 — Added `campus_size_sqft` (new)

**What it is:** Total campus footprint in square feet, including all building phases and grey space (mechanical rooms, electrical infrastructure, HVAC).
**Why:** VEIR requested this as a direct measure of campus scale. Larger campus = longer cable runs = more cable quantity = larger VEIR contract potential.
**Source:** Directly taken from `campus_sqft`, computed in the pipeline using state-specific grey space ratios (18–25%).

---

### Change 6 — Added `labor_cost_burden_score` (new, High priority)

**What it is:** A 0–10 score of how burdensome construction labor is in each state, based on:
- Construction sector union density (%)
- State prevailing wage law strength (strong / moderate / none)
- Local construction labor market conditions

**Why this matters for VEIR:** VEIR's superconducting cables have significantly higher ampacity than conventional copper cables — meaning you need *fewer cables* to deliver the same power. Fewer cables = fewer cable pulls = fewer labor hours. In high-union, high-wage states, this labor reduction translates to greater dollar savings for the customer, making VEIR's value proposition stronger and easier to quantify.

**Method:** LLM web search, deduplicated by state (24 unique states → 24 API calls).

**Key results:**
| State | Score | Union Density | Prevailing Wage |
|---|---|---|---|
| California | 9.0 | 15.4% | Strong |
| Illinois | 8.0 | 12.8% | Strong |
| Ohio | 8.0 | 12.1% | Strong |
| Pennsylvania | 8.0 | 12.9% | Strong |
| Minnesota | 8.0 | — | Strong |
| Nevada | 7.5 | 12.4% | Strong |
| Virginia | 7.5 | 10.7% | Strong |
| Texas | 3.0 | 4.5% | None (repealed 2021) |
| Georgia | 3.0 | 5.6% | None |
| Arizona | 3.0 | 3.7% | None |

---

## What Was NOT Changed

The following attributes were reviewed and kept as-is (rated Low weight — retained for potential use in ranking model):
- `cable_multiplicity_burden_score`
- `resiliency_topology_complexity_score`
- `whitespace_congestion_burden_score` *(recalculated with corrected whitespace density values)*

LLM-scored commercial attributes were not re-scored:
- `high_density_load_share_score` / `foak_commercial_access_score` / `customer_type_label`

Geo-lookup attributes were not re-scored:
- `permitting_burden_index` / `hv_mv_readiness_gap_score` / `land_cost_proxy_score` / `buildable_land_constraint_score`

---

## Output File

**`output/project_joined_v2.xlsx`**
- 554 projects × 63 attributes
- Sheet `project_joined_v2`: full dataset
- Sheet `v2_changes`: machine-readable log of all changes

---

## Next Steps

1. Build a weighted scoring model using the 7 VEIR-highlighted projects as calibration anchors
2. Assign weights to each attribute category based on VEIR review importance ratings (High / Med / Low)
3. Produce a ranked shortlist of top 10–20 projects for commercial engagement
