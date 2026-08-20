# FinQA Manual Review Cheat Sheet (refined)

## Step 0 — ALWAYS check this first

Before matching a question to any scenario below, look at its `gold_evidence_units`
value in the CSV (this is FinQA's own gold evidence-annotation count, not a guess):

| `gold_evidence_units` | Default tier | Scenario table to use |
|---|---|---|
| 1 | Narrow | 🟩 below |
| 2 | Boundary | 🟨 below |
| 3+ | Broad | 🟥 below |

The scenario descriptions exist to help you write a good rationale and catch cases
where the number is technically right but the *character* is off (see Step 0.5).
They are not a substitute for the count — if a scenario's wording and the actual
`gold_evidence_units` number disagree, **trust the number** and pick a scenario
from the correct tier's table instead, even if the wording elsewhere feels close.

## Step 0.5 — when to override the default tier

Override only when the evidence-unit count and the actual retrieval character
clearly diverge — e.g. a 2-evidence-unit question that also requires a 4-step
calculation spanning three distinct periods is describing more than "two related
facts," regardless of what the raw count says. When you override, write the
rationale explaining *why* the count undersells or oversells the real scope —
don't just relabel it silently.

---

## 🟩 NARROW (15 Qs) — `gold_evidence_units = 1`

**Definition:** Answer comes from one local fact or one tightly scoped comparison.

**Scenario 1: Single sentence calculation**
* **Scope:** `single text sentence`
* **Rationale:** `Requires extracting data from one localized sentence for a direct answer or single calculation.`

**Scenario 2: Single table row (Single value or constant math)**
* **Scope:** `single table row, one period`
* **Rationale:** `Requires extracting a single value or performing a one-step calculation (including with a constant) from one isolated line item.`

**Scenario 3: Single table row (Horizontal math or Boolean)**
* **Scope:** `single table row`
* **Rationale:** `Requires extracting values from a single isolated line item to perform a horizontal calculation across its columns (e.g., avg, min, max) or a boolean comparison.`

**Scenario 4: Single column vertical scan (e.g., highest/lowest in one year)**
* **Scope:** `single table column`
* **Rationale:** `Requires scanning a single column to locate one specific fact, isolated to one period (look for argmax, argmin, table_max, table_min).`
* **Note:** these operations can *feel* like they touch many rows, but FinQA's own gold annotation usually cites only the one winning cell — confirm `gold_evidence_units = 1` before using this scenario rather than assuming from the operation name alone.

---

## 🟨 BOUNDARY (20 Qs) — `gold_evidence_units = 2`

**Definition:** Requires two related facts, periods, or rows — or a modest calculation across a bounded part of the context.

**Scenario 1: Year-over-Year (YoY) Change in a table**
* **Scope:** `same line item, two consecutive periods`
* **Rationale:** `Requires extracting two related facts from the same row across different periods for a modest calculation.`

**Scenario 2: Two related text facts (Adjacent)**
* **Scope:** `two adjacent text spans`
* **Rationale:** `Requires locating and combining two related facts within the narrative text.`

**Scenario 3: Two related text facts (Dispersed)**
* **Scope:** `two dispersed text spans (exactly 2 facts — if the question spans 3+ periods or requires a multi-step calculation across them, use a Broad scenario instead)`
* **Rationale:** `Requires locating and combining exactly two related facts across non-contiguous text spans within the narrative text.`

**Scenario 4: Simple Hybrid (Table + Text)**
* **Scope:** `one table row + one text span`
* **Rationale:** `Requires combining a specific value from the table with a related fact found in the narrative text to perform a calculation.`

**Scenario 5: Two related table rows in the same year**
* **Scope:** `two line items, same period`
* **Rationale:** `Requires identifying two related rows within the same temporal column for a bounded comparison.`

**Scenario 6: Two line items across different periods**
* **Scope:** `two line items across two periods (confirm this is genuinely 2 evidence units, not 4 — if all four item×period cells must be individually retrieved, this is Broad Scenario 4 instead)`
* **Rationale:** `Requires extracting two related facts from different rows and periods to perform a modest calculation.`

---

## 🟥 BROAD (`gold_evidence_units = 3+`)

**Definition:** Requires three or more evidence units, and — like Narrow and Boundary —
is split by evidence adjacency (contiguous rows/spans vs. scattered ones) wherever
that split is real in the data, not just by modality or raw count.

**`Complex Hybrid (Massive Footprint)` is kept as its own named scenario** since it's
already applied in the current query selection — its scope below is the 4+-total-unit
hybrid case, in any table:text ratio.

**Scenario 1: Pure Table Broad — Contiguous Block**
* **Scope:** `three or more table rows/periods with consecutive indices (table_N, table_N+1, table_N+2...), no text evidence`
* **Rationale:** `Requires extracting values from an adjacent block of table rows — e.g. a running subtotal, a consecutive-year sequence, or a beginning-balance-through-ending-balance walk — to perform an aggregation or calculation across them.`
* **Note:** skews toward 2-step programs combining `add` + `divide` (sum the block, then take a share or average of it). Dominant ops: `add`, `divide`, `subtract`.

**Scenario 2: Pure Table Broad — Dispersed Rows**
* **Scope:** `three or more table rows/periods with non-consecutive indices, no text evidence`
* **Rationale:** `Requires locating and combining three or more table rows or periods that are scattered across the table (not adjacent line items or consecutive periods).`
* **Note:** skews toward 1-step programs, usually a single `divide` comparing two of the scattered values against each other (the "extra" evidence units are often there to establish which values are the right ones to compare, not to be combined arithmetically).

**Scenario 3: Pure Text Broad**
* **Scope:** `three or more text spans, no table evidence`
* **Rationale:** `Requires locating and combining three or more facts scattered across the narrative text.`
* **Note:** unlike pure-table, there's no contiguous variant of this in practice — consecutive sentences making the same point tend to get merged into a single gold span by FinQA's annotators, so a genuine 3+-span pure-text case is scattered by default. Skews 1-step, dominant op `divide`.

**Scenario 4: Table-Anchored Hybrid**
* **Scope:** `two table rows + one text span (total = 3 evidence units)`
* **Rationale:** `Requires combining two related table rows with one supporting fact from the narrative text — the table carries most of the evidence weight, text supplies one bounding or definitional fact.`
* **Note:** the two table rows are contiguous about a third of the time and dispersed the rest — check indices directly rather than assuming either way. Dominant op is `divide` (percentage-of / ratio questions), with `subtract` and `multiply` as secondary.

**Scenario 5: Text-Anchored Hybrid**
* **Scope:** `one table row + two text spans (total = 3 evidence units)`
* **Rationale:** `Requires combining one table value with two related facts drawn from the narrative text — text carries most of the evidence weight, the table supplies one anchoring number.`
* **Note:** the two text spans are dispersed more often than not (roughly 2:1 dispersed:contiguous). Dominant op is `divide`, same as Scenario 4.

**Scenario 6: Complex Hybrid (Massive Footprint)**
* **Scope:** `table and text evidence combined, 4 or more total units, in any table:text ratio (e.g. 2+2, 3+1, 1+3, 2+6)`
* **Rationale:** `Requires synthesizing a wide evidence footprint across both table and text — multiple table rows and/or multiple text spans — to locate the correct values, even if the resulting calculation itself is simple.`
* **Note:** program complexity does NOT track footprint size here — this scenario is 1–2 step programs just as often as the smaller hybrid scenarios above, so don't use step count as a signal for this scenario; use it only for the evidence-unit count and cross-modality spread. Both the table part and the text part are roughly split between contiguous and dispersed — again, check indices rather than assuming.