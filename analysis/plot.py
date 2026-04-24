"""Generate the four headline figures for the final report.

Expected input layout (after running scripts/run-experiment.sh):

    results/raw/baseline-run1.csv
    results/raw/baseline-run2.csv
    results/raw/keda-run1.csv
    results/raw/keda-run2.csv

Each CSV contains per-second samples emitted by ``collect-metrics.sh``.
Figures are written to ``results/figures/``.

Usage:
    python analysis/plot.py              # uses default results/ directory
    python analysis/plot.py --results /path/to/results
"""
from __future__ import annotations

import argparse
import re
from pathlib import Path

import matplotlib.pyplot as plt
import numpy as np
import pandas as pd

from metrics import TrialMetrics, compute_all, detect_load_window, load_trial

plt.rcParams.update({
    "figure.dpi": 120,
    "savefig.dpi": 200,
    "axes.grid": True,
    "grid.alpha": 0.3,
    "font.size": 11,
})

GROUP_COLOURS = {"baseline": "#1f77b4", "keda": "#d62728"}
GROUP_LABELS = {"baseline": "Baseline HPA (CPU-based)", "keda": "KEDA (queue-based)"}


def discover_trials(raw_dir: Path) -> dict[str, list[Path]]:
    pattern = re.compile(r"^(baseline|keda)-run(\d+)\.csv$")
    trials: dict[str, list[Path]] = {"baseline": [], "keda": []}
    for csv in sorted(raw_dir.glob("*.csv")):
        m = pattern.match(csv.name)
        if m:
            trials[m.group(1)].append(csv)
    return trials


def figure_pod_scaling(trials: dict[str, list[Path]], out_path: Path) -> None:
    fig, ax = plt.subplots(figsize=(8, 4.5))
    for group, paths in trials.items():
        for idx, p in enumerate(paths):
            df = load_trial(p)
            label = GROUP_LABELS[group] if idx == 0 else None
            ax.plot(df["t_s"], df["pod_ready"], color=GROUP_COLOURS[group],
                    alpha=0.4 if idx > 0 else 0.9, linewidth=2,
                    label=label)
    ax.set_xlabel("Time (s)")
    ax.set_ylabel("Ready Pods")
    ax.set_title("Figure 1 — Pod count over time during burst load")
    ax.legend(loc="best")
    fig.tight_layout()
    fig.savefig(out_path)
    plt.close(fig)


def figure_queue_depth(trials: dict[str, list[Path]], out_path: Path) -> None:
    fig, ax = plt.subplots(figsize=(8, 4.5))
    for group, paths in trials.items():
        for idx, p in enumerate(paths):
            df = load_trial(p)
            label = GROUP_LABELS[group] if idx == 0 else None
            ax.plot(df["t_s"], df["queue_depth"], color=GROUP_COLOURS[group],
                    alpha=0.4 if idx > 0 else 0.9, linewidth=2,
                    label=label)
    ax.set_xlabel("Time (s)")
    ax.set_ylabel("Queue depth (messages)")
    ax.set_title("Figure 2 — Queue depth over time")
    ax.legend(loc="best")
    fig.tight_layout()
    fig.savefig(out_path)
    plt.close(fig)


def aggregate_trials(trials: dict[str, list[Path]]) -> pd.DataFrame:
    rows: list[TrialMetrics] = []
    for group, paths in trials.items():
        for p in paths:
            run = int(re.search(r"run(\d+)", p.stem).group(1))
            try:
                rows.append(compute_all(p, group, run))
            except RuntimeError as e:
                print(f"skipping {p}: {e}")
    return pd.DataFrame([row.__dict__ for row in rows])


def figure_reaction_latency_bar(summary: pd.DataFrame, out_path: Path) -> None:
    if summary.empty:
        print("no summary data available — skipping reaction latency figure")
        return
    fig, ax = plt.subplots(figsize=(6, 4))
    groups = ["baseline", "keda"]
    means = [summary[summary["group"] == g]["reaction_latency_s"].mean() for g in groups]
    stds = [summary[summary["group"] == g]["reaction_latency_s"].std(ddof=0) for g in groups]
    colours = [GROUP_COLOURS[g] for g in groups]
    xpos = np.arange(len(groups))
    ax.bar(xpos, means, yerr=stds, color=colours, capsize=6, alpha=0.85)
    ax.set_xticks(xpos, [GROUP_LABELS[g] for g in groups])
    ax.set_ylabel("Reaction latency (s)")
    ax.set_title("Figure 3 — Reaction latency (lower is better)")
    for i, v in enumerate(means):
        if not np.isnan(v):
            ax.text(i, v, f"{v:.2f}s", ha="center", va="bottom", fontsize=11)
    fig.tight_layout()
    fig.savefig(out_path)
    plt.close(fig)


def figure_throughput_bar(summary: pd.DataFrame, out_path: Path) -> None:
    if summary.empty:
        print("no summary data available — skipping throughput figure")
        return
    fig, ax = plt.subplots(figsize=(6, 4))
    groups = ["baseline", "keda"]
    means = [summary[summary["group"] == g]["avg_throughput"].mean() for g in groups]
    stds = [summary[summary["group"] == g]["avg_throughput"].std(ddof=0) for g in groups]
    colours = [GROUP_COLOURS[g] for g in groups]
    xpos = np.arange(len(groups))
    ax.bar(xpos, means, yerr=stds, color=colours, capsize=6, alpha=0.85)
    ax.set_xticks(xpos, [GROUP_LABELS[g] for g in groups])
    ax.set_ylabel("Avg throughput (msg/s)")
    ax.set_title("Figure 4 — Average consumption throughput")
    for i, v in enumerate(means):
        if not np.isnan(v):
            ax.text(i, v, f"{v:.0f}", ha="center", va="bottom", fontsize=11)
    fig.tight_layout()
    fig.savefig(out_path)
    plt.close(fig)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--results", default=Path(__file__).resolve().parents[1] / "results",
                        type=Path, help="Root results directory (contains raw/ and figures/)")
    args = parser.parse_args()

    raw_dir = args.results / "raw"
    fig_dir = args.results / "figures"
    fig_dir.mkdir(parents=True, exist_ok=True)

    trials = discover_trials(raw_dir)
    n_baseline = len(trials["baseline"])
    n_keda = len(trials["keda"])
    print(f"discovered trials: baseline={n_baseline}, keda={n_keda}")
    if not any(trials.values()):
        raise SystemExit(f"no trial CSVs found in {raw_dir}")

    figure_pod_scaling(trials, fig_dir / "fig1-pod-scaling-timeline.png")
    figure_queue_depth(trials, fig_dir / "fig2-queue-depth-timeline.png")

    summary = aggregate_trials(trials)
    summary_path = args.results / "summary.csv"
    summary.to_csv(summary_path, index=False)
    print(f"summary written to {summary_path}")

    figure_reaction_latency_bar(summary, fig_dir / "fig3-reaction-latency-bar.png")
    figure_throughput_bar(summary, fig_dir / "fig4-throughput-comparison.png")
    print(f"figures written to {fig_dir}")


if __name__ == "__main__":
    main()
