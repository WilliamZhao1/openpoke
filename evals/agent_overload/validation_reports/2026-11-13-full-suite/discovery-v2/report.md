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
| 100 | base | development | bm25_v1 | 3.8323 | 4.6695 |
| 100 | base | development | heuristic_v1 | 3.0299 | 3.5588 |
| 100 | base | development | idf_v1 | 4.6788 | 6.4232 |
| 100 | base | evaluation | bm25_v1 | 3.7406 | 4.3017 |
| 100 | base | evaluation | heuristic_v1 | 2.8800 | 3.3567 |
| 100 | base | evaluation | idf_v1 | 4.4890 | 5.1180 |
| 1000 | 11 | development | bm25_v1 | 44.7151 | 78.2020 |
| 1000 | 11 | development | heuristic_v1 | 34.9002 | 63.3863 |
| 1000 | 11 | development | idf_v1 | 52.8341 | 79.1450 |
| 1000 | 11 | evaluation | bm25_v1 | 43.9869 | 75.0637 |
| 1000 | 11 | evaluation | heuristic_v1 | 34.5058 | 71.1713 |
| 1000 | 11 | evaluation | idf_v1 | 52.9903 | 86.5321 |
| 1000 | 22 | development | bm25_v1 | 44.5362 | 84.9969 |
| 1000 | 22 | development | heuristic_v1 | 35.8858 | 75.2810 |
| 1000 | 22 | development | idf_v1 | 53.2340 | 92.4026 |
| 1000 | 22 | evaluation | bm25_v1 | 44.5643 | 83.4641 |
| 1000 | 22 | evaluation | heuristic_v1 | 35.2378 | 76.1153 |
| 1000 | 22 | evaluation | idf_v1 | 53.3200 | 90.7802 |
| 1000 | 33 | development | bm25_v1 | 44.2455 | 90.6238 |
| 1000 | 33 | development | heuristic_v1 | 35.9237 | 82.5647 |
| 1000 | 33 | development | idf_v1 | 52.9279 | 94.9992 |
| 1000 | 33 | evaluation | bm25_v1 | 45.1965 | 90.0902 |
| 1000 | 33 | evaluation | heuristic_v1 | 35.5744 | 83.0434 |
| 1000 | 33 | evaluation | idf_v1 | 53.8094 | 102.7781 |
| 10000 | 11 | development | bm25_v1 | 534.7369 | 676.6529 |
| 10000 | 11 | development | heuristic_v1 | 485.2138 | 584.6360 |
| 10000 | 11 | development | idf_v1 | 637.1568 | 763.1333 |
| 10000 | 11 | evaluation | bm25_v1 | 590.2938 | 912.0759 |
| 10000 | 11 | evaluation | heuristic_v1 | 493.7823 | 722.4273 |
| 10000 | 11 | evaluation | idf_v1 | 679.8906 | 921.5029 |
| 10000 | 22 | development | bm25_v1 | 593.8406 | 760.7741 |
| 10000 | 22 | development | heuristic_v1 | 504.1480 | 665.7817 |
| 10000 | 22 | development | idf_v1 | 665.8901 | 846.5234 |
| 10000 | 22 | evaluation | bm25_v1 | 610.8771 | 993.7990 |
| 10000 | 22 | evaluation | heuristic_v1 | 526.4916 | 799.9684 |
| 10000 | 22 | evaluation | idf_v1 | 695.3254 | 1157.3616 |
| 10000 | 33 | development | bm25_v1 | 707.6402 | 1044.3346 |
| 10000 | 33 | development | heuristic_v1 | 604.3764 | 943.0699 |
| 10000 | 33 | development | idf_v1 | 782.2083 | 1178.3730 |
| 10000 | 33 | evaluation | bm25_v1 | 626.8997 | 812.0794 |
| 10000 | 33 | evaluation | heuristic_v1 | 545.3217 | 710.0033 |
| 10000 | 33 | evaluation | idf_v1 | 699.2436 | 885.2895 |

See [summary.json](summary.json) for category/answerability breakdowns, denominators, failures, intervals and paired differences; `results.jsonl.gz` for every scored/packed result; `catalogs/` for complete frozen snapshots; `inputs/` for separate queries/judgments and authoring provenance. This more varied fixture remains synthetic and templated, with independent review pending. Historical v1 scores are not directly comparable.
