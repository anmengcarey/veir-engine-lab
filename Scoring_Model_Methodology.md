# VEIR GTM Ranking Model — Methodology & Weight Reference
**Version:** project_scored.xlsx (v2 model)
**Prepared for:** VEIR internal review / commercial team presentation

---

## 1. Purpose

This model ranks 554 large-scale U.S. data center construction projects to identify the **top 10–20 highest-priority targets** for VEIR's commercial engagement. Projects are scored on how well they fit VEIR's value proposition as a superconducting cable provider.

**Starting universe:** 1,048 raw Engine Lab projects
**Filter criteria applied:**
- Capacity ≥ 60 MW (large enough for VEIR's product to be relevant)
- Kick-off date ≤ 2036 (actionable within planning horizon)
- No extreme historical schedule slippage

**Remaining:** 554 projects across 24 U.S. states

---

## 2. Two Scoring Models — Why

VEIR sells into **two distinct deployment environments**, each governed by different engineering constraints and thus different project attributes:

| Model | Product Line | What it measures |
|---|---|---|
| **Indoor** | In-building power distribution cables | How power-dense and congested is the whitespace *inside* the building? |
| **Underground** | Campus-level external cable routing | How large, complex, and costly is the *campus* power infrastructure outside the building? |

The two models are scored **independently** — no cross-pollination. An attribute rated only for one model is fully excluded from the other. This separation was confirmed by VEIR (per Priyanshi's email: inside-weighted is the primary product; underground is secondary/nice-to-have ranking).

The **Indoor model is the primary deliverable.** The Underground model is a secondary lens.

---

## 3. Attributes, Weights, and Rationale

Weights derive directly from VEIR's Review sheet ratings:

| Review Rating | Weight |
|---|---|
| High | 1.0 |
| High/Med | 0.75 |
| Med | 0.5 |
| Med/Low | 0.35 |
| Low | 0.2 |
| — (not rated) | 0.0 (excluded) |

---

### 3.1 Timing

#### `time_to_power_months` — **Indoor: High (1.0) | Underground: High (1.0)**

**What it is:** Months from today (April 2026) to the project's projected completion date.

**Why it matters:** VEIR is at an early commercial stage. Projects energizing sooner give VEIR less time to get into the conversation — making them *more urgent to engage now*. Score is inverted (lower months → higher score).

**Data source:** `Completion` date column (100% coverage across all 554 projects). Earlier approach using Kick-Off + Duration was abandoned because 43% of projects had no Duration value.

**Range:** 47–143 months from April 2026.

---

### 3.2 Power Density (Inside the Building)

#### `whitespace_power_density_w_sqft` — **Indoor: High (1.0) | Underground: excluded**

**What it is:** Watts per square foot of *this phase's* new server floor space.

**Why it matters:** High density = high-performance compute (AI/GPU workloads). VEIR's superconducting cables carry significantly more current per cable than conventional copper — making them most valuable in high-density deployments where you'd otherwise need many parallel conventional feeders.

**Formula:** `Project Capacity (MW) × 1,000,000 ÷ New Building Size (sqft)`
Denominator is this phase's new server floor only (not cumulative campus whitespace, which would dilute expansion phases).

**Industry benchmark:** Standard DCs ≈ 100–200 W/sqft; AI/GPU clusters ≈ 300–600+ W/sqft.
Model median: **246 W/sqft** (consistent with mixed workload dataset).

#### `whitespace_congestion_burden_score` — **Indoor: Low (0.2) | Underground: excluded**

**What it is:** A 0–10 composite score of how congested the whitespace is, accounting for power density, number of phases, and sector type.

**Why it matters:** High congestion means cable management becomes more difficult — which is exactly where VEIR's high-ampacity cables (fewer cables needed) deliver measurable floor space savings. Weighted Low because this is partially captured by whitespace power density already.

---

### 3.3 Campus Scale (Outside the Building)

#### `campus_power_density_w_sqft` — **Indoor: excluded | Underground: High (1.0)**

**What it is:** Total power across *all phases of the campus* divided by total campus footprint (sqft).

**Why it matters:** For underground cable routing, the full campus power load determines how many high-ampacity feeders are needed from the substation to the buildings. Higher campus density = more feeder congestion = greater benefit from VEIR's cables.

**Formula:** `Sum of all phase capacities for this campus (MW) × 1,000,000 ÷ campus_sqft`
Numerator uses umbrella-summed capacity (not just one phase). Denominator uses the clean `campus_sqft` field (computed from all phases + grey space ratios), not the raw Existing Building Size field which had data quality issues.

#### `campus_size_sqft` — **Indoor: Med (0.5) | Underground: Med (0.5)**

**What it is:** Total physical footprint of the campus in square feet, including all building phases and grey space (mechanical, electrical, HVAC).

**Why it matters:** Larger campus = longer cable runs = more cable quantity = larger potential VEIR contract. Applies to both indoor and underground contexts.

**Source:** `campus_sqft`, computed in the pipeline using state-specific grey space ratios (18–25%).

#### `cable_multiplicity_burden_score` — **Indoor: excluded | Underground: Low (0.2)**

**What it is:** Estimated number of feeder cables needed based on total campus load and conventional cable ratings.

**Why it matters:** More feeders = greater complexity = bigger benefit from VEIR's high-ampacity cables (fewer cables to run, trench, and terminate). Weighted Low because it correlates strongly with campus power density.

#### `resiliency_topology_complexity_score` — **Indoor: excluded | Underground: Low (0.2)**

**What it is:** How complex the campus power topology is, based on number of phases, expansion type, and campus size.

**Why it matters:** More complex topologies require more sophisticated cable routing solutions — a potential differentiator for VEIR. Weighted Low as a secondary signal.

---

### 3.4 Commercial Viability

#### `high_density_load_share_score` — **Indoor: Med (0.5) | Underground: Med (0.5)**

**What it is:** 0–10 score of how likely this owner runs AI/HPC/GPU workloads. Scored 10 for confirmed GPU cluster operators.

**Why it matters:** High-density compute workloads drive the power density trends that make VEIR's cables most valuable. An owner already running AI workloads is also more likely to keep pushing density higher in future phases.

**Method:** LLM-scored via web search by owner name + sector type.

#### `foak_commercial_access_score` — **Indoor: Med (0.5) | Underground: Med (0.5)**

**What it is:** 0–10 score of how open this owner is to buying from first-of-a-kind (FOAK) vendors like VEIR.

**Why it matters:** VEIR is not yet a tier-1 established vendor. Owners with a history of innovation pilots, novel vendor partnerships, or early-adopter procurement culture are far more likely to engage with VEIR at this stage.

**Method:** LLM-scored via web search by owner name + recent procurement news.

#### `customer_type_label` → `customer_type_score` — **Indoor: Med (0.5) | Underground: Med (0.5)**

**What it is:** Owner classification: hyperscaler / neocloud / colo / enterprise / OEM.

**Why it matters:** VEIR's current commercial stage is better suited for non-hyperscalers. Hyperscalers (AWS, Google, Meta, Microsoft) build their own infrastructure solutions and are extremely difficult to penetrate as a FOAK vendor. Non-hyperscalers (enterprise-owned DCs, colos, neocloud providers) have more standard procurement processes and greater openness to novel vendors.

**Scoring method — binary:**
```
Non-hyperscaler (enterprise / neocloud / colo / OEM) → raw score 8
Hyperscaler (AWS, Google, Meta, Microsoft, etc.)     → raw score 2
```
We deliberately do not sub-rank within non-hyperscaler categories (e.g., enterprise vs colo), because VEIR has not provided evidence that one non-hyperscaler type is meaningfully more accessible than another. The binary encoding faithfully captures VEIR's stated preference without introducing unverified sub-hierarchies.

After percentile normalization across the dataset, the effective score gap is:
- Non-hyperscaler: ~7.0 / 10
- Hyperscaler: ~1.5 / 10

---

### 3.5 Location Factors

#### `permitting_burden_index` — **Indoor: Med (0.5) | Underground: High (1.0)**

**What it is:** 0–10 score of how difficult local permitting is for large infrastructure in this jurisdiction.

**Why it matters:** High permitting burden = longer pre-construction window = more lead time for VEIR to enter the conversation. For underground cable routing (which involves trenching, civil work, and utility coordination), permitting is especially consequential.

**Source:** Geo-lookup by state and county, based on known permitting difficulty tiers.

#### `hv_mv_readiness_gap_score` — **Indoor: excluded | Underground: Med (0.5)**

**What it is:** 0–10 score of the gap between existing grid infrastructure and what this data center requires.

**Why it matters:** A larger gap means more new HV/MV infrastructure must be built — more opportunity for VEIR to be specified into the design from the start, rather than retrofitting around existing conventional cable infrastructure.

#### `land_cost_proxy_score` — **Indoor: Med (0.5) | Underground: High/Med (0.75)**

**What it is:** 0–10 score of industrial land cost in the area.

**Why it matters:** High land cost = higher economic pressure to use space efficiently. VEIR's cables occupy less conduit space and fewer cable trays than conventional copper, making land-efficient cable routing more valuable in expensive markets.

#### `buildable_land_constraint_score` — **Indoor: Med/Low (0.35) | Underground: High/Med (0.75)**

**What it is:** 0–10 score of how constrained developable land is near the project.

**Why it matters:** Land-constrained sites have less room for wide cable routing corridors and underground trenching — making high-ampacity, space-efficient cables like VEIR's more attractive. Higher weight for underground because physical routing constraints are most acute outside the building.

#### `labor_cost_burden_score` — **Indoor: High (1.0) | Underground: High (1.0)**

**What it is:** 0–10 score of how burdensome construction labor is in each state, based on:
- Construction sector union density (%)
- State prevailing wage law strength (strong / moderate / none)

**Why it matters:** VEIR's superconducting cables have significantly higher ampacity than conventional copper — meaning **fewer cables** are needed to deliver the same power. Fewer cables = fewer cable pulls = fewer labor hours. In high-union, high-prevailing-wage states, each avoided cable pull saves substantially more money. This makes VEIR's labor cost savings argument strongest in states like California, Illinois, Pennsylvania, and Virginia.

**Method:** LLM-scored per state via web search (24 unique states, 24 API calls). Deduplicated by state to avoid redundant calls.

**Score compression applied:** Raw LLM scores ranged [2, 9] — a 7-point spread that overstated the marginal difference between high-union and low-union states. Compressed linearly to [4, 7] to reflect that VEIR delivers labor savings in all markets, with a moderate (not extreme) scaling factor:
```
compressed = 4.0 + (raw − 2.0) / 7.0 × 3.0
```

**Key state values (post-compression):**

| State | Raw Score | Compressed | Union Density | Prevailing Wage |
|---|---|---|---|---|
| California | 9.0 | 7.0 | 15.4% | Strong |
| Illinois | 8.0 | 6.6 | 12.8% | Strong |
| Ohio | 8.0 | 6.6 | 12.1% | Strong |
| Pennsylvania | 8.0 | 6.6 | 12.9% | Strong |
| Nevada | 7.5 | 6.4 | 12.4% | Strong |
| Virginia | 7.5 | 6.4 | 10.7% | Strong |
| Texas | 3.0 | 4.4 | 4.5% | None (repealed 2021) |
| Georgia | 3.0 | 4.4 | 5.6% | None |
| Arizona | 3.0 | 4.4 | 3.7% | None |

---

## 4. Normalization Method

All attributes are normalized to a **0–10 scale using percentile rank** before scoring:

```
normalized = percentile_rank(raw_value, across_554_projects) × 10
```

**Why percentile rank (not min-max normalization)?**
- Robust to outliers: one extreme outlier cannot compress all other scores into a tiny range
- Distribution-agnostic: works equally well for skewed power-law data (e.g., whitespace density) and more normally distributed data (e.g., permitting scores)
- Interpretable: a score of 7.0 means the project is in the 70th percentile for that attribute

For `time_to_power_months` (lower = better), the score is **inverted** after normalization:
```
inverted_score = 10 − percentile_rank_score
```
So a project completing in 47 months (most urgent) gets a score close to 10.

---

## 5. Weighted Scoring Formula

For each project, the final model score is a **NaN-safe weighted average** of normalized attribute scores:

```
Indoor Score = Σ (normalized_score_i × indoor_weight_i) / Σ indoor_weight_i
```

"NaN-safe" means: if a project is missing a value for an attribute (e.g., no LLM score was generated), that attribute is excluded from both the numerator and denominator for that project, rather than pulling its score toward zero.

---

## 6. Indoor Model — Weight Breakdown

Total weight sum: **7.05**

| Attribute | Weight | % of Model |
|---|---|---|
| Time to Power | 1.0 | 14.2% |
| Whitespace Power Density | 1.0 | 14.2% |
| Labor Cost Burden | 1.0 | 14.2% |
| High-Density Load Share | 0.5 | 7.1% |
| FOAK Commercial Access | 0.5 | 7.1% |
| Customer Type | 0.5 | 7.1% |
| Permitting Burden | 0.5 | 7.1% |
| Land Cost Proxy | 0.5 | 7.1% |
| Campus Size | 0.5 | 7.1% |
| Buildable Land Constraint | 0.35 | 5.0% |
| Whitespace Congestion | 0.2 | 2.8% |
| **Total** | **7.05** | **100%** |

**Excluded from Indoor model:** Campus Power Density, HV/MV Readiness Gap, Cable Multiplicity, Resiliency Complexity (all Outside-only attributes)

---

## 7. Underground Model — Weight Breakdown

Total weight sum: **9.40**

| Attribute | Weight | % of Model |
|---|---|---|
| Time to Power | 1.0 | 10.6% |
| Campus Power Density | 1.0 | 10.6% |
| Permitting Burden | 1.0 | 10.6% |
| Labor Cost Burden | 1.0 | 10.6% |
| Land Cost Proxy | 0.75 | 8.0% |
| Buildable Land Constraint | 0.75 | 8.0% |
| High-Density Load Share | 0.5 | 5.3% |
| FOAK Commercial Access | 0.5 | 5.3% |
| Customer Type | 0.5 | 5.3% |
| HV/MV Readiness Gap | 0.5 | 5.3% |
| Campus Size | 0.5 | 5.3% |
| Cable Multiplicity | 0.2 | 2.1% |
| Resiliency Complexity | 0.2 | 2.1% |
| **Total** | **9.40** | **100%** |

**Excluded from Underground model:** Whitespace Power Density, Whitespace Congestion (Inside-only attributes)

---

## 8. Calibration — 7 VEIR-Highlighted Projects

VEIR's manager identified 7 projects as appealing reference points. These were **not used to train the model** — they serve as a post-hoc validation check that the model's logic aligns with VEIR's commercial intuition.

| Project | State | Customer Type | Indoor Rank | Indoor %ile | Underground Rank | Underground %ile |
|---|---|---|---|---|---|---|
| Springfield DC Expansion Bldg 5 | IL | colo | #22 | Top 4% | #172 | Top 69% |
| Amarillo (Project Matador) Bldg 13 | TX | enterprise | #44 | Top 8% | #23 | Top 96% |
| Sulpher Springs Matrix DC Bldg 28 | TX | enterprise | #81 | Top 15% | #80 | Top 86% |
| Evanston (Aspen Mountain) PH II Bldg 4 | WY | hyperscaler | #108 | Top 20% | #288 | Top 52% |
| Maxwell Caldwell Valley Bldg 10 | VA | neocloud | #131 | Top 24% | #239 | Top 57% |
| Taylorsville DC Campus Bldg 7 | UT | colo | #149 | Top 27% | #189 | Top 66% |
| Yorkville (Project Cardinal) Bldg 8 | IL | enterprise | #226 | Top 59% | #46 | Top 92% |

**Summary:**
- Indoor average rank: **109 / 554 (top 20%)** — highlighted projects cluster meaningfully in the upper quintile
- 2 of 7 projects in Indoor top 50; 3 of 7 in Indoor top 100
- Yorkville ranks low on Indoor (#226) but very high on Underground (#46) — reflecting its large campus profile with relatively standard whitespace density
- Evanston (Aspen Mountain) is a hyperscaler, which correctly pulls it down in both models given VEIR's commercial stage preference

---

## 9. Attributes Excluded from Final Model

Three attributes were dropped after VEIR manager review (rated Low/Drop):

| Dropped Attribute | Reason |
|---|---|
| `power_infra_disaggregation_score` | Redundant with campus density metrics; not clearly tied to VEIR value prop |
| `future_readiness_pressure_score` | sqft expansion ratio was not meaningful enough to differentiate projects |
| `baseline_distribution_loss_mwh` | Duration-scaled MWh figure was not actionable for GTM prioritization |

---

## 10. Output Files

| File | Contents |
|---|---|
| `output/project_joined_v2.xlsx` | Full dataset: 554 projects × 63 attributes (source of truth) |
| `output/project_scored.xlsx` | Ranked output with 7 sheets (see below) |

**Sheets in project_scored.xlsx:**

| Sheet | Contents |
|---|---|
| Indoor Ranking | All 554 projects ranked by Indoor score |
| Underground Ranking | All 554 projects ranked by Underground score |
| Top 20 Indoor | Top 20 by Indoor score |
| Top 20 Underground | Top 20 by Underground score |
| Top 20 Unique Campuses | Top 20 deduplicated by campus (one phase per campus) |
| Weight Reference | Complete attribute weight table |
| Calibration Check | 7 VEIR-highlighted projects with scores and ranks |

Yellow highlighting = VEIR-highlighted projects (visible in all ranking sheets).
