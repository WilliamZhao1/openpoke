# Deferred storage checkpoint

The reduced-scope implementation plan permits an explicit backup instead of a
separate-branch commit. `storage-checkpoint.zip` is that backup, created and
verified before removing the inactive workflow package from the active source.
It preserves the working-tree versions, including uncommitted and untracked
files, rather than just pointing at an earlier commit.

The checkpoint contains:

- All 11 workflow-package source/documentation files.
- All 3 dedicated workflow, migration, and history test files.
- The repository README and historical progress log as they stood before cleanup.
- The earlier implementation plan from Git HEAD and the tracked working diff
  for the selected files. Untracked source files are included as full files.

There are 16 working-tree files, including 4 untracked files. The manifest records
each file's original path, SHA-256, byte length, and tracking status, plus the
origin commit and branch. The archive also contains its own file manifest.
Its SHA-256 is:

```text
d134bc0af228b732b24a4c5f24a27d648a12b69595b5daee09ee1a0425cb4973
```

Every archived file was read back and compared with both its recorded hash and
the working-tree bytes before cleanup. This checkpoint does not contain runtime
data or credentials. The user's revised implementation plan is excluded and
remains in the active tree.

To inspect the backup, run from the repository root:

```powershell
python -m zipfile -l deferred/execution-agent-overload-storage-2026-11-08/storage-checkpoint.zip
python -m zipfile -t deferred/execution-agent-overload-storage-2026-11-08/storage-checkpoint.zip
```

For restoration, first extract into a new scratch directory using
`python -m zipfile -e <archive> <scratch-directory>`. Original files are under
`files/`; compare their hashes with `manifest.json` before selectively restoring
them to a separate branch/worktree. Review README/progress changes individually
so restoration does not replace newer project documentation.

The saved APIs passed 143 tests before being set aside. Their 65 dedicated tests
are archived with the code. The retained 78-test Phase 0/runtime suite is the
active cleanup regression check. These historical storage tests do not establish
that deferred storage satisfies the reduced-scope release plan.
