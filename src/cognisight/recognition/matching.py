"""Versioned gallery matching. Similarity scores are not probabilities."""

import math
from dataclasses import dataclass
from typing import Optional


def normalize(vector):
    values = tuple(float(x) for x in vector)
    if not values or not all(math.isfinite(x) for x in values):
        raise ValueError("Embedding must contain finite values")
    norm = math.sqrt(sum(x * x for x in values))
    if norm < 1e-12:
        raise ValueError("Embedding has zero length")
    return tuple(x / norm for x in values)


@dataclass(frozen=True)
class Match:
    state: str
    person_id: Optional[str]
    similarity: float


class Gallery:
    def __init__(self, people, threshold, margin):
        if not (0 < threshold <= 1 and 0 < margin <= 1):
            raise ValueError("Positive calibrated threshold and margin required")
        self.people = {key: tuple(normalize(v) for v in vectors) for key, vectors in people.items()}
        dimensions = {len(v) for vectors in self.people.values() for v in vectors}
        if len(dimensions) > 1:
            raise ValueError("Inconsistent gallery dimensions")
        self.dimension = next(iter(dimensions), None)
        self.threshold, self.margin = threshold, margin

    def match(self, vector):
        try:
            query = normalize(vector)
        except (ValueError, TypeError):
            return Match("unknown", None, 0.0)
        if not self.people or len(query) != self.dimension:
            return Match("unknown", None, 0.0)
        scores = sorted(
            (
                (max(sum(a * b for a, b in zip(query, v)) for v in vectors), key)
                for key, vectors in self.people.items()
                if vectors
            ),
            reverse=True,
        )
        if not scores:
            return Match("unknown", None, 0.0)
        best, person_id = scores[0]
        if best < self.threshold:
            return Match("unknown", None, best)
        if len(scores) > 1 and best - scores[1][0] < self.margin:
            return Match("ambiguous", None, best)
        return Match("known", person_id, best)
