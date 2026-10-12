import os
from typing import Tuple

try:
    from langchain_openai import OpenAIEmbeddings
except ImportError:  # The Ollama-only evaluator does not need LangChain.
    OpenAIEmbeddings = None

def extract_ticker_year(query_id: str) -> Tuple[str, str]:
    """
    Extracts ticker and year from a FinQA query ID.
    Format: TICKER/YEAR/page_N.pdf-idx (e.g., ADI/2009/page_49.pdf-1)
    """
    parts = query_id.split("/")
    if len(parts) >= 2:
        return parts[0], parts[1]
    return "UNKNOWN", "UNKNOWN"

def get_embedding_client() -> OpenAIEmbeddings:
    """
    Returns a configured OpenAIEmbeddings client using environment variables.
    Ensures that both the setup script and router use the exact same embedding space.
    """
    api_key = os.getenv("OPENROUTER_API_KEY")
    api_base = os.getenv("OPENROUTER_API_BASE")
    # NOTE: EMBEDDING_MODEL (default qwen/qwen3-embedding-8b) applies only to this OpenRouter path. The table finqa_evidence
    # was built with Ollama nomic-embed-text (768-d, raw text, no prefix), not with this model; finqa_evidence_qwen3 was
    # built by build_finqa_embedding_table.py.
    embedding_model_name = os.getenv("EMBEDDING_MODEL", "qwen/qwen3-embedding-8b")
    
    if not api_key:
        # Warning printed by the caller if needed
        return None

    if OpenAIEmbeddings is None:
        raise RuntimeError("langchain-openai is required for OpenRouter embeddings")
        
    return OpenAIEmbeddings(
        model=embedding_model_name,
        openai_api_base=api_base,
        api_key=api_key
    )


def exact_selectivity(conn, ticker: str, year: str) -> tuple[float, int, int]:
    """Exact per-query selectivity: rows matching (ticker, year) / all rows of finqa_evidence.

    Returns (selectivity, matching_rows, total_rows). Raises if the table is empty or nothing matches
    (a query whose filter matches no rows cannot be answered and must not get a made-up selectivity).
    """
    with conn.cursor() as cur:
        cur.execute("SELECT COUNT(*) FROM finqa_evidence")
        total = cur.fetchone()[0]
        cur.execute("SELECT COUNT(*) FROM finqa_evidence WHERE metadata->>'ticker' = %s AND metadata->>'year' = %s",
                    (ticker, year))
        match = cur.fetchone()[0]
    if total == 0:
        raise RuntimeError("finqa_evidence is empty")
    if match == 0:
        raise RuntimeError(f"no rows match ticker={ticker!r} year={year!r}")
    return match / total, match, total
