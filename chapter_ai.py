"""TypeSafe Jev boundary for chapter re-ranking."""
from __future__ import annotations

import json
import os
import time
import urllib.error
import urllib.request
from concurrent.futures import ThreadPoolExecutor


JEV_MODEL = "jev-1.13.0"
JEV_SHORTLIST = 15
CODEX_SUMMARY_MODEL = "codex-gpt-6-luna"
CODEX_PROMPT_VERSION = "codex-bjj-chapter-summary-v1"


class AIServiceUnavailable(RuntimeError):
    pass


def _post_json(url, payload, api_key, timeout=60, attempts=3):
    body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
    request = urllib.request.Request(
        url,
        data=body,
        headers={"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"},
        method="POST",
    )
    for attempt in range(attempts):
        try:
            with urllib.request.urlopen(request, timeout=timeout) as response:
                return json.loads(response.read().decode("utf-8"))
        except urllib.error.HTTPError as exc:
            detail = exc.read().decode("utf-8", errors="replace")[:500]
            if exc.code not in {429, 500, 502, 503, 529} or attempt == attempts - 1:
                raise AIServiceUnavailable(f"AI service returned HTTP {exc.code}: {detail}") from exc
        except (OSError, ValueError) as exc:
            if attempt == attempts - 1:
                raise AIServiceUnavailable("AI service request failed.") from exc
        time.sleep(2 ** attempt)
    raise AIServiceUnavailable("AI service request failed.")


class JevReranker:
    """Pairwise TypeSafe Jev relevance judgments for a bounded shortlist."""

    endpoint = "https://api.typesafe.ai/v1/systemone"
    question = {
        "type": "noul",
        "instructions": (
            "Does `candidate` directly help answer the BJJ search query in `query`? "
            "Judge practical technical relevance. Account for synonymous grappling terminology "
            "and plausible speech-transcription errors."
        ),
        "criteria": {
            "true": (
                "The chapter teaches, explains, troubleshoots, or demonstrates material that "
                "would substantively help answer the query."
            ),
            "false": (
                "The overlap is superficial, incidental, or unrelated; the chapter would not "
                "materially help answer the query."
            ),
        },
    }

    def __init__(self, api_key=None, model=JEV_MODEL, workers=8):
        self.api_key = api_key if api_key is not None else os.environ.get("TYPESAFE_API_KEY", "")
        self.model = model
        self.workers = workers

    @property
    def available(self):
        return bool(self.api_key)

    def _score(self, query, candidate):
        state = {
            "query": query,
            "candidate": {
                "title": candidate.get("title", ""),
                "chapter": candidate.get("section", ""),
                "transcript": candidate.get("_content", candidate.get("excerpt", "")),
            },
        }
        payload = {"state": state, "questions": {"relevant": self.question}, "model": self.model}
        # A conservative byte gate keeps requests far below Jev's documented 32k-token
        # state-plus-longest-question ceiling without depending on a private tokenizer.
        if len(json.dumps(payload, ensure_ascii=False).encode("utf-8")) >= 30_000:
            raise AIServiceUnavailable("A Jev re-ranking candidate exceeds the safe context budget.")
        response = _post_json(self.endpoint, payload, self.api_key, timeout=15, attempts=2)
        try:
            return float(response["answers"]["relevant"]["noul"])
        except (KeyError, TypeError, ValueError) as exc:
            raise AIServiceUnavailable("Jev returned an invalid relevance response.") from exc

    def rank(self, query, candidates):
        candidates = list(candidates[:JEV_SHORTLIST])
        if not self.available or not candidates:
            return candidates
        with ThreadPoolExecutor(max_workers=min(self.workers, len(candidates))) as pool:
            scores = list(pool.map(lambda candidate: self._score(query, candidate), candidates))
        for candidate, score in zip(candidates, scores):
            candidate["jev_score"] = score
        return sorted(candidates, key=lambda candidate: candidate["jev_score"], reverse=True)
