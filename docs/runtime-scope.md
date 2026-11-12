# Runtime scope and deferred capabilities

The active application uses the Interaction Agent / Execution Agent split,
name-based worker dispatch, local JSON/log storage, and owner-qualified saved
content. Bounded worker discovery and bounded model context are the defaults.
See the [architecture map](architecture-map.md) for the executed paths and the
[release checks](agent-overload-release-checks.md) for configuration and opt-out.

## Active behavior

- The Interaction Agent sees at most five recent workers and can call
  `find_worker` over the complete stored roster. Retrieval returns candidates;
  it does not dispatch a worker or authorize an external action.
- Worker names remain exact identities. Filename-collision checks protect new
  registrations; no semantic merge or alias reconciliation is implemented.
- Complete text requests pass shared budget preflight. Large new inputs/results
  are saved before previewing, with paged source reads and selected-history recall.
- Draft bodies can travel by exact reference through creation and full review.
  Confirmation remains agent policy; there is no durable approval ledger.
- Triggers, email watchers, worker callbacks, conversation memory, and telemetry
  use the existing runtime services. Pending executions and callbacks are not a
  durable queue.

The supported storage model assumes a local application process. Local locks
and atomic file replacement do not supply cross-process coordination,
multi-user isolation, or distributed execution guarantees.

## Deferred integration

These are excluded capabilities, not implementation instructions. Their current
behavior, safeguards, and conditions for reconsideration remain in the register.

| Capability | Current boundary and reconsideration condition |
| --- | --- |
| Stable workflow IDs, aliases, and history migration | Names/files remain authoritative. Revisit for a demonstrated identity or migration requirement; preserve histories and ownership. [LIM-007](known-limitations.md#lim-007) |
| Shared execution admission and per-worker serialization | No shared active/pending limit. Revisit after demonstrated mixed chat/trigger pressure. [LIM-017](known-limitations.md#lim-017) |
| Durable callbacks, restart replay, and effect recovery | Accepted work is held in process memory; exactly-once external effects are not guaranteed. Revisit for a concrete recovery requirement. [LIM-019](known-limitations.md#lim-019), [LIM-020](known-limitations.md#lim-020) |
| Approval ledger and revision locking | Model instructions require confirmation, but external drafts can change after review. Revisit with an explicit durable authorization/revision design. [LIM-014](known-limitations.md#lim-014), [LIM-015](known-limitations.md#lim-015) |
| Distributed storage, automatic retention, and multi-user deployment | Local storage remains; separate scope is needed for coordination, deletion policy, quotas, and authentication. [LIM-022](known-limitations.md#lim-022), [LIM-023](known-limitations.md#lim-023), [LIM-025](known-limitations.md#lim-025) |
| Semantic retrieval in application discovery | The [community catalog experiment](community-catalog.md) is standalone. Live indexing, updates, widening, reconciliation, and dispatch integration remain unimplemented. Revisit with representative quality and matched performance evidence. [LIM-003](known-limitations.md#lim-003), [LIM-004](known-limitations.md#lim-004), [LIM-006](known-limitations.md#lim-006) |

## Deferred storage checkpoint

The inactive workflow/migration/event implementation was backed up before its
removal from active source. The local checkpoint is
`deferred/execution-agent-overload-storage-2026-11-08/`. It includes the source,
dedicated tests/docs, a manifest, and `storage-checkpoint.zip`; these files are
now ignored and remain on the current machine.

The last tracked copy before this documentation cleanup is available at commit
`26f9d8f1bffd59d99b964e767931ce6e4d30ad13`:
[checkpoint and recovery notes](https://github.com/WilliamZhao1/openpoke/tree/26f9d8f1bffd59d99b964e767931ce6e4d30ad13/deferred/execution-agent-overload-storage-2026-11-08).
The archive SHA-256 is
`d134bc0af228b732b24a4c5f24a27d648a12b69595b5daee09ee1a0425cb4973`.

On a clone without local copies, restore the checkpoint from that retained commit:

```powershell
git restore --source=26f9d8f1bffd59d99b964e767931ce6e4d30ad13 --worktree -- deferred/execution-agent-overload-storage-2026-11-08
```

Inspect its README and manifest, verify the archive hash, and extract into a new
scratch directory before selectively reusing anything. Restoring a checkpoint
does not connect it to the application. Historical storage tests do not establish
current runtime integration or satisfy a new feature's validation requirements.
