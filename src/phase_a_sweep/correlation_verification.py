"""Generate a notebook that verifies correlation-tier table construction."""

from __future__ import annotations

import nbformat as nbf

from src import NOTEBOOKS_DIR, ensure_dir


def build_correlation_verification_notebook():
    nb = nbf.v4.new_notebook()

    markdown_intro = """# Selectivity Sweep - Correlation Verification
This notebook verifies that the synthetic metadata scrambling (derangement) hit the target correlation percentages (100%, 75%, 50%, 25%, 0%) for the `hm_clothes` tables.

It reads the original categories directly from the benchmark payload file and cross-references them with the actual stored categories in each isolated PostgreSQL table.
"""

    code_setup = """import json
import os
import psycopg2
import pandas as pd
import matplotlib.pyplot as plt

conn = psycopg2.connect(
    dbname=os.getenv("POSTGRES_DB", "vector_db"),
    user=os.getenv("POSTGRES_USER", "postgres"),
    password=os.getenv("POSTGRES_PASSWORD", "mysecretpassword"),
    host=os.getenv("POSTGRES_HOST", "127.0.0.1"),
    port=os.getenv("POSTGRES_HOST_PORT", "5433"),
)

data_dir = os.path.join("ann-filtering-benchmark-datasets", "data")
payloads_path = os.path.join(data_dir, "payloads.jsonl")

with open(payloads_path, encoding="utf-8") as f:
    payloads = [json.loads(line) for line in f]

original_categories = [p.get("department_name", "Unknown") for p in payloads]
print(f"Loaded {len(original_categories)} original categories.")
"""

    code_verify = """tables = ["hm_clothes_100", "hm_clothes_75", "hm_clothes_50", "hm_clothes_25", "hm_clothes_0"]
results = []

for table in tables:
    query = f"SELECT vector_id, category FROM {table} ORDER BY vector_id ASC"
    df_db = pd.read_sql(query, conn)
    db_categories = df_db["category"].tolist()

    matches = sum(1 for orig, db in zip(original_categories, db_categories) if orig == db)
    match_percentage = (matches / len(original_categories)) * 100

    results.append({
        "Table": table,
        "Target Correlation (%)": int(table.split("_")[-1]),
        "Actual Correlation (%)": round(match_percentage, 2),
        "Exact Matches": matches,
    })

results_df = pd.DataFrame(results)
display(results_df)
"""

    code_scatter = """fig, axes = plt.subplots(1, 5, figsize=(25, 5), sharex=True, sharey=True)
fig.suptitle("Category Migration (Original vs Assigned) Across Correlation Tiers", fontsize=16)

unique_categories = sorted(set(original_categories))
cat_to_int = {category: idx for idx, category in enumerate(unique_categories)}
orig_ints = [cat_to_int[category] for category in original_categories]

for idx, table in enumerate(tables):
    query = f"SELECT vector_id, category FROM {table} ORDER BY vector_id ASC"
    df_db = pd.read_sql(query, conn)
    db_categories = df_db["category"].tolist()

    unknown_cats = set(db_categories) - set(unique_categories)
    assert not unknown_cats, f"Found corrupted/unknown categories in {table}: {unknown_cats}"

    db_ints = [cat_to_int[category] for category in db_categories]

    ax = axes[idx]
    ax.scatter(orig_ints, db_ints, alpha=0.01, s=1, color="blue")
    target_pct = int(table.split("_")[-1])
    ax.set_title(f"{table}\\nCorrelation: {target_pct}%")
    ax.set_xlabel("Original Category ID")
    if idx == 0:
        ax.set_ylabel("Assigned Category ID")

plt.tight_layout()
plt.show()
"""

    nb["cells"] = [
        nbf.v4.new_markdown_cell(markdown_intro),
        nbf.v4.new_code_cell(code_setup),
        nbf.v4.new_code_cell(code_verify),
        nbf.v4.new_code_cell(code_scatter),
    ]
    return nb


def write_correlation_verification_notebook(path=NOTEBOOKS_DIR / "correlation_verification.ipynb") -> None:
    ensure_dir(path.parent)
    with path.open("w", encoding="utf-8") as output:
        nbf.write(build_correlation_verification_notebook(), output)
    print(f"Created {path} successfully.")


def main() -> None:
    write_correlation_verification_notebook()

if __name__ == "__main__":
    main()
