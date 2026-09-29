"""Repeatable local retrieval evaluation for the BJJ/journal search index."""
from __future__ import annotations

import argparse
import json
import math
import re
from pathlib import Path

from embeddings import HashEmbedder, LocalBGEEmbedder
from bjj import SEARCH_STOP_WORDS


ROOT = Path(__file__).resolve().parent
DEFAULT_DATASET = ROOT / "tests" / "fixtures" / "bjj_retrieval_eval.json"


def cosine(left, right):
    return sum(a * b for a, b in zip(left, right))


def lexical_score(query, passage):
    query_terms = set(re.findall(r"[a-z0-9]+", query.lower())) - SEARCH_STOP_WORDS
    passage_terms = set(re.findall(r"[a-z0-9]+", passage.lower()))
    return len(query_terms & passage_terms) / math.sqrt(max(1, len(query_terms) * len(passage_terms)))


def rankings(embedder, documents, queries, hybrid=False):
    document_vectors = embedder.embed_documents([document["text"] for document in documents])
    results = []
    for query in queries:
        query_vector = embedder.embed_query(query["text"])
        semantic = sorted(
            ((cosine(query_vector, vector), document["id"]) for document, vector in zip(documents, document_vectors)),
            reverse=True,
        )
        if not hybrid:
            results.append([identifier for _, identifier in semantic])
            continue
        lexical = sorted(((lexical_score(query["text"], document["text"]), document["id"]) for document in documents), reverse=True)
        scores = {}
        for rank, (_, identifier) in enumerate(semantic, 1):
            scores[identifier] = scores.get(identifier, 0) + 0.85 / (60 + rank)
        for rank, (score, identifier) in enumerate(lexical, 1):
            if score:
                scores[identifier] = scores.get(identifier, 0) + 0.15 / (60 + rank)
        results.append(sorted(scores, key=scores.get, reverse=True))
    return results


def metrics(ranked, queries):
    reciprocal_ranks = []
    hits = {1: 0, 3: 0, 5: 0}
    for ranking, query in zip(ranked, queries):
        relevant = set(query["relevant"])
        first = next((position for position, identifier in enumerate(ranking, 1) if identifier in relevant), None)
        reciprocal_ranks.append(1 / first if first else 0)
        for cutoff in hits:
            hits[cutoff] += int(bool(relevant & set(ranking[:cutoff])))
    count = len(queries)
    return {"queries": count, "mrr": round(sum(reciprocal_ranks) / count, 4),
            **{f"recall@{cutoff}": round(value / count, 4) for cutoff, value in hits.items()}}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--dataset", type=Path, default=DEFAULT_DATASET)
    parser.add_argument("--baseline-only", action="store_true")
    args = parser.parse_args()
    data = json.loads(args.dataset.read_text(encoding="utf-8"))
    report = {"hash-v1": metrics(rankings(HashEmbedder(), data["documents"], data["queries"]), data["queries"])}
    if not args.baseline_only:
        bge = LocalBGEEmbedder()
        report["bge-small-en-v1.5"] = metrics(rankings(bge, data["documents"], data["queries"]), data["queries"])
        report["hybrid-bge+lexical"] = metrics(rankings(bge, data["documents"], data["queries"], hybrid=True), data["queries"])
    print(json.dumps(report, indent=2))


if __name__ == "__main__":
    main()
