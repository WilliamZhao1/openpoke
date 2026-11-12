# OpenPoke documentation

Start with the [architecture map](architecture-map.md) for the runtime flow and
the [known limitations](known-limitations.md) for current bounds, deferred
capabilities, evidence gaps, and resolved findings. Installation and startup are
in the [repository README](../README.md).

## How the system works

| Guide | What it explains |
| --- | --- |
| [Architecture map](architecture-map.md) | Chat, agents, tools, callbacks, background jobs, APIs, and storage |
| [Runtime scope](runtime-scope.md) | Active capabilities, deployment assumptions, deferred work, and checkpoint recovery |
| [Worker discovery](worker-discovery.md) | Recent workers, complete-roster lookup, names, metadata, and dispatch safeguards |
| [Worker ranking](worker-ranking.md) | Ranking methods, configuration, interfaces, comparisons, and the retained default |
| [Context budgets](context-budgets.md) | Model allowances, request accounting, and provider preflight |
| [Content capture](content-capture.md) | Full-content storage, opaque references, ownership, and clearing |
| [Context recovery](context-recovery.md) | Paged result reads and selected-history recall |
| [Outer-agent context](bounded-context.md) | History selection, required episodes, and result previews |
| [Draft references](draft-references.md) | Exact bodies, complete review, provider draft IDs, and confirmation |
| [Inner context](inner-context.md) | Email search, importance classification, and summarization budgets |
| [Observability](observability.md) | Usage, timing, failures, provenance, and asynchronous correlation |

## How the system is evaluated

| Guide or evidence | What it covers |
| --- | --- |
| [Evaluation guide](evaluation.md) | Test layers, reproduction commands, measured outcomes, and claim boundaries |
| [Legacy/bounded comparison](agent-overload-comparison.md) | Historical live-model comparison with fake Gmail, initial failure, and focused recheck |
| [Application release checks](agent-overload-release-checks.md) | Scripted HTTP/proxy/rendering checks, default promotion, and rollback |
| [Community catalog experiment](community-catalog.md) | Standalone semantic retrieval design, frozen configuration, results, and limits |
| [Agent evaluation harness](../evals/agent_overload/README.md) | Baseline, paired comparisons, fixtures, and outputs |
| [Community experiment CLI](../evals/community_catalog_poc/README.md) | Setup, build/query/evaluate commands, and saved evidence |

Historical reports, frozen protocols, manifests, and saved evidence remain in
`evals/`. Generated agent runs remain ignored under `evals/agent_overload/runs/`.
Frozen evidence bundles retain their original bytes, including historical links
to planning files. Those plans remain available in
[the documentation at the retained pre-cleanup commit](https://github.com/WilliamZhao1/openpoke/tree/26f9d8f1bffd59d99b964e767931ce6e4d30ad13/docs);
use the guides above for current navigation and commands.

## Documentation policy

The root `.gitignore` explicitly includes the reader-facing files listed here.
Other files under `docs/` stay local by default, including implementation plans,
progress logs, design proposals, and recording scripts. Deferred checkpoints under
`deferred/` also stay local. Ignoring these files preserves local copies; it does
not erase earlier committed versions from Git history.

When adding a system or evaluation guide, add it to both this index and the
`.gitignore` include list. Keep historical measurements intact and update the
[limitations register](known-limitations.md) when a limitation changes.
