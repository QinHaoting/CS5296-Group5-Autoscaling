"""Burst traffic producer for the CS5296 HPA vs KEDA experiment.

This script publishes N messages to a RabbitMQ queue at a configurable rate
and records the exact send timestamp of each message so downstream analysis
can compute end-to-end latency.

Typical usage from a laptop (RabbitMQ exposed via NodePort / LoadBalancer):

    python producer.py \
        --rabbitmq amqp://admin:cs5296-demo@<EC2_IP>:30567 \
        --queue baseline-queue \
        --pattern patterns/burst.yaml \
        --output ../results/raw/hpa-run1-sendlog.csv

The pattern YAML describes a list of "phases" (see patterns/burst.yaml). Each
phase has a target duration and rate; the producer honours both by sleeping
between publishes.
"""
from __future__ import annotations

import csv
import json
import logging
import os
import sys
import time
from dataclasses import dataclass
from pathlib import Path

import click
import pika
from pika.exceptions import AMQPError, StreamLostError
import yaml

log = logging.getLogger("producer")


@dataclass
class Phase:
    duration_sec: float
    rate_per_sec: float
    payload_bytes: int = 256


def load_pattern(path: Path) -> list[Phase]:
    with path.open("r", encoding="utf-8") as f:
        cfg = yaml.safe_load(f)
    phases: list[Phase] = []
    for raw in cfg["phases"]:
        phases.append(
            Phase(
                duration_sec=float(raw["duration_sec"]),
                rate_per_sec=float(raw["rate_per_sec"]),
                payload_bytes=int(raw.get("payload_bytes", 256)),
            )
        )
    return phases


def build_payload(size_bytes: int, seq: int) -> bytes:
    """Build a JSON payload padded to the requested byte size."""
    meta = {"seq": seq, "ts_ms": int(time.time() * 1000)}
    body = json.dumps(meta)
    pad = max(size_bytes - len(body), 0)
    return (body + ("x" * pad)).encode("utf-8")


def run(
    amqp_url: str,
    queue: str,
    phases: list[Phase],
    csv_path: Path | None,
) -> None:
    log.info("connecting to %s", amqp_url)
    params = pika.URLParameters(amqp_url)
    connection = pika.BlockingConnection(params)
    try:
        channel = connection.channel()
        channel.queue_declare(queue=queue, durable=True)

        out_file = None
        writer = None
        if csv_path is not None:
            csv_path.parent.mkdir(parents=True, exist_ok=True)
            out_file = csv_path.open("w", newline="", encoding="utf-8")
            writer = csv.writer(out_file)
            writer.writerow(["seq", "phase_idx", "send_ts_ms"])

        seq = 0
        overall_start = time.time()
        for idx, phase in enumerate(phases):
            log.info(
                "phase %d: rate=%.1f/s for %.1fs (payload=%dB)",
                idx,
                phase.rate_per_sec,
                phase.duration_sec,
                phase.payload_bytes,
            )
            if phase.rate_per_sec <= 0:
                time.sleep(phase.duration_sec)
                continue
            interval = 1.0 / phase.rate_per_sec
            phase_end = time.time() + phase.duration_sec
            while time.time() < phase_end:
                send_ts_ms = int(time.time() * 1000)
                channel.basic_publish(
                    exchange="",
                    routing_key=queue,
                    body=build_payload(phase.payload_bytes, seq),
                )
                if writer is not None:
                    writer.writerow([seq, idx, send_ts_ms])
                seq += 1
                time.sleep(interval)
        total_elapsed = time.time() - overall_start
        log.info(
            "sent %d messages in %.1fs (avg %.1f msg/s)",
            seq,
            total_elapsed,
            seq / total_elapsed if total_elapsed > 0 else 0,
        )

        if out_file is not None:
            out_file.close()
    finally:
        if connection.is_open:
            try:
                connection.close()
            except (AMQPError, StreamLostError):
                log.warning("connection already closed by broker during shutdown", exc_info=True)


@click.command(context_settings={"show_default": True})
@click.option(
    "--rabbitmq",
    envvar="RABBITMQ_URL",
    default="amqp://admin:cs5296-demo@localhost:5672",
    help="AMQP URL, e.g. amqp://user:pass@host:port",
)
@click.option(
    "--queue",
    required=True,
    help="Target queue name, e.g. baseline-queue or keda-queue",
)
@click.option(
    "--pattern",
    required=True,
    type=click.Path(exists=True, path_type=Path),
    help="Path to a pattern YAML (see patterns/burst.yaml)",
)
@click.option(
    "--output",
    type=click.Path(path_type=Path),
    default=None,
    help="CSV file to record send timestamps (optional)",
)
@click.option("-v", "--verbose", is_flag=True, help="Enable debug logging")
def main(rabbitmq: str, queue: str, pattern: Path, output: Path | None, verbose: bool) -> None:
    """Publish a burst of messages to the given RabbitMQ queue."""
    logging.basicConfig(
        level=logging.DEBUG if verbose else logging.INFO,
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
    )
    phases = load_pattern(pattern)
    run(rabbitmq, queue, phases, output)


if __name__ == "__main__":
    main()
