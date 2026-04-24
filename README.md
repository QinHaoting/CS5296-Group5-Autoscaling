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
├── analysis/           pandas + matplotlib, produces report figures
├── results/
│   ├── raw/            Per-trial CSVs from the metrics collector
│   └── figures/        Generated plots referenced by the report
├── docs/               Artifact appendix, commit plan, demo link
└── report/             9-page LaTeX final report (IEEE style)
```

Only two things are compared. That's why every K8s sub-directory, every script argument, and every CSV file follows the **same `baseline` / `keda` dichotomy** — no other scenario enters the data pipeline.

## Prerequisites

- AWS EC2 `m5.large` (2 vCPU / 8 GiB), Ubuntu Server 22.04 LTS amd64, 40 GiB gp3
- Security group inbound ports: `22`, `6443`, `15672`, and `30000-32767`
- Docker 24.x on your dev machine
- A public Docker registry (DockerHub or ECR) for the consumer image
- `kubectl`, `helm`, `curl`, `jq` on the cluster host
- Python 3.10+ for load testing and analysis
- Java 17 + Maven 3.9+ if you rebuild the consumer locally

## Reproduce the Master-Branch Experiment

These steps reproduce the experiment configuration on `master`: one EC2 host, one
RabbitMQ broker, one Baseline HPA deployment, one KEDA deployment, and three
trials for each scaling strategy.

### 1. Checkout and shell variables

```bash
git clone https://github.com/<your-org>/CS5296-Group5-Autoscaling.git
cd CS5296-Group5-Autoscaling
git checkout master

cp .env.example .env
# Edit .env for your notes, then export the values used by the scripts:
export CS5296_REPO="$PWD"
export DOCKERHUB_USER="<your-dockerhub-user>"
export CONSUMER_IMAGE="${DOCKERHUB_USER}/cs5296-consumer:v1.0"
export EC2_IP="<your-ec2-public-ip>"
```

### 2. Prepare the EC2 host

Launch an EC2 instance with:

| Item | Value |
|---|---|
| Region | `us-west-2` for a regular AWS account, or the Vocareum default region for AWS Academy |
| AMI | Ubuntu Server 22.04 LTS amd64 |
| Instance type | `m5.large` |
| Storage | 40 GiB gp3 |
| Security group | inbound `22`, `6443`, `15672`, `30000-32767` from `0.0.0.0/0` |

Then SSH to the host and run the cluster bootstrap:

```bash
ssh -i ~/cs5296-key.pem ubuntu@$EC2_IP
sudo apt-get update
sudo apt-get install -y git curl jq python3-venv tmux

git clone https://github.com/<your-org>/CS5296-Group5-Autoscaling.git ~/CS5296-Group5-Autoscaling
export CS5296_REPO="$HOME/CS5296-Group5-Autoscaling"
cd "$CS5296_REPO"
bash scripts/setup.sh
```

`scripts/setup.sh` installs K3s, Helm, metrics-server, KEDA, namespaces, and
the shared RabbitMQ StatefulSet.

### 3. Build and push the consumer image

Run this on the machine that has Docker and Maven. The explicit platform is
required when building from Apple Silicon because the EC2 node is `linux/amd64`.

```bash
cd "$CS5296_REPO/consumer"
mvn -DskipTests clean package

docker buildx build \
  --platform linux/amd64 \
  -t "${CONSUMER_IMAGE}" \
  --push \
  .
```

The `master` manifests currently pin an image under
`k8s/baseline/deployment.yaml` and `k8s/keda/deployment.yaml`. If you want to use
your rebuilt image, run this in the checkout that will execute the deploy
scripts:

```bash
cd "$CS5296_REPO"
sed -i.bak "s|image: .*cs5296-consumer.*|image: ${CONSUMER_IMAGE}|" \
  k8s/baseline/deployment.yaml \
  k8s/keda/deployment.yaml
rm k8s/baseline/deployment.yaml.bak k8s/keda/deployment.yaml.bak
```

### 4. Deploy both experiment groups

```bash
export CS5296_REPO="$HOME/CS5296-Group5-Autoscaling"
export CONSUMER_IMAGE="<your-dockerhub-user>/cs5296-consumer:v1.0"
cd "$CS5296_REPO"

bash scripts/deploy-baseline.sh
bash scripts/deploy-keda.sh

kubectl get pods -n baseline
kubectl get hpa -n baseline
kubectl get pods -n keda
kubectl get scaledobject -n keda
```

`scripts/deploy-baseline.sh` applies the Baseline deployment, service, secret,
and HPA. `scripts/deploy-keda.sh` applies the KEDA deployment, service, secret,
TriggerAuthentication, and ScaledObject. Both scripts wait for the consumer
deployment to become ready.

### 5. Master experiment parameters

Authoritative values live in the Kubernetes manifests, `load-test/patterns/`,
and `scripts/run-experiment.sh`.

| Area | Master value |
|---|---|
| Consumer resources | request `100m` CPU / `256Mi`, limit `300m` CPU / `512Mi` |
| Consumer work | `CONSUMER_PROCESS_MS=200` per message |
| Baseline scaler | HPA CPU average utilization `50%`, `minReplicas=1`, `maxReplicas=6` |
| KEDA scaler | RabbitMQ `QueueLength`, `value=100`, `pollingInterval=5s`, `cooldownPeriod=60s`, `minReplicaCount=1`, `maxReplicaCount=6` |
| RabbitMQ queues | `baseline-queue`, `keda-queue` |
| RabbitMQ NodePorts | AMQP `30567`, Management UI/API `31672` |
| Producer pattern | `load-test/patterns/burst.yaml` |
| Burst pattern | 10s warm-up at 5 msg/s, 10s burst at 1000 msg/s, 180s silence, 256 B payload |
| `run-experiment.sh` default observation | `OBS_DURATION=180` after the producer exits |
| Trial count | 3 Baseline + 3 KEDA |
| Trial order | `baseline-1`, `keda-1`, `baseline-2`, `keda-2`, `baseline-3`, `keda-3` |
| Cooldown between trials | 120s |

`scripts/run-experiment.sh` performs the per-trial reset automatically: scale
the target deployment back to one replica, purge the queue, start
`scripts/collect-metrics.sh`, wait 10s, run the producer, keep observing for
`OBS_DURATION`, then stop the collector. A full master trial is about 390s
because the burst pattern already contains 180s of silence and the script adds
another 180s post-producer observation window.

### 6. Run the six official trials

Run the full loop inside `tmux` on the EC2 host so SSH disconnects do not lose
the run.

```bash
ssh -i ~/cs5296-key.pem ubuntu@$EC2_IP
tmux new -s experiment

export CS5296_REPO="$HOME/CS5296-Group5-Autoscaling"
cd "$CS5296_REPO"
export KUBECONFIG=~/.kube/config
export RABBITMQ_URL="amqp://admin:cs5296-demo@localhost:30567"
export RMQ_MGMT_URL="http://localhost:31672"
export PATTERN="$PWD/load-test/patterns/burst.yaml"
export OBS_DURATION=180

python3 -m venv load-test/.venv
source load-test/.venv/bin/activate
pip install -r load-test/requirements.txt

for trial in 1 2 3; do
  echo "===== trial $trial ===== $(date +%T)"
  bash scripts/run-experiment.sh baseline "$trial"
  echo "--- cooldown 120s ---"
  sleep 120
  bash scripts/run-experiment.sh keda "$trial"
  echo "--- cooldown 120s ---"
  sleep 120
done

ls -lh results/raw/
```

Expected raw data:

- `results/raw/baseline-run{1,2,3}.csv`
- `results/raw/baseline-run{1,2,3}-sendlog.csv`
- `results/raw/keda-run{1,2,3}.csv`
- `results/raw/keda-run{1,2,3}-sendlog.csv`

### 7. Plot results

Run this in the checkout that contains the completed `results/raw/` files. If
the trials ran on EC2 and you want to plot locally, copy the results back first:

```bash
rsync -avz -e "ssh -i ~/cs5296-key.pem" \
  ubuntu@$EC2_IP:~/CS5296-Group5-Autoscaling/results/ \
  "$CS5296_REPO/results/"
```

```bash
cd "$CS5296_REPO"
python3 -m venv .venv-analysis
source .venv-analysis/bin/activate
pip install -r analysis/requirements.txt
python analysis/plot.py --results results
```

The analysis writes `results/summary.csv` plus report figures under
`results/figures/`.

### 8. Teardown

```bash
cd "$CS5296_REPO"
bash scripts/teardown.sh
# Then terminate your EC2 instance via the AWS Console
```

## Script Reference

| Script | Use |
|---|---|
| `scripts/setup.sh` | Bootstrap K3s, Helm, metrics-server, KEDA, namespaces, and RabbitMQ |
| `scripts/deploy-baseline.sh` | Deploy the CPU-based HPA baseline group |
| `scripts/deploy-keda.sh` | Deploy the RabbitMQ queue-length KEDA group |
| `scripts/run-experiment.sh <baseline|keda> <run>` | Run one clean trial and write metrics/sendlog CSVs |
| `scripts/collect-metrics.sh <namespace> <queue> <output.csv>` | Low-level 1 Hz collector used by `run-experiment.sh` |
| `scripts/teardown.sh` | Remove experiment namespaces, RabbitMQ, and KEDA; EC2 termination is manual |

## Reproducibility

Use [Reproduce the Master-Branch Experiment](#reproduce-the-master-branch-experiment)
as the self-contained reproduction path. The detailed internal command runbook
used during development is `plan/10-执行手册.md` in the course workspace, if that
workspace is available.

## Deliverables

| Deliverable | Location |
|---|---|
| Final report (PDF) | `report/main.pdf` |
| Artifact appendix | Embedded as the appendix of `main.pdf` |
| Demo video | [Bilibili recording](https://www.bilibili.com/video/BV1WsojB8EsA/?spm_id_from=333.1387.upload.video_card.click&vd_source=00447e7dd04403f16b636c8ef7d5db9f) |

## License

MIT — see [`LICENSE`](LICENSE).

## Acknowledgments

Reference implementations that inspired this work:

- [Keda-Spring](https://github.com/lucasnscr/Keda-Spring) by lucasnscr
- [spring-boot-k8s-hpa](https://github.com/learnk8s/spring-boot-k8s-hpa) by learnk8s
