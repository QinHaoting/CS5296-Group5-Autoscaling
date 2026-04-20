# CS5296-Group5-Autoscaling

[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](LICENSE)
[![Status](https://img.shields.io/badge/status-in--development-orange)](https://github.com)

> Comparative analysis of a Kubernetes **Baseline (HPA)** vs **KEDA**
> autoscaling strategy for a RabbitMQ-backed microservice.

## Scope

A single experiment, two scaling strategies, one burst workload:

| Group | Scaling trigger | Controlled by |
|---|---|---|
| **Baseline** | CPU utilisation (50%) | Kubernetes HPA |
| **KEDA** | RabbitMQ queue length (100) | KEDA ScaledObject |

Everything else — the consumer image, resource limits, broker, load pattern, hardware — is held constant. We measure four metrics:

1. **Reaction latency** — how fast the first new pod becomes Ready after the burst hits
2. **Queue drain time** — how long before the backlog reaches zero
3. **Average throughput** — messages delivered per second during the drain
4. **Peak replica count** — cost signal

## Repository Layout

```
CS5296-Group5-Autoscaling/
├── consumer/           Java Spring Boot SUT (System Under Test)
├── load-test/          Python burst producer + patterns
├── k8s/
│   ├── infra/          Shared infra: namespaces + RabbitMQ
│   ├── baseline/       Baseline group: Deployment + Service + HPA
│   └── keda/           KEDA group: Deployment + Service + ScaledObject
├── scripts/            Setup / deploy / experiment / teardown (bash)
├── analysis/           pandas + matplotlib, produces 4 figures
├── results/
│   ├── raw/            Per-trial CSVs from the metrics collector
│   └── figures/        Generated plots referenced by the report
├── docs/               Artifact appendix, commit plan, demo link
└── report/             9-page LaTeX final report (IEEE style)
```

Only two things are compared. That's why every K8s sub-directory, every script argument, and every CSV file follows the **same `baseline` / `keda` dichotomy** — no other scenario enters the data pipeline.

## Prerequisites

- AWS EC2 `t3.medium` (or larger), Ubuntu 22.04
- Docker 24.x on your dev machine
- A public Docker registry (DockerHub or ECR) for the consumer image
- `kubectl`, `helm`, `curl`, `jq` on the cluster host
- Python 3.10+ for load testing and analysis
- Java 17 + Maven 3.9+ if you rebuild the consumer locally

## Quick Start

### 1. Clone and configure

```bash
git clone https://github.com/<your-org>/CS5296-Group5-Autoscaling.git
cd CS5296-Group5-Autoscaling

cp .env.example .env
# Edit .env with your DockerHub username, EC2 IP, etc.
```

### 2. Build and push the consumer image

```bash
cd consumer
docker build -t <your-dockerhub>/cs5296-consumer:v1.0 .
docker push <your-dockerhub>/cs5296-consumer:v1.0
cd ..
```

Then update the image reference in `k8s/baseline/deployment.yaml` and `k8s/keda/deployment.yaml` (or export `CONSUMER_IMAGE` and let the deploy scripts substitute it).

### 3. Provision the cluster

SSH to your EC2 host, then:

```bash
./scripts/setup.sh
```

Installs K3s, metrics-server, KEDA (via Helm), and the shared RabbitMQ.

### 4. Deploy both experiment groups

```bash
export CONSUMER_IMAGE=<your-dockerhub>/cs5296-consumer:v1.0
./scripts/deploy-baseline.sh
./scripts/deploy-keda.sh
```

### 5. Run experiments

```bash
./scripts/run-experiment.sh baseline 1   # Baseline trial 1
./scripts/run-experiment.sh keda     1   # KEDA trial 1
./scripts/run-experiment.sh baseline 2   # Repeat for statistical strength
./scripts/run-experiment.sh keda     2
```

Raw data lands in `results/raw/*.csv`.

### 6. Plot results

```bash
cd analysis
pip install -r requirements.txt
python plot.py
```

Four PNGs and a `results/summary.csv` appear under `results/`.

### 7. Teardown

```bash
./scripts/teardown.sh
# Then terminate your EC2 instance via the AWS Console
```

## Key Configuration

Runtime settings live in `.env`; the important ones:

- `CONSUMER_IMAGE` — full image reference pushed in step 2
- `EC2_PUBLIC_IP` — used by the external Python producer
- `HPA_CPU_TARGET` — baseline threshold (default 50%)
- `KEDA_QUEUE_LENGTH` — KEDA threshold (default 100 messages)
- `MIN_REPLICAS` / `MAX_REPLICAS` — scaling bounds (default 1 / 10)

## Reproducibility

Step-by-step reproduction instructions live in [`docs/ARTIFACT.md`](docs/ARTIFACT.md).

## Deliverables

| Deliverable | Location |
|---|---|
| Final report (PDF) | `report/main.pdf` |
| Artifact appendix | Embedded as the appendix of `main.pdf` |
| Demo video | See [`docs/DEMO.md`](docs/DEMO.md) |

## License

MIT — see [`LICENSE`](LICENSE).

## Acknowledgments

Reference implementations that inspired this work:

- [Keda-Spring](https://github.com/lucasnscr/Keda-Spring) by lucasnscr
- [spring-boot-k8s-hpa](https://github.com/learnk8s/spring-boot-k8s-hpa) by learnk8s
