# Load Test Module

Produces bursty AMQP traffic to stress the Baseline and KEDA consumers.

## Install

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

## Running against a remote cluster

Expose RabbitMQ first (from the EC2 host):

```bash
kubectl -n rabbitmq port-forward svc/rabbitmq 5672:5672
```

Then from your laptop:

```bash
python producer.py \
    --rabbitmq amqp://admin:cs5296-demo@localhost:5672 \
    --queue baseline-queue \
    --pattern patterns/burst.yaml \
    --output ../results/raw/baseline-run1-sendlog.csv
```

## Patterns

| File | Description |
|---|---|
| `patterns/burst.yaml` | 10k msgs in 10s, then silence (default for main experiments) |
| `patterns/steady.yaml` | 200 msg/s for 2 minutes (sanity check) |

Each pattern is a list of phases with `duration_sec`, `rate_per_sec`, and an
optional `payload_bytes`.
