"""Deterministic local ranking over one immutable, caller-owned roster snapshot."""

from collections import Counter
from dataclasses import dataclass
from math import isfinite, log
import re
from types import MappingProxyType
from typing import Mapping, Protocol
import unicodedata


RANKER_IDS = ("heuristic_v1", "idf_v1", "bm25_v1")
FIELDS = ("name", "purpose", "recent_assignment")


def normalise(text):
    return unicodedata.normalize("NFKC", text).casefold()


def words(text):
    return tuple(re.findall(r"[^\W_]+", normalise(text)))


def terms(text):
    return set(words(text))


@dataclass(frozen=True)
class WorkerDocument:
    name: str
    values: tuple[str, ...]
    frequencies: tuple[Mapping[str, int], ...]
    lengths: tuple[int, ...]


@dataclass(frozen=True)
class SearchCatalog:
    documents: tuple[WorkerDocument, ...]
    document_frequency: Mapping[str, int]
    average_lengths: tuple[float, ...]

    @classmethod
    def build(cls, names, metadata):
        documents, frequency = [], Counter()
        totals = [0, 0, 0]
        for name in dict.fromkeys(names):
            record = metadata.get(name, {})
            values = (name, record.get("purpose") or "", record.get("recent_assignment") or "")
            counts = tuple(Counter(words(value)) for value in values)
            lengths = tuple(sum(count.values()) for count in counts)
            frequency.update(set().union(*(count.keys() for count in counts)))
            for index, length in enumerate(lengths):
                totals[index] += length
            documents.append(WorkerDocument(name, values, tuple(MappingProxyType(count) for count in counts), lengths))
        size = len(documents)
        return cls(tuple(documents), MappingProxyType(dict(frequency)),
                   tuple(total / size if size else 0.0 for total in totals))

    def idf(self, term):
        count = self.document_frequency.get(term, 0)
        return log(1 + (len(self.documents) - count + 0.5) / (count + 0.5))


@dataclass(frozen=True)
class RankedWorker:
    name: str
    score: float
    reasons: tuple[str, ...]


class WorkerRanker(Protocol):
    """Return scored matches; rank_workers enforces identity and final ordering."""
    id: str

    def rank(self, query: str, catalog: SearchCatalog) -> list[RankedWorker]: ...


class RankingError(RuntimeError):
    pass


def _name_bonus(query, document, score, reasons, phrase_bonus):
    if query == document.name:
        return score + 10000, ["exact_name", *reasons]
    if normalise(query) == normalise(document.name):
        return score + 1000, ["normalized_exact_name", *reasons]
    phrase = " ".join(words(query))
    name = " ".join(words(document.name))
    if phrase and f" {phrase} " in f" {name} ":
        score += phrase_bonus
        reasons.append("name_word_phrase")
    return score, reasons


def rank_workers(ranker, query, catalog):
    """Validate implementation output and impose shared identity/tie ordering."""
    matches = ranker.rank(query, catalog)
    names = {document.name for document in catalog.documents}
    seen = set()
    if not isinstance(matches, list):
        raise RankingError("Ranker must return a complete list of matches")
    for match in matches:
        if (not isinstance(match, RankedWorker) or match.name not in names or match.name in seen
                or type(match.score) not in (int, float) or not isfinite(match.score) or match.score <= 0
                or not isinstance(match.reasons, tuple) or len(match.reasons) > 8
                or any(not isinstance(reason, str) or not reason or len(reason) > 64 for reason in match.reasons)):
            raise RankingError("Ranker returned an invalid worker, score, or explanation")
        seen.add(match.name)
    if query in names and query not in seen:
        raise RankingError("Ranker omitted an exact worker-name match")
    return sorted(matches, key=lambda match: (match.name != query, -match.score, match.name))


class HeuristicRanker:
    id = "heuristic_v1"

    def rank(self, query, catalog):
        tokens, normal_query = terms(query), normalise(query)
        matches = []
        for document in catalog.documents:
            score, reasons = 0, []
            if query == document.name:
                score += 10000
                reasons.append("exact_name")
            elif normal_query in normalise(document.name):
                score += 1000
                reasons.append("name_phrase")
            for field, counts, weight in zip(FIELDS, document.frequencies, (20, 6, 3)):
                hits = tokens.intersection(counts)
                if hits:
                    score += weight * len(hits)
                    reasons.append(field + "_terms")
            if score:
                matches.append(RankedWorker(document.name, score, tuple(reasons)))
        return matches


class IdfCoverageRanker:
    id = "idf_v1"
    weights = (4.0, 2.0, 1.0)
    phrase_bonus = 0.5

    def rank(self, query, catalog):
        tokens = terms(query)
        weights = {term: catalog.idf(term) for term in sorted(tokens)}
        total = sum(weights.values())
        matches = []
        for document in catalog.documents:
            matched, reasons, score = set(), [], 0.0
            for field, counts in zip(FIELDS, document.frequencies):
                if tokens.intersection(counts):
                    reasons.append(field + "_terms")
            for term, rarity in weights.items():
                strongest = max((weight for counts, weight in zip(document.frequencies, self.weights) if term in counts), default=0)
                if strongest:
                    matched.add(term)
                    score += rarity * strongest
            if score:
                coverage = sum(weights[term] for term in sorted(matched)) / total
                score *= 0.5 + 0.5 * coverage
                reasons.append("query_coverage")
            score, reasons = _name_bonus(query, document, score, reasons, self.phrase_bonus)
            if score:
                matches.append(RankedWorker(document.name, score, tuple(reasons)))
        return matches

class BM25Ranker:
    id = "bm25_v1"
    weights = (4.0, 2.0, 1.0)
    phrase_bonus = 0.5
    k1 = 1.2
    b = 0.75

    def rank(self, query, catalog):
        tokens = {term: catalog.idf(term) for term in sorted(terms(query))}
        matches = []
        for document in catalog.documents:
            score, reasons = 0.0, []
            for field, counts, length, average, weight in zip(
                    FIELDS, document.frequencies, document.lengths, catalog.average_lengths, self.weights):
                contribution = 0.0
                for term, rarity in tokens.items():
                    count = counts.get(term, 0)
                    if count:
                        norm = 1 - self.b + self.b * length / average
                        contribution += rarity * count * (self.k1 + 1) / (count + self.k1 * norm)
                if contribution:
                    score += weight * contribution
                    reasons.append(field + "_terms")
            score, reasons = _name_bonus(query, document, score, reasons, self.phrase_bonus)
            if score:
                matches.append(RankedWorker(document.name, score, tuple(reasons)))
        return matches


def get_ranker(identifier):
    implementations = {ranker.id: ranker for ranker in (HeuristicRanker, IdfCoverageRanker, BM25Ranker)}
    try:
        return implementations[identifier]()
    except (KeyError, TypeError) as exc:
        raise ValueError("Unknown worker ranker; choose heuristic_v1, idf_v1, or bm25_v1") from exc


def ranker_parameters(ranker):
    if ranker.id == "heuristic_v1":
        return {"field_weights": [20, 6, 3], "exact_bonus": 10000, "substring_bonus": 1000}
    parameters = {"field_weights": list(ranker.weights), "exact_bonus": 10000,
                  "normalized_exact_bonus": 1000, "word_phrase_bonus": ranker.phrase_bonus}
    if ranker.id == "bm25_v1":
        parameters.update(k1=ranker.k1, b=ranker.b, idf="worker_union", field_normalization="independent")
    else:
        parameters.update(coverage_factor="0.5 + 0.5 * idf_coverage", repeated_fields="strongest_only")
    return parameters
