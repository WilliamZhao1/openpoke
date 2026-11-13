# Discovery-quality v2 first baseline

Offline production discovery/ranking; model and Gmail calls: zero. No defaults promoted.

Rows: 4200; distinct requests: 200; families: 20; failures: 0.
Review: `author_checked_pending_independent_review`. Integrity checks are not independent semantic review.

Draws are averaged within a request before family-cluster bootstrap intervals. Repeats/seeds are not new independent requests. Intervals describe authored synthetic families, not production accuracy. Insufficient-metadata requests are diagnostic; no-match has no recall denominator. Ambiguous coverage does not establish model clarification or authorization.

| Workers | Split | Ranker | Top-1 | Recall@5 | Packed recall | Every owner packed | No-match FP |
| ---: | --- | --- | ---: | ---: | ---: | ---: | ---: |
| 100 | development | heuristic_v1 | 0.8000 | 1.0000 | 1.0000 | 1.0000 | 1.0000 |
| 100 | development | idf_v1 | 0.8000 | 1.0000 | 1.0000 | 1.0000 | 1.0000 |
| 100 | development | bm25_v1 | 0.8333 | 0.9750 | 0.9750 | 0.9750 | 1.0000 |
| 100 | evaluation | heuristic_v1 | 0.7444 | 0.9917 | 0.9917 | 0.9917 | 1.0000 |
| 100 | evaluation | idf_v1 | 0.7778 | 0.9833 | 0.9833 | 0.9833 | 1.0000 |
| 100 | evaluation | bm25_v1 | 0.8667 | 0.9833 | 0.9833 | 0.9833 | 1.0000 |
| 1000 | development | heuristic_v1 | 0.8000 | 0.9708 | 0.9708 | 0.9667 | 1.0000 |
| 1000 | development | idf_v1 | 0.8333 | 0.9792 | 0.9792 | 0.9667 | 1.0000 |
| 1000 | development | bm25_v1 | 0.8111 | 0.9792 | 0.9792 | 0.9750 | 1.0000 |
| 1000 | evaluation | heuristic_v1 | 0.7444 | 0.9708 | 0.9708 | 0.9611 | 1.0000 |
| 1000 | evaluation | idf_v1 | 0.8074 | 0.9764 | 0.9764 | 0.9694 | 1.0000 |
| 1000 | evaluation | bm25_v1 | 0.8741 | 0.9903 | 0.9903 | 0.9889 | 1.0000 |
| 10000 | development | heuristic_v1 | 0.8000 | 0.9500 | 0.9500 | 0.9250 | 1.0000 |
| 10000 | development | idf_v1 | 0.8333 | 0.9875 | 0.9875 | 0.9750 | 1.0000 |
| 10000 | development | bm25_v1 | 0.8000 | 0.9875 | 0.9875 | 0.9750 | 1.0000 |
| 10000 | evaluation | heuristic_v1 | 0.7444 | 0.9292 | 0.9292 | 0.9000 | 1.0000 |
| 10000 | evaluation | idf_v1 | 0.8000 | 0.9750 | 0.9750 | 0.9667 | 1.0000 |
| 10000 | evaluation | bm25_v1 | 0.8778 | 0.9875 | 0.9875 | 0.9833 | 1.0000 |

## Per-draw timings

Fresh JSON reads, preparation, scoring and packing are included. Timing repeats do not increase quality denominators. Preparation allocations are measured separately and are not process RSS.

| Workers | Draw | Split | Ranker | Median ms | p95 ms |
| ---: | --- | --- | --- | ---: | ---: |
| 100 | base | development | bm25_v1 | 3.8064 | 4.3582 |
| 100 | base | development | heuristic_v1 | 2.9650 | 3.7434 |
| 100 | base | development | idf_v1 | 4.5135 | 5.3795 |
| 100 | base | evaluation | bm25_v1 | 3.6097 | 4.0042 |
| 100 | base | evaluation | heuristic_v1 | 2.8284 | 3.1233 |
| 100 | base | evaluation | idf_v1 | 4.3538 | 4.8335 |
| 1000 | 11 | development | bm25_v1 | 42.7238 | 71.8059 |
| 1000 | 11 | development | heuristic_v1 | 33.0849 | 60.4950 |
| 1000 | 11 | development | idf_v1 | 50.4915 | 78.5290 |
| 1000 | 11 | evaluation | bm25_v1 | 42.4070 | 74.9109 |
| 1000 | 11 | evaluation | heuristic_v1 | 33.2115 | 66.6853 |
| 1000 | 11 | evaluation | idf_v1 | 51.1608 | 82.7595 |
| 1000 | 22 | development | bm25_v1 | 42.8203 | 78.1672 |
| 1000 | 22 | development | heuristic_v1 | 33.6092 | 67.6911 |
| 1000 | 22 | development | idf_v1 | 51.1677 | 92.3892 |
| 1000 | 22 | evaluation | bm25_v1 | 43.2223 | 82.0416 |
| 1000 | 22 | evaluation | heuristic_v1 | 33.5605 | 74.2593 |
| 1000 | 22 | evaluation | idf_v1 | 51.5709 | 86.6788 |
| 1000 | 33 | development | bm25_v1 | 43.7295 | 85.5458 |
| 1000 | 33 | development | heuristic_v1 | 34.1905 | 76.3156 |
| 1000 | 33 | development | idf_v1 | 51.4497 | 94.0099 |
| 1000 | 33 | evaluation | bm25_v1 | 44.1194 | 87.2945 |
| 1000 | 33 | evaluation | heuristic_v1 | 34.2770 | 80.1164 |
| 1000 | 33 | evaluation | idf_v1 | 52.2664 | 96.6892 |
| 10000 | 11 | development | bm25_v1 | 527.6243 | 663.7383 |
| 10000 | 11 | development | heuristic_v1 | 477.7478 | 573.4845 |
| 10000 | 11 | development | idf_v1 | 625.9169 | 748.5454 |
| 10000 | 11 | evaluation | bm25_v1 | 556.6582 | 688.8678 |
| 10000 | 11 | evaluation | heuristic_v1 | 452.4555 | 593.1068 |
| 10000 | 11 | evaluation | idf_v1 | 619.2720 | 764.7629 |
| 10000 | 22 | development | bm25_v1 | 576.8094 | 693.5767 |
| 10000 | 22 | development | heuristic_v1 | 477.7445 | 608.7234 |
| 10000 | 22 | development | idf_v1 | 628.4873 | 792.0882 |
| 10000 | 22 | evaluation | bm25_v1 | 564.3234 | 715.9826 |
| 10000 | 22 | evaluation | heuristic_v1 | 487.3129 | 623.7573 |
| 10000 | 22 | evaluation | idf_v1 | 637.2987 | 794.6698 |
| 10000 | 33 | development | bm25_v1 | 568.4063 | 720.1518 |
| 10000 | 33 | development | heuristic_v1 | 504.5928 | 629.5015 |
| 10000 | 33 | development | idf_v1 | 692.5148 | 820.6391 |
| 10000 | 33 | evaluation | bm25_v1 | 587.8047 | 743.6760 |
| 10000 | 33 | evaluation | heuristic_v1 | 492.6972 | 660.1583 |
| 10000 | 33 | evaluation | idf_v1 | 659.0083 | 824.3089 |

See [summary.json](summary.json) for category/answerability breakdowns, denominators, failures, intervals and paired differences; `results.jsonl.gz` for every scored/packed result; `catalogs/` for complete frozen snapshots; `inputs/` for separate queries/judgments and authoring provenance. This more varied fixture remains synthetic and templated, with independent review pending. Historical v1 scores are not directly comparable.
