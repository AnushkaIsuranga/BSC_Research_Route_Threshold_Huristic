"""Shared constants and helpers for the EDGAR-CORPUS build (Phase F).

Source: EDGAR-CORPUS (Loukas et al., ECONLP 2021), Hugging Face dataset eloukas/edgar-corpus at a pinned revision.
The downloaded files are untrusted data: they live only in data/raw/edgar_corpus/ and are read as JSON lines here;
nothing in that folder is executed or imported.
"""

from __future__ import annotations

import hashlib
import json
from pathlib import Path

from src import PROJECT_ROOT

RAW_DIR = PROJECT_ROOT / "data/raw/edgar_corpus"
HF_REPO = "eloukas/edgar-corpus"
HF_REVISION = "7e90f0f342569b35213445f809cfaf3b91f9964f"
YEARS = (2018, 2019, 2020)
SPLITS = ("train", "validate", "test")
# sha256 = the git-LFS oid listed by the Hugging Face API for HF_REVISION
EXPECTED_SHA256 = {
    "2018/test.jsonl": "f66ce0755e86fed09b986905c59962cfed9b28a523cdce57723075157c9c44c7",
    "2018/train.jsonl": "e81d3d4d380f00a5bc965f5f1d55a882d5f5c7bfdc905530b0b183a6124968ef",
    "2018/validate.jsonl": "f0c62c3cec722a9e7f1e92ceb81e7b213bd6dacbd8b7ab4869207109ac56666e",
    "2019/test.jsonl": "abb9947646fbc32a48dcb56f35f668fcef2f628307f6d7c14cc5c2fc14466042",
    "2019/train.jsonl": "9f05959fe52a99536c474c8cf61f2197e9bbce6c16b2a1c2dd4a81622e0a8d91",
    "2019/validate.jsonl": "9b220d29c23341cc9fa528dd81bdd06484aa246ad478231f57bb0097dd03b07e",
    "2020/test.jsonl": "5409efc829acfde7e1f96b93ff52be0b55e22dd47e2495986ce765f556538f72",
    "2020/train.jsonl": "ee605e79b4ac9f91d6571228b3ad4c4db4509e741efba4438c679433a104f2bc",
    "2020/validate.jsonl": "89bba2f87645bf0e6639204987fe71434fcf6d63222cee7d92f85e192a2d9f59",
}
TOKENIZER_REPO = "Qwen/Qwen3-Embedding-8B"
TOKENIZER_REVISION = "1d8ad4ca9b3dd8059ad90a75d4983776a23d44af"
TOKENIZER_SHA256 = "83cdf8c3a34f68862319cb1810ee7b1e2c0a44e0864ae930194ddb76bb7feb8d"
TOKENIZER_PATH = RAW_DIR / "qwen3_tokenizer/tokenizer.json"

KEEP_SECTIONS = ("1", "1A", "7", "7A", "8")   # section label as stored in edgar_chunks.section
SEED = 20261031
CHUNK_TOKENS, OVERLAP_TOKENS, SNAP_TOKENS = 400, 50, 40
EMBED_MODEL, EMBED_DIM = "qwen/qwen3-embedding-8b", 1024
TABLE = "edgar_chunks"


def sha256_file(path: Path, bufsize: int = 1 << 22) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as f:
        while b := f.read(bufsize):
            h.update(b)
    return h.hexdigest()


def text_hash(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def load_tokenizer(path: Path = TOKENIZER_PATH):
    """The Qwen3-Embedding-8B tokenizer (tokenizers library), checked against its pinned sha256."""
    from tokenizers import Tokenizer
    if sha256_file(path) != TOKENIZER_SHA256:
        raise RuntimeError(f"{path} does not match the pinned tokenizer sha256")
    return Tokenizer.from_file(str(path))


def read_record(path: Path, offset: int) -> dict:
    """One JSON record of a downloaded file, by byte offset (offsets come from the source-check index)."""
    with open(path, "rb") as f:
        f.seek(offset)
        return json.loads(f.readline())


def _boundary(text: str, offsets, j: int) -> bool:
    """Token j starts a word: its first character is whitespace or follows whitespace."""
    s = offsets[j][0]
    return s == 0 or text[s].isspace() or text[s - 1].isspace()


def chunk_spans(text: str, offsets, size: int = CHUNK_TOKENS, overlap: int = OVERLAP_TOKENS, snap: int = SNAP_TOKENS):
    """Token windows [(start_tok, end_tok)] of at most `size` tokens; consecutive windows share about `overlap` tokens.
    Window ends (and next starts) are moved back by at most `snap` tokens to a word boundary so words are not split."""
    n = len(offsets)
    spans, start = [], 0
    while start < n:
        end = min(start + size, n)
        if end < n:
            for j in range(end, max(start + 1, end - snap), -1):
                if _boundary(text, offsets, j):
                    end = j
                    break
        spans.append((start, end))
        if end >= n:
            break
        nxt = max(end - overlap, start + 1)
        for j in range(nxt, max(start + 1, nxt - snap), -1):
            if _boundary(text, offsets, j):
                nxt = j
                break
        start = nxt
    return spans


def chunk_section(text: str, tokenizer) -> list[dict]:
    """Chunks of one section (never crossing sections): text sliced from the original string at token offsets."""
    if not text or not text.strip():
        return []
    enc = tokenizer.encode(text, add_special_tokens=False)
    offs = enc.offsets
    out = []
    for a, b in chunk_spans(text, offs):
        piece = text[offs[a][0]:offs[b - 1][1]].strip()
        if piece:
            out.append({"text": piece, "n_tokens": b - a})
    return out


def n_chunks_for(n_tokens: int, size: int = CHUNK_TOKENS, overlap: int = OVERLAP_TOKENS) -> int:
    """Chunk count without word snapping (used for the projection)."""
    if n_tokens <= 0:
        return 0
    if n_tokens <= size:
        return 1
    return 1 + -(-(n_tokens - size) // (size - overlap))
