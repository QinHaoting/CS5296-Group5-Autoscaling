"""Generate the headline figures for the final report.

Figures produced (in ``results/figures/``):

    fig1-run1-timeline.png      baseline-run1 vs keda-run1 (pod + queue, burst-aligned)
    fig2-run2-timeline.png      same for run 2
    fig3-run3-timeline.png      same for run 3
    fig4-response-bar.png       reaction / scale-up / drain (mean +- std, bars)
    fig5-scale-down-bar.png     scale-down-start / scale-down-time (bars)
    fig6-overshoot-cost.png     pod-seconds overshoot (cost proxy, bars)

The per-run timeline figures each show the baseline run and the matching
KEDA run on the same burst-aligned time axis, with the 10 s burst window and
the reaction-latency / scale-up landmarks annotated. Use these to talk about
individual runs in the report; use fig4-6 to summarise the aggregate.

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
GROUP_LABELS = {"baseline": "Baseline HPA (CPU)", "keda": "KEDA (queueLength)"}


def discover_trials(raw_dir: Path) -> dict[str, list[Path]]:
    pattern = re.compile(r"^(baseline|keda)-run(\d+)\.csv$")
    trials: dict[str, list[Path]] = {"baseline": [], "keda": []}
    for csv in sorted(raw_dir.glob("*.csv")):
        m = pattern.match(csv.name)
        if m:
            trials[m.group(1)].append(csv)
    return trials


# ---------------------------------------------------------------------------
# Per-run timeline figures
# ---------------------------------------------------------------------------

def _align_to_burst(df: pd.DataFrame) -> tuple[pd.DataFrame, float, float]:
    """Return a copy of df with ``t_rel`` rebased to the start of the burst.

    Also returns (burst_start_abs, burst_end_abs) in the original t_s frame.
    """
    burst_start, burst_end = detect_load_window(df)
    if burst_start is None:
        burst_start = 0.0
        burst_end = 0.0
    out = df.copy()
    out["t_rel"] = out["t_s"] - burst_start
    return out, burst_start, burst_end


def _first_time_ge(df: pd.DataFrame, col: str, threshold: int, t_min: float = 0.0) -> float | None:
    sel = df[(df["t_rel"] >= t_min) & (df[col] >= threshold)]
    if sel.empty:
        return None
    return float(sel["t_rel"].iloc[0])


def _first_time_lt(df: pd.DataFrame, col: str, threshold: int, t_min: float = 0.0) -> float | None:
    sel = df[(df["t_rel"] >= t_min) & (df[col] < threshold)]
    if sel.empty:
        return None
    return float(sel["t_rel"].iloc[0])


def figure_run_pair(baseline_csv: Path, keda_csv: Path, run_idx: int, out_path: Path) -> None:
    """Draw baseline run N and KEDA run N on one figure, two stacked panels.

    Panels (shared x-axis, t=0 = burst start):
      top:    pod_ready timeline
      bottom: queue_depth timeline

    Annotations per scaler:
      reaction  = first time pod_ready > minReplicas  (dashed vertical)
      peak      = first time pod_ready == maxReplicas (dotted vertical)
      scale-dn  = first time pod_ready < peak after peak reached (dash-dot)
    """
    df_b_raw = load_trial(baseline_csv)
    df_k_raw = load_trial(keda_csv)
    df_b, bb_start, bb_end = _align_to_burst(df_b_raw)
    df_k, kb_start, kb_end = _align_to_burst(df_k_raw)

    burst_len = max(bb_end - bb_start, kb_end - kb_start, 10.0)

    fig, (ax1, ax2) = plt.subplots(
        2, 1, figsize=(11, 7), sharex=True,
        gridspec_kw={"height_ratios": [1, 1]},
    )

    for ax in (ax1, ax2):
        ax.axvspan(0, burst_len, color="#ffcc00", alpha=0.18, label="burst window")

    # Top panel: pod_ready
    ax1.plot(df_b["t_rel"], df_b["pod_ready"], color=GROUP_COLOURS["baseline"],
             linewidth=2.2, label=GROUP_LABELS["baseline"])
    ax1.plot(df_k["t_rel"], df_k["pod_ready"], color=GROUP_COLOURS["keda"],
             linewidth=2.2, label=GROUP_LABELS["keda"])
    y_top = max(df_b["pod_ready"].max(), df_k["pod_ready"].max()) + 1
    ax1.set_ylabel("Ready pods (count)")
    ax1.set_ylim(0, y_top)
    ax1.set_title(f"Run {run_idx}: pod count and queue depth "
                  f"(t = 0 at burst start; burst window shaded)")
    ax1.legend(loc="upper right", fontsize=9)

    # Per-scaler annotations. Stack labels vertically so they never overlap:
    # baseline on top row, keda on bottom row, inside the plot.
    y_label_rows = {"baseline": y_top - 0.55, "keda": y_top - 1.55}
    tag_display = {"baseline": "Baseline HPA", "keda": "KEDA"}
    for df, colour, tag in ((df_b, GROUP_COLOURS["baseline"], "baseline"),
                            (df_k, GROUP_COLOURS["keda"], "keda")):
        min_r = int(df.iloc[0]["pod_ready"])
        peak = int(df["pod_ready"].max())
        t_react = _first_time_ge(df, "pod_ready", min_r + 1)
        t_peak = _first_time_ge(df, "pod_ready", peak)
        t_sd = (_first_time_lt(df, "pod_ready", peak, t_min=t_peak)
                if t_peak is not None else None)

        parts = []
        if t_react is not None:
            ax1.axvline(t_react, color=colour, linestyle="--", linewidth=1, alpha=0.6)
            parts.append(f"react {t_react:.0f}s")
        if t_peak is not None:
            ax1.axvline(t_peak, color=colour, linestyle=":", linewidth=1, alpha=0.6)
            parts.append(f"peak {t_peak:.0f}s")
        if t_sd is not None:
            ax1.axvline(t_sd, color=colour, linestyle="-.", linewidth=1, alpha=0.6)
            parts.append(f"scale-down {t_sd:.0f}s")
        if parts:
            ax1.text(5, y_label_rows[tag],
                     f"{tag_display[tag]}: " + " | ".join(parts),
                     fontsize=9, color=colour,
                     bbox=dict(boxstyle="round,pad=0.25", facecolor="white",
                               edgecolor=colour, alpha=0.85))

    # Bottom panel: queue_depth
    ax2.plot(df_b["t_rel"], df_b["queue_depth"], color=GROUP_COLOURS["baseline"],
             linewidth=2.2, label=GROUP_LABELS["baseline"])
    ax2.plot(df_k["t_rel"], df_k["queue_depth"], color=GROUP_COLOURS["keda"],
             linewidth=2.2, label=GROUP_LABELS["keda"])
    ax2.set_xlabel("Time since burst start (s)")
    ax2.set_ylabel("Queue depth (msgs)")
    ax2.legend(loc="upper right", fontsize=9)

    # Show pre-burst warm-up + burst + drain + scale-down: clip to -20 .. 400 s
    # so baseline's lack of scale-down (pods stay at 6) is visible alongside
    # KEDA's descent back towards minReplicas.
    ax2.set_xlim(-20, 400)

    fig.tight_layout()
    fig.savefig(out_path)
    plt.close(fig)


# ---------------------------------------------------------------------------
# Aggregated bar charts
# ---------------------------------------------------------------------------

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


def _bar_mean_std(ax, summary: pd.DataFrame, metric: str, ylabel: str, fmt: str = "{:.1f}") -> None:
    groups = ["baseline", "keda"]
    means = [summary[summary["group"] == g][metric].mean() for g in groups]
    stds = [summary[summary["group"] == g][metric].std(ddof=1) for g in groups]
    xpos = np.arange(len(groups))
    ax.bar(xpos, means, yerr=stds, capsize=6, alpha=0.85,
           color=[GROUP_COLOURS[g] for g in groups])
    ax.set_xticks(xpos, [GROUP_LABELS[g] for g in groups])
    ax.set_ylabel(ylabel)
    for i, v in enumerate(means):
        if not np.isnan(v):
            ax.text(i, v, fmt.format(v), ha="center", va="bottom", fontsize=10)


def figure_response_bar(summary: pd.DataFrame, out_path: Path) -> None:
    """Responsiveness side-by-side: reaction / scale-up / drain."""
    if summary.empty:
        return
    fig, axes = plt.subplots(1, 3, figsize=(12, 4.2))
    _bar_mean_std(axes[0], summary, "reaction_latency_s",
                  "Reaction latency (s)", "{:.1f}s")
    axes[0].set_title("(a) Time to first new Ready pod")
    _bar_mean_std(axes[1], summary, "scale_up_time_s",
                  "Scale-up time (s)", "{:.1f}s")
    axes[1].set_title("(b) Time to reach peak pods")
    _bar_mean_std(axes[2], summary, "drain_time_s",
                  "Queue drain time (s)", "{:.1f}s")
    axes[2].set_title("(c) Time to drain the queue")
    fig.suptitle("Responsiveness metrics (mean ± std, n = 3; lower is better)",
                 fontsize=11)
    fig.tight_layout()
    fig.savefig(out_path)
    plt.close(fig)


def figure_scale_down_bar(summary: pd.DataFrame, out_path: Path,
                          ceiling_s: int = 355) -> None:
    """Scale-down behaviour: when it starts and how many pods remain at trial end.

    If a group does not trigger scale-down anywhere inside a trial, render
    that bar at ``ceiling_s`` with a hatched pattern and a ">trial-length"
    annotation. ``ceiling_s`` should be slightly above the longest observed
    scale-down-start time so the contrast is legible.
    """
    if summary.empty:
        return
    fig, axes = plt.subplots(1, 2, figsize=(9, 4.4))

    ax = axes[0]
    groups = ["baseline", "keda"]
    means, stds, captured = [], [], []
    for g in groups:
        vals = summary[summary["group"] == g]["scale_down_start_s"].dropna()
        captured.append(len(vals))
        if vals.empty:
            means.append(ceiling_s)
            stds.append(0.0)
        else:
            means.append(vals.mean())
            stds.append(vals.std(ddof=1) if len(vals) > 1 else 0.0)
    xpos = np.arange(len(groups))
    ax.bar(xpos, means, yerr=stds, capsize=6, alpha=0.85,
           color=[GROUP_COLOURS[g] for g in groups],
           hatch=["///" if c == 0 else "" for c in captured])
    ax.set_xticks(xpos, [GROUP_LABELS[g] for g in groups])
    ax.set_ylabel("Time after burst end (s)")
    ax.set_title("(a) First pod removal after burst")
    ax.set_ylim(0, ceiling_s * 1.18)
    for i, (v, cap) in enumerate(zip(means, captured)):
        if cap == 0:
            ax.text(i, v / 2.0, "not observed\n(CPU > 50% for\nentire trial)",
                    ha="center", va="center", fontsize=9,
                    color="white", fontweight="bold")
        else:
            ax.text(i, v, f"{v:.0f}s", ha="center", va="bottom", fontsize=10)

    ax = axes[1]
    _bar_mean_std(ax, summary, "final_pods",
                  "Ready pods remaining (count)",
                  "{:.1f}")
    ax.set_title("(b) Ready pods at end of trial")

    fig.suptitle("Scale-down behaviour (mean ± std, n = 3; lower is better)",
                 fontsize=11)
    fig.tight_layout()
    fig.savefig(out_path)
    plt.close(fig)


def figure_overshoot_cost(summary: pd.DataFrame, out_path: Path) -> None:
    """Cost proxy: pod-seconds overshoot above minReplicas."""
    if summary.empty:
        return
    fig, ax = plt.subplots(figsize=(6.8, 4.6))
    _bar_mean_std(ax, summary, "pod_seconds_overshoot",
                  "Pod-seconds above minReplicas",
                  "{:.0f}")
    ax.set_title("Resource over-provisioning\n"
                 "(mean ± std, n = 3; lower is better)", fontsize=11)
    fig.tight_layout()
    fig.savefig(out_path)
    plt.close(fig)


# ---------------------------------------------------------------------------
# main
# ---------------------------------------------------------------------------

def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--results", default=Path(__file__).resolve().parents[1] / "results",
                        type=Path, help="Root results directory (contains raw/ and figures/)")
    args = parser.parse_args()

    raw_dir = args.results / "raw"
    fig_dir = args.results / "figures"
    fig_dir.mkdir(parents=True, exist_ok=True)

    trials = discover_trials(raw_dir)
    print(f"discovered trials: baseline={len(trials['baseline'])}, keda={len(trials['keda'])}")
    if not any(trials.values()):
        raise SystemExit(f"no trial CSVs found in {raw_dir}")

    # Per-run timeline figures (pair baseline-runN with keda-runN)
    baseline_by_run = {int(re.search(r"run(\d+)", p.stem).group(1)): p for p in trials["baseline"]}
    keda_by_run = {int(re.search(r"run(\d+)", p.stem).group(1)): p for p in trials["keda"]}
    paired_runs = sorted(set(baseline_by_run) & set(keda_by_run))
    for i, run in enumerate(paired_runs, start=1):
        out = fig_dir / f"fig{i}-run{run}-timeline.png"
        figure_run_pair(baseline_by_run[run], keda_by_run[run], run, out)
        print(f"wrote {out}")

    # Summary CSV
    summary = aggregate_trials(trials)
    summary_path = args.results / "summary.csv"
    summary.to_csv(summary_path, index=False)
    print(f"summary written to {summary_path}")

    # Aggregate bar charts (numbered continuing from per-run)
    next_idx = len(paired_runs) + 1
    figure_response_bar(summary, fig_dir / f"fig{next_idx}-response-bar.png")
    figure_scale_down_bar(summary, fig_dir / f"fig{next_idx + 1}-scale-down-bar.png")
    figure_overshoot_cost(summary, fig_dir / f"fig{next_idx + 2}-overshoot-cost.png")
    print(f"figures written to {fig_dir}")


if __name__ == "__main__":
    main()
