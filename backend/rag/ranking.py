"""
Hybrid ranking for retrieval: keyword (BM25) + vector search, steered by the
permit stage a question is about.

Vector search alone missed exact terms ("sanitary permit", "TIN") and let the
BIR Citizen's Charter - nearly half the index - crowd into unrelated answers.
"""
import math
import re
from collections import Counter, defaultdict
from typing import Dict, Iterable, List, Sequence, Set

from rag.document_loader import source_agency

_TOKEN = re.compile(r"[a-z0-9]+")

# Too common in this corpus to tell passages apart.
_STOPWORDS = {
    "the", "and", "for", "with", "from", "that", "this", "are", "was", "will",
    "shall", "may", "any", "all", "such", "its", "their", "his", "her", "not",
    "a", "an", "of", "or", "to", "in", "on", "at", "by", "is", "be", "as",
    "ang", "ng", "sa", "na", "mga", "at", "ay", "para", "kung", "ko", "ba",
    "what", "how", "do", "i", "my", "need", "can", "where", "saan", "paano",
}

# Words in a question that point at one permit stage. Matched on whole
# tokens, plus phrases checked against the raw lowercased text.
_AGENCY_TOKENS = {
    "bir": {"bir", "tin", "orus", "1901", "1903", "1905", "0605", "2551q",
            "resibo", "invoice", "receipts", "receipt", "percentage"},
    "dti": {"dti", "bnrs"},
    "barangay": {"barangay", "brgy"},
    "zoning": {"zoning", "locational", "cpdo", "variance"},
    "mayors_permit": {"mayor", "mayors", "bplo", "bpls", "sanitary",
                      "fsic", "bfp", "fire", "occupancy", "cedula", "renewal"},
}
_AGENCY_PHRASES = {
    "dti": ("business name", "pangalan ng negosyo"),
    "mayors_permit": ("business permit", "bureau of permits", "health certificate",
                      "business tax", "community tax"),
    "bir": ("books of account", "authority to print", "registration fee"),
    "zoning": ("land use",),
}

# Score multipliers once the question's stage is known.
MATCH_BOOST = 2.0
OFF_TOPIC_PENALTY = 0.35

# Reciprocal rank fusion constant; 60 is the value from the original paper.
RRF_K = 60

# No single file may fill more than this many of the returned slots.
MAX_PER_SOURCE = 2


def tokenize(text: str) -> List[str]:
    return [t for t in _TOKEN.findall((text or "").lower())
            if len(t) > 1 and t not in _STOPWORDS]


def detect_agencies(query: str) -> Set[str]:
    """Which permit stages a question is about; empty when it is general."""
    text = (query or "").lower()
    tokens = set(_TOKEN.findall(text))
    found = {agency for agency, words in _AGENCY_TOKENS.items() if tokens & words}
    found |= {agency for agency, phrases in _AGENCY_PHRASES.items()
              if any(p in text for p in phrases)}
    return found


class BM25:
    """Okapi BM25 over a fixed list of texts."""

    def __init__(self, texts: Sequence[str], k1: float = 1.5, b: float = 0.75):
        self.k1, self.b = k1, b
        self.doc_tokens = [Counter(tokenize(t)) for t in texts]
        self.doc_len = [sum(c.values()) for c in self.doc_tokens]
        self.avg_len = (sum(self.doc_len) / len(self.doc_len)) if self.doc_len else 0.0

        self.postings: Dict[str, List[int]] = defaultdict(list)
        for i, counts in enumerate(self.doc_tokens):
            for term in counts:
                self.postings[term].append(i)

        n = len(texts)
        self.idf = {
            term: math.log(1 + (n - len(docs) + 0.5) / (len(docs) + 0.5))
            for term, docs in self.postings.items()
        }

    def search(self, query: str, k: int) -> List[int]:
        scores: Dict[int, float] = defaultdict(float)
        for term in set(tokenize(query)):
            idf = self.idf.get(term)
            if idf is None:
                continue
            for i in self.postings[term]:
                tf = self.doc_tokens[i][term]
                norm = self.k1 * (1 - self.b + self.b * self.doc_len[i] / self.avg_len)
                scores[i] += idf * tf * (self.k1 + 1) / (tf + norm)
        return [i for i, _ in sorted(scores.items(), key=lambda kv: -kv[1])[:k]]


def fuse(rankings: Iterable[List[int]]) -> Dict[int, float]:
    """Reciprocal rank fusion of several best-first index lists."""
    scores: Dict[int, float] = defaultdict(float)
    for ranking in rankings:
        for rank, idx in enumerate(ranking):
            scores[idx] += 1.0 / (RRF_K + rank + 1)
    return scores


def rerank(
    scores: Dict[int, float],
    sources: Sequence[str],
    agencies: Set[str],
    k: int,
) -> List[int]:
    """
    Apply the stage boost and the per-source cap, returning the top k.

    `sources` maps each index to its source filename.
    """
    adjusted = {}
    for idx, score in scores.items():
        agency = source_agency(sources[idx])
        if agencies:
            if agency in agencies:
                score *= MATCH_BOOST
            elif agency != "general":
                score *= OFF_TOPIC_PENALTY
        adjusted[idx] = score

    picked: List[int] = []
    per_source: Counter = Counter()
    for idx in sorted(adjusted, key=lambda i: -adjusted[i]):
        if per_source[sources[idx]] >= MAX_PER_SOURCE:
            continue
        picked.append(idx)
        per_source[sources[idx]] += 1
        if len(picked) == k:
            break
    return picked
