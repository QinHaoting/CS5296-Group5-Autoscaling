# Demo Video

## Public Link

Placeholder for the fresh rerun demo:

`https://youtu.be/REPLACE_WITH_RERUN_LINK`

## Target Length

5 to 7 minutes is enough for this rerun branch because the repository now
already contains fresh figures and a locally generated PDF report.

## Suggested Structure

| Section | Time | What to show |
|---|---|---|
| Intro | 0:00 - 0:30 | Topic, branch name, and what was rerun |
| Local platform | 0:30 - 1:15 | Rancher Desktop, K3s, RabbitMQ, baseline + KEDA namespaces |
| Baseline trial clip | 1:15 - 2:15 | `kubectl get pods -n baseline -w` during a burst |
| KEDA trial clip | 2:15 - 3:15 | `kubectl get pods -n keda -w` during a burst |
| Results | 3:15 - 5:30 | `results/summary.csv` and the four fresh figures |
| Closing | 5:30 - 6:00 | What changed from the original hypothesis and why |

## Key Talking Points

- This rerun was executed on a clean branch:
  `rerun-20260423-fresh-artifacts`.
- The local environment was Rancher Desktop with 4 CPU and 8 GiB memory.
- Six fresh trials were collected: three baseline and three KEDA.
- The fresh rerun did not reproduce the expected "KEDA faster than HPA"
  outcome; instead, HPA reacted faster on average in this local setup.
- The branch also contains cross-platform fixes that were required to make the
  experiment run reliably on macOS and arm64 hardware.

## On-screen Assets

- `results/figures/fig1-pod-scaling-timeline.png`
- `results/figures/fig2-queue-depth-timeline.png`
- `results/figures/fig3-reaction-latency-bar.png`
- `results/figures/fig4-throughput-comparison.png`
- `report/main.pdf`

## Recording Checklist

- [ ] Show the Git branch in terminal once.
- [ ] Show `kubectl get pods -A`.
- [ ] Show one baseline raw CSV and one KEDA raw CSV.
- [ ] Show `results/summary.csv`.
- [ ] Show the final `report/main.pdf`.

## Closing Script Draft

> This branch is a fully fresh rerun of the experiment on a clean worktree.
> We rebuilt the consumer image, redeployed RabbitMQ, HPA, and KEDA, collected
> six new CSV traces, regenerated the figures, and produced a new PDF report.
> In this local rerun, HPA reacted faster on average than KEDA, which is a
> useful reminder that autoscaling results are sensitive to the runtime
> environment and instrumentation path.
