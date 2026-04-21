# Smoke Test Artefacts (2026-04-20)

End-to-end sanity check that the full pipeline (Producer → RabbitMQ NodePort →
Consumer → HPA / KEDA) works before running the formal experiment in `raw/`.

## Configuration

- **Cluster**: single-node K3s on AWS EC2 `m5.large` (2 vCPU / 8 GB, `us-west-2`)
- **RabbitMQ**: `rabbitmq:3.12-management`, 1000m / 1Gi limits, tcpSocket probes
- **Consumer image**: `htasteqin/cs5296-consumer:v1.0` (Spring Boot 3.2.5 + Spring AMQP)
- **Pattern**: see [`smoke-pattern.yaml`](smoke-pattern.yaml) — **3s warm-up @ 5 msg/s + 25s burst @ 20 msg/s + 30s drain = 58s total**, 485 messages of 256 B each
- **Producer location**: local macOS venv → AMQP over public NodePort `$EC2_IP:30567`

## Files

| File | Description |
|---|---|
| `smoke-pattern.yaml` | Load pattern used for this smoke run |
| `baseline-sendlog.csv` | 485 rows, columns `seq,phase_idx,send_ts_ms` (baseline-queue) |
| `keda-sendlog.csv` | 485 rows, same columns (keda-queue) |
| `baseline-producer.log` | `pika` client log: connect → 3 phases → close |
| `keda-producer.log` | same, but publishing to `keda-queue` |
| `observations.md` | Side-by-side scaling timeline tables and take-aways |

## How this relates to the formal experiment

The smoke run exercises the **same** producer script, queues and RabbitMQ
NodePort. The formal experiment differs only in:

- Load pattern: `load-test/patterns/burst.yaml` (10 s × 1000 msg/s = ~10 000
  messages instead of 485)
- Repetitions: 3 runs per scenario × 2 scenarios = 6 trials
- Producer location: EC2 `tmux` (using `localhost:30567`) instead of laptop
- Collector: `scripts/collect-metrics.sh` samples every 1 s into
  `results/raw/<scenario>-run<N>.csv`

The behaviour observed during smoke (HPA bursting to `maxReplicas`, KEDA sizing
replicas from queue depth) should therefore match — only amplified. The formal
CSVs in `results/raw/` are the scientific artefacts; the files in this folder
are kept purely as a reference snapshot of a *known-good* pipeline state.
