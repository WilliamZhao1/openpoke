# Local worker ranking comparison

Authored synthetic retrieval judgments; no model or Gmail calls. Passing checks indicate the comparison ran, not that a new default is justified.

| Workers | Split | Ranker | Top-1 | Recall@5 | MRR | Packed recall | No-match FP | Lookup median / p95 ms |
| ---: | --- | --- | ---: | ---: | ---: | ---: | ---: | ---: |
| 100 | development | bm25_v1 | 1.000 | 1.000 | 1.000 | 1.000 | 0.000 | 2.860 / 3.289 |
| 100 | development | heuristic_v1 | 1.000 | 1.000 | 1.000 | 1.000 | 0.000 | 2.397 / 11.336 |
| 100 | development | idf_v1 | 1.000 | 1.000 | 1.000 | 1.000 | 0.000 | 3.076 / 3.635 |
| 100 | evaluation | bm25_v1 | 1.000 | 0.944 | 1.000 | 0.944 | 0.000 | 2.804 / 3.113 |
| 100 | evaluation | heuristic_v1 | 1.000 | 0.944 | 1.000 | 0.944 | 0.000 | 2.496 / 2.800 |
| 100 | evaluation | idf_v1 | 1.000 | 0.944 | 1.000 | 0.944 | 0.000 | 3.051 / 3.655 |
| 1000 | development | bm25_v1 | 1.000 | 1.000 | 1.000 | 1.000 | 0.000 | 28.614 / 53.431 |
| 1000 | development | heuristic_v1 | 1.000 | 1.000 | 1.000 | 1.000 | 0.000 | 23.887 / 45.615 |
| 1000 | development | idf_v1 | 1.000 | 1.000 | 1.000 | 1.000 | 0.000 | 31.680 / 58.449 |
| 1000 | evaluation | bm25_v1 | 1.000 | 0.944 | 1.000 | 0.944 | 0.000 | 29.525 / 55.572 |
| 1000 | evaluation | heuristic_v1 | 1.000 | 0.944 | 1.000 | 0.944 | 0.000 | 24.797 / 49.083 |
| 1000 | evaluation | idf_v1 | 1.000 | 0.944 | 1.000 | 0.944 | 0.000 | 31.857 / 55.959 |
| 10000 | development | bm25_v1 | 1.000 | 1.000 | 1.000 | 1.000 | 0.000 | 358.840 / 439.728 |
| 10000 | development | heuristic_v1 | 1.000 | 1.000 | 1.000 | 1.000 | 0.000 | 326.226 / 399.194 |
| 10000 | development | idf_v1 | 1.000 | 1.000 | 1.000 | 1.000 | 0.000 | 392.293 / 463.377 |
| 10000 | evaluation | bm25_v1 | 1.000 | 0.944 | 1.000 | 0.944 | 0.000 | 368.603 / 457.931 |
| 10000 | evaluation | heuristic_v1 | 1.000 | 0.944 | 1.000 | 0.944 | 0.000 | 317.838 / 415.049 |
| 10000 | evaluation | idf_v1 | 1.000 | 0.944 | 1.000 | 0.944 | 0.000 | 387.878 / 464.833 |

Eligibility under the predeclared offline gate:

```json
{
  "heuristic_v1": {
    "offline_eligible": null,
    "reason": "retained_baseline"
  },
  "idf_v1": {
    "offline_eligible": false,
    "reason": "predeclared_quality_and_latency_gate",
    "promotion": "requires_separate_live_agent_evidence"
  },
  "bm25_v1": {
    "offline_eligible": false,
    "reason": "predeclared_quality_and_latency_gate",
    "promotion": "requires_separate_live_agent_evidence"
  }
}
```

Timing is local and noisy; preprocessing memory excludes native allocations. Scores are not confidence. See summary.json for denominators/failures, results.json for disagreements and scores, and provenance.json for source hashes. Agent decisions and effects need a separate fixed-strategy comparison. Production remains heuristic_v1.
