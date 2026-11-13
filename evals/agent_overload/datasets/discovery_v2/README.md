# Frozen discovery-quality v2

100 authored worker records, 20 task families/domains, 200 requests (50 development,
150 evaluation), ten request categories and 100 targeted owners. The complete
[design, commands and interpretation guide](../../../../docs/discovery-quality-benchmark.md)
describes the benchmark.

`workers.json` contains only public identity/name/metadata fields. `queries.json`
and `judgments.json` are separate. `families.json` records split membership and
project scope; the ranking projection excludes all family annotations and labels.
`scenario_source.json` preserves the reviewable authoring record. The dataset was
authored and checked by the implementation author; independent semantic review is
pending. Integrity tests do not change that status.

Expansion uses `background.json` and three fixed draws (11, 22, 33). Thirty percent
of extra records are close alternatives derived from related tasks with a different
project scope; the remainder use 32 activities and varied organizations, contacts,
project names and phrasing. Missing metadata and older activity are included. The
background remains synthetic and templated. Every answerable judged request names
its protected base project, which expansion must not reuse. The private-reference
requests deliberately lack the necessary reference-to-owner link in searchable
metadata and are diagnostic only. They are not primary retrieval failures.
Requests are predominantly English; a Unicode title is not a multilingual quality
evaluation. The repeated five-role family structure is another generalization bound.

Do not regenerate this manifest to hide a regression. Intentional data/judgment or
generator changes after freezing require a new reviewed version, with old reports
preserved. The seven canonical catalog hashes and canonical JSON file hashes in
`manifest.json` are verified before measurement. Full generated catalogs are saved
with each run, rather than committing three copies of 10,000 repetitive records.

These inputs do not change production ranking or integrate the community PoC.
No live model, real mailbox or private user history is used.
