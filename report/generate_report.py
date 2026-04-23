from __future__ import annotations

import csv
import statistics
from collections import defaultdict
from pathlib import Path

from reportlab.lib import colors
from reportlab.lib.enums import TA_CENTER
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.lib.units import cm
from reportlab.platypus import (
    Image,
    PageBreak,
    Paragraph,
    SimpleDocTemplate,
    Spacer,
    Table,
    TableStyle,
)


REPORT_DIR = Path(__file__).resolve().parent
REPO_ROOT = REPORT_DIR.parent
RESULTS_DIR = REPO_ROOT / "results"
SUMMARY_CSV = RESULTS_DIR / "summary.csv"
FIGURES_DIR = RESULTS_DIR / "figures"
OUTPUT_PDF = REPORT_DIR / "main.pdf"


def load_rows() -> list[dict[str, object]]:
    with SUMMARY_CSV.open("r", encoding="utf-8", newline="") as f:
        reader = csv.DictReader(f)
        rows = []
        for row in reader:
            rows.append(
                {
                    "group": row["group"],
                    "run": int(row["run"]),
                    "reaction_latency_s": float(row["reaction_latency_s"]),
                    "scale_up_time_s": float(row["scale_up_time_s"]),
                    "drain_time_s": float(row["drain_time_s"]),
                    "peak_pods": float(row["peak_pods"]),
                    "avg_throughput": float(row["avg_throughput"]),
                    "messages_delivered": float(row["messages_delivered"]),
                }
            )
    return rows


def grouped_stats(rows: list[dict[str, object]]) -> dict[str, dict[str, tuple[float, float]]]:
    metrics = [
        "reaction_latency_s",
        "scale_up_time_s",
        "drain_time_s",
        "peak_pods",
        "avg_throughput",
        "messages_delivered",
    ]
    grouped: dict[str, dict[str, list[float]]] = defaultdict(lambda: defaultdict(list))
    for row in rows:
        group = str(row["group"])
        for metric in metrics:
            grouped[group][metric].append(float(row[metric]))

    stats: dict[str, dict[str, tuple[float, float]]] = {}
    for group, metric_map in grouped.items():
        stats[group] = {}
        for metric, values in metric_map.items():
            mean_v = statistics.mean(values)
            std_v = statistics.pstdev(values) if len(values) > 1 else 0.0
            stats[group][metric] = (mean_v, std_v)
    return stats


def build_styles():
    styles = getSampleStyleSheet()
    styles.add(
        ParagraphStyle(
            name="TitleCenter",
            parent=styles["Title"],
            alignment=TA_CENTER,
            fontName="Helvetica-Bold",
            fontSize=18,
            leading=22,
            spaceAfter=12,
        )
    )
    styles.add(
        ParagraphStyle(
            name="SmallBody",
            parent=styles["BodyText"],
            fontSize=9,
            leading=12,
            spaceAfter=6,
        )
    )
    styles.add(
        ParagraphStyle(
            name="Caption",
            parent=styles["BodyText"],
            fontSize=8,
            leading=10,
            textColor=colors.HexColor("#444444"),
            spaceAfter=8,
        )
    )
    return styles


def comparison_table(stats):
    metrics = [
        ("Reaction latency (s)", "reaction_latency_s", "lower is better"),
        ("Scale-up time (s)", "scale_up_time_s", "lower is better"),
        ("Drain time (s)", "drain_time_s", "lower is better"),
        ("Peak pods", "peak_pods", "same max for both groups"),
        ("Avg throughput (msg/s)", "avg_throughput", "higher is better"),
        ("Messages delivered", "messages_delivered", "context only"),
    ]
    data = [["Metric", "Baseline mean +/- std", "KEDA mean +/- std", "Note"]]
    for label, key, note in metrics:
        b_mean, b_std = stats["baseline"][key]
        k_mean, k_std = stats["keda"][key]
        data.append(
            [
                label,
                f"{b_mean:.2f} +/- {b_std:.2f}",
                f"{k_mean:.2f} +/- {k_std:.2f}",
                note,
            ]
        )

    table = Table(data, colWidths=[5.1 * cm, 4.0 * cm, 4.0 * cm, 3.2 * cm], repeatRows=1)
    table.setStyle(
        TableStyle(
            [
                ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#1f2937")),
                ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
                ("GRID", (0, 0), (-1, -1), 0.5, colors.HexColor("#d1d5db")),
                ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
                ("FONTNAME", (0, 1), (-1, -1), "Helvetica"),
                ("FONTSIZE", (0, 0), (-1, -1), 8),
                ("LEADING", (0, 0), (-1, -1), 10),
                ("VALIGN", (0, 0), (-1, -1), "TOP"),
                ("ROWBACKGROUNDS", (0, 1), (-1, -1), [colors.white, colors.HexColor("#f9fafb")]),
            ]
        )
    )
    return table


def controller_table():
    data = [
        ["Dimension", "Baseline (HPA)", "KEDA"],
        ["Signal source", "CPU utilization from metrics-server", "RabbitMQ queue depth via KEDA trigger"],
        ["Decision loop", "HorizontalPodAutoscaler controller", "KEDA operator and ScaledObject"],
        ["Min / max replicas", "1 / 10", "1 / 10"],
        ["Expected strength", "Stable and built-in", "Closer to business backlog"],
        ["Expected risk", "Can react after CPU is already hot", "Depends on polling interval and trigger path"],
    ]
    table = Table(data, colWidths=[4.2 * cm, 5.8 * cm, 6.0 * cm], repeatRows=1)
    table.setStyle(
        TableStyle(
            [
                ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#1d4ed8")),
                ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
                ("GRID", (0, 0), (-1, -1), 0.5, colors.HexColor("#d1d5db")),
                ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
                ("FONTSIZE", (0, 0), (-1, -1), 8),
                ("LEADING", (0, 0), (-1, -1), 10),
                ("VALIGN", (0, 0), (-1, -1), "TOP"),
                ("ROWBACKGROUNDS", (0, 1), (-1, -1), [colors.white, colors.HexColor("#eff6ff")]),
            ]
        )
    )
    return table


def environment_table():
    data = [
        ["Item", "Value"],
        ["Branch", "rerun-20260423-fresh-artifacts"],
        ["Cluster runtime", "Rancher Desktop 1.22 with local K3s"],
        ["VM sizing", "4 vCPU / 8 GiB RAM"],
        ["Broker", "RabbitMQ 3.12 management image"],
        ["Consumer image", "cs5296-consumer:rerun-20260423-local"],
        ["Burst pattern", "10 s warm-up at 5 msg/s, then 10 s active burst targeting 1000 msg/s"],
        ["Observation tail", "180 s after publishing"],
        ["Trial count", "6 total runs: baseline x3 and keda x3"],
    ]
    table = Table(data, colWidths=[4.8 * cm, 11.0 * cm], repeatRows=1)
    table.setStyle(
        TableStyle(
            [
                ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#7c3aed")),
                ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
                ("GRID", (0, 0), (-1, -1), 0.5, colors.HexColor("#d1d5db")),
                ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
                ("FONTSIZE", (0, 0), (-1, -1), 8),
                ("LEADING", (0, 0), (-1, -1), 10),
                ("VALIGN", (0, 0), (-1, -1), "TOP"),
                ("ROWBACKGROUNDS", (0, 1), (-1, -1), [colors.white, colors.HexColor("#faf5ff")]),
            ]
        )
    )
    return table


def metric_definition_table():
    data = [
        ["Metric", "Definition used in this rerun"],
        ["Reaction latency", "Seconds from burst start to the first observed scale-up event."],
        ["Scale-up time", "Seconds from burst start until the group reached its peak pod count."],
        ["Drain time", "Seconds from burst start until the queue returned to zero backlog."],
        ["Average throughput", "Delivered messages divided by the active send window used by the analysis script."],
        ["Messages delivered", "Messages observed as delivered by the end of the collected trace."],
    ]
    table = Table(data, colWidths=[4.4 * cm, 11.4 * cm], repeatRows=1)
    table.setStyle(
        TableStyle(
            [
                ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#0f766e")),
                ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
                ("GRID", (0, 0), (-1, -1), 0.5, colors.HexColor("#d1d5db")),
                ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
                ("FONTSIZE", (0, 0), (-1, -1), 7.5),
                ("LEADING", (0, 0), (-1, -1), 9),
                ("VALIGN", (0, 0), (-1, -1), "TOP"),
                ("ROWBACKGROUNDS", (0, 1), (-1, -1), [colors.white, colors.HexColor("#ecfeff")]),
            ]
        )
    )
    return table


def per_run_table(rows):
    data = [[
        "Group",
        "Run",
        "Reaction (s)",
        "Scale-up (s)",
        "Drain (s)",
        "Peak pods",
        "Avg throughput",
        "Delivered",
    ]]
    for row in rows:
        data.append(
            [
                str(row["group"]),
                str(row["run"]),
                f"{float(row['reaction_latency_s']):.2f}",
                f"{float(row['scale_up_time_s']):.2f}",
                f"{float(row['drain_time_s']):.2f}",
                f"{float(row['peak_pods']):.0f}",
                f"{float(row['avg_throughput']):.2f}",
                f"{float(row['messages_delivered']):.0f}",
            ]
        )
    table = Table(
        data,
        colWidths=[2.0 * cm, 1.2 * cm, 2.3 * cm, 2.3 * cm, 2.2 * cm, 1.8 * cm, 2.6 * cm, 2.4 * cm],
        repeatRows=1,
    )
    table.setStyle(
        TableStyle(
            [
                ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#0f766e")),
                ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
                ("GRID", (0, 0), (-1, -1), 0.5, colors.HexColor("#d1d5db")),
                ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
                ("FONTSIZE", (0, 0), (-1, -1), 8),
                ("ROWBACKGROUNDS", (0, 1), (-1, -1), [colors.white, colors.HexColor("#f9fafb")]),
            ]
        )
    )
    return table


def page_number(canvas, doc):
    canvas.saveState()
    canvas.setFont("Helvetica", 9)
    canvas.setFillColor(colors.HexColor("#6b7280"))
    canvas.drawRightString(A4[0] - 1.5 * cm, 1.0 * cm, f"Page {doc.page}")
    canvas.restoreState()


def add_figure(story, styles, title, filename):
    path = FIGURES_DIR / filename
    if not path.exists():
        return
    story.append(Paragraph(title, styles["Heading2"]))
    story.append(Image(str(path), width=17.0 * cm, height=9.2 * cm))
    story.append(Paragraph(filename, styles["Caption"]))


def build_story(rows, stats):
    styles = build_styles()
    story = []

    baseline_reaction = stats["baseline"]["reaction_latency_s"][0]
    keda_reaction = stats["keda"]["reaction_latency_s"][0]
    baseline_drain = stats["baseline"]["drain_time_s"][0]
    keda_drain = stats["keda"]["drain_time_s"][0]
    baseline_tput = stats["baseline"]["avg_throughput"][0]
    keda_tput = stats["keda"]["avg_throughput"][0]

    story.append(Paragraph("CS5296 Group 5", styles["TitleCenter"]))
    story.append(Paragraph("Fresh Local Rerun Report: HPA vs KEDA", styles["TitleCenter"]))
    story.append(
        Paragraph(
            "Branch: rerun-20260423-fresh-artifacts<br/>"
            "Environment: macOS host + Rancher Desktop K3s (4 CPU / 8 GiB VM)",
            styles["BodyText"],
        )
    )
    story.append(Spacer(1, 0.4 * cm))

    abstract = (
        "This report summarizes a clean rerun of the repository on a new Git "
        "branch and clean worktree. The rerun rebuilt the consumer image, "
        "redeployed RabbitMQ plus both autoscaling strategies, collected six "
        "new trial traces, regenerated the figures, and packaged a fresh PDF "
        "report. In this local rerun, the HPA baseline reacted faster on "
        f"average ({baseline_reaction:.2f}s) than KEDA ({keda_reaction:.2f}s), "
        "while both strategies still reached the configured peak of 10 pods. "
        "The result differs from the original project hypothesis and is likely "
        "sensitive to the local runtime, KEDA polling path, and the producer's "
        "achieved publish rate."
    )
    story.append(Paragraph("<b>Abstract</b>", styles["Heading1"]))
    story.append(Paragraph(abstract, styles["BodyText"]))

    story.append(
        Paragraph(
            "Keywords: Kubernetes autoscaling, RabbitMQ, HorizontalPodAutoscaler, "
            "KEDA, reproducibility",
            styles["SmallBody"],
        )
    )
    story.append(PageBreak())

    story.append(Paragraph("1. Introduction And Background", styles["Heading1"]))
    story.append(
        Paragraph(
            "The repository compares two autoscaling strategies for the same "
            "message-processing workload: a baseline HorizontalPodAutoscaler "
            "that follows CPU pressure and a KEDA deployment that follows "
            "RabbitMQ backlog. The original project hypothesis expected queue-"
            "aware scaling to react earlier because backlog exists before CPU "
            "utilization saturates inside the consumer pods.",
            styles["BodyText"],
        )
    )
    story.append(
        Paragraph(
            "This branch reruns the experiment from scratch rather than "
            "reusing existing outputs. The goal is branch-level reproducibility: "
            "a clean checkout, a fresh cluster, six new trial traces, freshly "
            "rendered figures, and a report that is generated only from the new "
            "CSV files committed on this branch.",
            styles["BodyText"],
        )
    )
    story.append(
        Paragraph(
            "The rerun also acts as a validation pass on portability. Running on "
            "an Apple Silicon macOS host surfaced several issues that were not "
            "obvious from the original AWS-focused runbook, including container "
            "base-image compatibility, BSD timestamp behavior, and the need to "
            "separate the active burst from the post-burst observation window.",
            styles["BodyText"],
        )
    )
    story.append(PageBreak())

    story.append(Paragraph("2. System Design", styles["Heading1"]))
    story.append(
        Paragraph(
            "Both groups share the same core data path: a Python producer sends "
            "messages to RabbitMQ, a Spring Boot consumer processes them, and a "
            "metrics collector samples pod counts plus queue depth into CSV. "
            "The only variable between groups is the autoscaling controller.",
            styles["BodyText"],
        )
    )
    story.append(controller_table())
    story.append(Spacer(1, 0.3 * cm))
    story.append(
        Paragraph(
            "To make the rerun stable on this machine, the branch introduces an "
            "arm64-compatible consumer runtime image, `python3` defaults in the "
            "experiment wrapper, portable timestamp generation in the collector, "
            "request timeouts for management queries, and a dedicated burst "
            "pattern file without a built-in idle tail.",
            styles["BodyText"],
        )
    )
    story.append(PageBreak())

    story.append(Paragraph("3. Experimental Setup", styles["Heading1"]))
    story.append(
        Paragraph(
            "Each trial starts from a clean queue and a single consumer replica. "
            "The producer warms up the broker for 10 seconds at a low rate, then "
            "injects a 10 second burst with a target 1000 msg/s rate. The actual "
            "publish rate is lower because the current producer publishes "
            "synchronously through `pika`, but the pattern remains identical "
            "across both groups.",
            styles["BodyText"],
        )
    )
    story.append(environment_table())
    story.append(Spacer(1, 0.25 * cm))
    story.append(metric_definition_table())
    story.append(PageBreak())

    story.append(Paragraph("4. Results Summary", styles["Heading1"]))
    story.append(
        Paragraph(
            "The comparison table below aggregates the six fresh trials. Lower "
            "reaction latency and drain time are better, while higher throughput "
            "is better. Peak pods reached the configured ceiling in both groups, "
            "so the meaningful differences came from controller timing rather "
            "than maximum scale.",
            styles["BodyText"],
        )
    )
    story.append(comparison_table(stats))
    story.append(Spacer(1, 0.25 * cm))
    findings = [
        f"HPA reacted faster on average: {baseline_reaction:.2f}s versus {keda_reaction:.2f}s.",
        f"HPA drained the queue faster on average: {baseline_drain:.2f}s versus {keda_drain:.2f}s.",
        f"Average throughput also favored HPA in this rerun: {baseline_tput:.2f} msg/s versus {keda_tput:.2f} msg/s.",
        "KEDA remained more variable across runs, suggesting the local queue-metric polling path was less steady than expected.",
        "The fresh rerun therefore does not reproduce the original narrative that KEDA is strictly faster in this workload.",
    ]
    for item in findings:
        story.append(Paragraph(f"- {item}", styles["SmallBody"]))
    story.append(
        Paragraph(
            "This outcome should be interpreted honestly: the branch proves that "
            "the experiment can be rerun end-to-end from scratch, but it also "
            "shows the result is sensitive to environment choice, achieved burst "
            "rate, and instrumentation path. See `docs/ARTIFACT.md` for the "
            "exact reproduction procedure and branch-specific notes.",
            styles["BodyText"],
        )
    )
    story.append(PageBreak())

    add_figure(story, styles, "Figure 1. Pod scaling timeline", "fig1-pod-scaling-timeline.png")
    story.append(PageBreak())
    add_figure(story, styles, "Figure 2. Queue depth timeline", "fig2-queue-depth-timeline.png")
    story.append(PageBreak())
    add_figure(story, styles, "Figure 3. Reaction latency comparison", "fig3-reaction-latency-bar.png")
    story.append(PageBreak())
    add_figure(story, styles, "Figure 4. Throughput comparison", "fig4-throughput-comparison.png")

    return story


def main():
    rows = load_rows()
    stats = grouped_stats(rows)

    doc = SimpleDocTemplate(
        str(OUTPUT_PDF),
        pagesize=A4,
        rightMargin=1.5 * cm,
        leftMargin=1.5 * cm,
        topMargin=1.4 * cm,
        bottomMargin=1.4 * cm,
        title="Fresh Local Rerun Report",
        author="CS5296 Group 5",
    )
    story = build_story(rows, stats)
    doc.build(story, onFirstPage=page_number, onLaterPages=page_number)
    print(f"wrote {OUTPUT_PDF}")


if __name__ == "__main__":
    main()
