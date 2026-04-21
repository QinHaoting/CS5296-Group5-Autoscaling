"""Metric computation helpers for the HPA vs KEDA comparison.

The raw CSVs produced by ``scripts/collect-metrics.sh`` contain per-second
samples of pod count and queue depth. Given those we derive headline numbers
per experiment trial along three axes:

* Responsiveness (how fast the scaler reacts)
    - ``reaction_latency_s``: time between the load spike and the first new
      Pod reaching Ready.
    - ``scale_up_time_s``: time to reach the peak pod count observed during
      the trial.
* User-visible effect (queue + throughput)
    - ``drain_time_s``: time from the end of load injection until the queue
      is empty.
    - ``avg_throughput``: mean deliver rate during the drain window.
* Resource usage / cost
    - ``peak_pods``: maximum ready pod count observed.
    - ``scale_down_start_s``: time from end-of-burst until pod count first
      drops below peak.
    - ``scale_down_time_s``: time from end-of-burst until pod count returns
      to its initial value (``minReplicas``).
    - ``pod_seconds_overshoot``: integral of ``(pod_ready - minReplicas)``
      over the full trial — a cost-proxy. Lower means fewer over-provisioned
      pod-seconds.
"""
from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

import numpy as np
import pandas as pd


REQUIRED_COLUMNS = {
    "ts_ms",
    "pod_total",
    "pod_ready",
    "queue_depth",
    "rate_in",
    "rate_out",
    "deliver_total",
    "publish_total",
}


@dataclass
class TrialMetrics:
    group: str
    run: int
    reaction_latency_s: float
    scale_up_time_s: float
    drain_time_s: float
    peak_pods: int
    avg_throughput: float
    messages_delivered: int
    scale_down_start_s: float
    scale_down_time_s: float
    final_pods: int
    pod_seconds_overshoot: float


def load_trial(csv_path: Path) -> pd.DataFrame:
    df = pd.read_csv(csv_path)
    missing = REQUIRED_COLUMNS - set(df.columns)
    if missing:
        raise ValueError(f"{csv_path} is missing columns: {missing}")
    df = df.sort_values("ts_ms").reset_index(drop=True)
    df["t_s"] = (df["ts_ms"] - df.loc[0, "ts_ms"]) / 1000.0
    return df


def detect_load_window(df: pd.DataFrame, publish_threshold: float = 50.0):
    """Return (load_start_s, load_end_s) based on the RabbitMQ publish rate."""
    hot = df[df["rate_in"] >= publish_threshold]
    if hot.empty:
        return None, None
    return float(hot["t_s"].iloc[0]), float(hot["t_s"].iloc[-1])


def reaction_latency(df: pd.DataFrame, load_start: float) -> float:
    """Time from load_start until pod_ready rises above its baseline."""
    baseline = int(df.loc[0, "pod_ready"])
    after = df[(df["t_s"] >= load_start) & (df["pod_ready"] > baseline)]
    if after.empty:
        return float("nan")
    return float(after["t_s"].iloc[0] - load_start)


def scale_up_time(df: pd.DataFrame, load_start: float) -> tuple[float, int]:
    """Time from load_start until pod_ready hits its peak; returns (seconds, peak)."""
    peak = int(df["pod_ready"].max())
    at_peak = df[(df["t_s"] >= load_start) & (df["pod_ready"] >= peak)]
    if at_peak.empty:
        return float("nan"), peak
    return float(at_peak["t_s"].iloc[0] - load_start), peak


def drain_time(df: pd.DataFrame, load_end: float) -> float:
    """Time from load_end until the queue first reaches zero."""
    after = df[(df["t_s"] >= load_end) & (df["queue_depth"] == 0)]
    if after.empty:
        return float("nan")
    return float(after["t_s"].iloc[0] - load_end)


def avg_throughput(df: pd.DataFrame, load_start: float, load_end: float) -> float:
    """Average deliver rate during the drain window (load_start .. queue empty)."""
    drain_end = load_end + drain_time(df, load_end)
    window = df[(df["t_s"] >= load_start) & (df["t_s"] <= drain_end)]
    if window.empty:
        return float("nan")
    return float(window["rate_out"].mean())


def messages_delivered(df: pd.DataFrame) -> int:
    if df["deliver_total"].empty:
        return 0
    return int(df["deliver_total"].max() - df.loc[0, "deliver_total"])


def _peak_reached_at(df: pd.DataFrame, load_end: float, peak: int) -> float | None:
    """Earliest time at or after load_end where pod_ready first reaches peak."""
    at_peak = df[(df["t_s"] >= load_end) & (df["pod_ready"] >= peak)]
    if at_peak.empty:
        return None
    return float(at_peak["t_s"].iloc[0])


def scale_down_start(df: pd.DataFrame, load_end: float, peak: int) -> float:
    """Time from load_end until pod_ready first drops below peak (after reaching peak)."""
    peak_t = _peak_reached_at(df, load_end, peak)
    if peak_t is None:
        return float("nan")
    dropping = df[(df["t_s"] >= peak_t) & (df["pod_ready"] < peak)]
    if dropping.empty:
        return float("nan")
    return float(dropping["t_s"].iloc[0] - load_end)


def scale_down_time(df: pd.DataFrame, load_end: float, peak: int, min_replicas: int) -> float:
    """Time from load_end until pod_ready returns to min_replicas (after reaching peak)."""
    peak_t = _peak_reached_at(df, load_end, peak)
    if peak_t is None:
        return float("nan")
    back_to_min = df[(df["t_s"] >= peak_t) & (df["pod_ready"] <= min_replicas)]
    if back_to_min.empty:
        return float("nan")
    return float(back_to_min["t_s"].iloc[0] - load_end)


def pod_seconds_overshoot(df: pd.DataFrame, min_replicas: int) -> float:
    """Trapezoidal integral of (pod_ready - min_replicas) over the trial."""
    excess = (df["pod_ready"] - min_replicas).clip(lower=0).to_numpy()
    t = df["t_s"].to_numpy()
    if len(t) < 2:
        return 0.0
    # numpy>=2.0 renamed np.trapz -> np.trapezoid; stay compatible.
    trap = getattr(np, "trapezoid", None) or np.trapz
    return float(trap(excess, t))


def compute_all(csv_path: Path, group: str, run: int) -> TrialMetrics:
    df = load_trial(csv_path)
    load_start, load_end = detect_load_window(df)
    if load_start is None:
        raise RuntimeError(f"No load burst detected in {csv_path}")

    min_replicas = int(df.loc[0, "pod_ready"])
    reaction = reaction_latency(df, load_start)
    scale_t, peak = scale_up_time(df, load_start)
    drain = drain_time(df, load_end)
    tput = avg_throughput(df, load_start, load_end)
    delivered = messages_delivered(df)
    sd_start = scale_down_start(df, load_end, peak)
    sd_time = scale_down_time(df, load_end, peak, min_replicas)
    final_pods_val = int(df["pod_ready"].iloc[-1])
    overshoot = pod_seconds_overshoot(df, min_replicas)

    return TrialMetrics(
        group=group,
        run=run,
        reaction_latency_s=reaction,
        scale_up_time_s=scale_t,
        drain_time_s=drain,
        peak_pods=peak,
        avg_throughput=tput,
        messages_delivered=delivered,
        scale_down_start_s=sd_start,
        scale_down_time_s=sd_time,
        final_pods=final_pods_val,
        pod_seconds_overshoot=overshoot,
    )
