# Analysis Module

Computes headline metrics and draws four figures from the per-second CSVs
produced during each experiment trial.

## Install

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

## Run

```bash
python plot.py
```

Figures are written to `../results/figures/` and a per-trial summary to
`../results/summary.csv`.

## Headline metrics

| Metric | Meaning |
|---|---|
| `reaction_latency_s` | Time from load start to the first *new* pod entering Ready. |
| `scale_up_time_s` | Time from load start to reaching the peak pod count. |
| `drain_time_s` | Time from end-of-burst to queue depth = 0. |
| `peak_pods` | Maximum Ready pod count observed in the trial. |
| `avg_throughput` | Mean consumer deliver rate during the drain window. |
| `messages_delivered` | Total messages consumed during the trial. |

## Figures

1. `fig1-pod-scaling-timeline.png` — Pod count over time (Baseline vs KEDA).
2. `fig2-queue-depth-timeline.png` — Queue depth over time.
3. `fig3-reaction-latency-bar.png` — Mean reaction latency with error bars.
4. `fig4-throughput-comparison.png` — Mean throughput with error bars.
