# Local worker ranking comparison

Authored synthetic retrieval judgments; no model or Gmail calls. Passing checks indicate the comparison ran, not that a new default is justified.

| Workers | Split | Ranker | Top-1 | Recall@5 | MRR | Packed recall | No-match FP | Lookup median / p95 ms |
| ---: | --- | --- | ---: | ---: | ---: | ---: | ---: | ---: |
| 100 | development | bm25_v1 | 1.000 | 1.000 | 1.000 | 1.000 | 0.000 | 2.861 / 3.271 |
| 100 | development | heuristic_v1 | 1.000 | 1.000 | 1.000 | 1.000 | 0.000 | 2.536 / 9.306 |
| 100 | development | idf_v1 | 1.000 | 1.000 | 1.000 | 1.000 | 0.000 | 3.176 / 3.364 |
| 100 | evaluation | bm25_v1 | 1.000 | 0.944 | 1.000 | 0.944 | 0.000 | 2.724 / 3.032 |
| 100 | evaluation | heuristic_v1 | 1.000 | 0.944 | 1.000 | 0.944 | 0.000 | 2.398 / 2.681 |
| 100 | evaluation | idf_v1 | 1.000 | 0.944 | 1.000 | 0.944 | 0.000 | 2.981 / 3.266 |
| 1000 | development | bm25_v1 | 1.000 | 1.000 | 1.000 | 1.000 | 0.000 | 27.057 / 52.261 |
| 1000 | development | heuristic_v1 | 1.000 | 1.000 | 1.000 | 1.000 | 0.000 | 22.776 / 41.653 |
| 1000 | development | idf_v1 | 1.000 | 1.000 | 1.000 | 1.000 | 0.000 | 30.125 / 63.174 |
| 1000 | evaluation | bm25_v1 | 1.000 | 0.944 | 1.000 | 0.944 | 0.000 | 28.302 / 56.836 |
| 1000 | evaluation | heuristic_v1 | 1.000 | 0.944 | 1.000 | 0.944 | 0.000 | 24.256 / 55.935 |
| 1000 | evaluation | idf_v1 | 1.000 | 0.944 | 1.000 | 0.944 | 0.000 | 30.082 / 53.102 |
| 10000 | development | bm25_v1 | 1.000 | 1.000 | 1.000 | 1.000 | 0.000 | 352.183 / 418.086 |
| 10000 | development | heuristic_v1 | 1.000 | 1.000 | 1.000 | 1.000 | 0.000 | 322.159 / 414.334 |
| 10000 | development | idf_v1 | 1.000 | 1.000 | 1.000 | 1.000 | 0.000 | 375.094 / 445.309 |
| 10000 | evaluation | bm25_v1 | 1.000 | 0.944 | 1.000 | 0.944 | 0.000 | 352.634 / 426.802 |
| 10000 | evaluation | heuristic_v1 | 1.000 | 0.944 | 1.000 | 0.944 | 0.000 | 306.275 / 370.115 |
| 10000 | evaluation | idf_v1 | 1.000 | 0.944 | 1.000 | 0.944 | 0.000 | 360.573 / 448.843 |

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
