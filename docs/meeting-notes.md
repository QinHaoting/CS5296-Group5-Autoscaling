# Meeting Notes

## 2026-04-23 Fresh Rerun Notes

- Created a clean worktree and branch:
  `rerun-20260423-fresh-artifacts`.
- Pushed the branch to GitHub before generating any new artifacts.
- Verified the local machine lacked the original AWS-oriented toolchain from
  the runbook, so the rerun pivoted to a local Rancher Desktop K3s cluster.
- Increased the Rancher Desktop VM from 2 CPU / 4 GiB to 4 CPU / 8 GiB after
  the first attempt showed API handshake timeouts under load.
- Fixed several portability issues uncovered during the rerun:
  - consumer runtime image updated to an arm64-compatible base
  - experiment scripts now use `python3`
  - collector timestamps are portable on macOS
  - collector calls use timeouts to avoid hanging the whole trial
  - the burst publish pattern is now separated from the observation window
- Collected six fresh trials and regenerated `results/summary.csv` plus four
  figures.
- Generated a new branch-local PDF report from the fresh results.
