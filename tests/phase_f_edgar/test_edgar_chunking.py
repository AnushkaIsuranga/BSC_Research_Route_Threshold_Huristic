"""Phase F chunker: window sizes, overlap, word snapping, no empty chunks (whitespace tokenizer stand-in; no downloaded data)."""

import re

from src.phase_f_edgar import common as C


class _Enc:
    def __init__(self, text):
        self.offsets = [m.span() for m in re.finditer(r"\s*\S+", text)]
        self.ids = list(range(len(self.offsets)))


class WordTok:
    def encode(self, text, add_special_tokens=False):
        return _Enc(text)


def test_n_chunks_for():
    assert C.n_chunks_for(0) == 0
    assert C.n_chunks_for(1) == 1
    assert C.n_chunks_for(400) == 1
    assert C.n_chunks_for(401) == 2
    assert C.n_chunks_for(750) == 2
    assert C.n_chunks_for(751) == 3


def test_spans_cover_text_with_overlap_and_bounded_size():
    text = " ".join(f"w{i}" for i in range(2000))
    offs = _Enc(text).offsets
    spans = C.chunk_spans(text, offs)
    assert spans[0][0] == 0 and spans[-1][1] == len(offs)
    assert all(b - a <= C.CHUNK_TOKENS for a, b in spans)
    for (a1, b1), (a2, b2) in zip(spans, spans[1:]):
        assert a1 < a2 < b1 < b2                       # progress and overlap
        assert b1 - a2 <= C.OVERLAP_TOKENS + C.SNAP_TOKENS


def test_chunks_do_not_split_words_and_are_nonempty():
    text = "Revenue was $1,234 million in 2019.\n" * 300
    chunks = C.chunk_section(text, WordTok())
    assert chunks and all(c["text"].strip() for c in chunks)
    words = set(text.split())
    for c in chunks:
        assert c["text"].split()[0] in words and c["text"].split()[-1] in words
        assert c["n_tokens"] <= C.CHUNK_TOKENS


def test_empty_section_gives_no_chunks():
    assert C.chunk_section("", WordTok()) == []
    assert C.chunk_section("   \n ", WordTok()) == []


def test_text_hash_is_sha256_of_utf8():
    assert C.text_hash("abc") == "ba7816bf8f01cfea414140de5dae2223b00361a396177a9cb410ff61f20015ad"
