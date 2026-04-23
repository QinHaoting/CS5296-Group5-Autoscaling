# Artifact Appendix

This appendix documents the fresh rerun artifacts produced on branch
`rerun-20260423-fresh-artifacts`. Unlike the original project plan, this rerun
was executed on a local Rancher Desktop Kubernetes cluster because the current
workspace did not have the AWS CLI / kubeconfig / DockerHub workflow prepared
for a same-turn EC2 replay.

## A.1 Abstract

The artifact contains a Spring Boot RabbitMQ consumer, Kubernetes manifests for
two scaling strategies (CPU-based HPA and queue-length-based KEDA), a Python
producer that injects a reproducible burst workload, a shell metrics collector,
fresh raw CSV traces for six trials, and four generated comparison figures. The
fresh rerun also includes compatibility fixes required for this machine:
portable timestamp collection on macOS, `python3`-aware experiment scripts, an
arm64-compatible consumer base image, and a producer pattern that separates the
publish burst from the post-burst observation window.

## A.2 Artifact Check-list

| Item | Value |
|---|---|
| Topic | HPA vs KEDA autoscaling for a RabbitMQ-backed consumer |
| Branch | `rerun-20260423-fresh-artifacts` |
| Source repo | `https://github.com/QinHaoting/CS5296-Group5-Autoscaling` |
| Runtime environment | macOS 26.2 host + Rancher Desktop 1.22 + K3s v1.34.5 |
| VM size | 4 vCPU / 8 GiB RAM |
| Broker | RabbitMQ 3.12 management image |
| Consumer image | `cs5296-consumer:rerun-20260423-local` |
| Producer pattern | `load-test/patterns/burst-active.yaml` |
| Observation window | 180 s per trial |
| Experiment count | 6 trials (3 baseline + 3 KEDA) |
| Raw outputs | `results/raw/*.csv` and `results/raw/*-sendlog.csv` |
| Summary output | `results/summary.csv` |
| Figures | `results/figures/fig1-fig4*.png` |
| Report | `report/main.pdf` |

## A.3 How To Access

The rerun branch is published here:

`https://github.com/QinHaoting/CS5296-Group5-Autoscaling/tree/rerun-20260423-fresh-artifacts`

Fresh rerun data is stored directly in this branch under `results/`.

## A.4 Hardware And Software Dependencies

Hardware used for this rerun:

- Apple Silicon host
- 10 logical CPU cores on the host
- 16 GiB host memory
- Rancher Desktop VM configured to 4 CPU / 8 GiB

Software used for this rerun:

- Rancher Desktop 1.22 with Kubernetes enabled
- Docker 29.x
- Helm 4.0.5
- `kubectl` 1.35.2
- Python 3.14 for load generation
- ReportLab-based PDF generation for the fresh report

## A.5 Installation And Deployment

Start from the rerun branch checkout:

```bash
git clone git@github.com:QinHaoting/CS5296-Group5-Autoscaling.git
cd CS5296-Group5-Autoscaling
git checkout rerun-20260423-fresh-artifacts
```

Enable a local Kubernetes runtime. For this rerun we used Rancher Desktop with:

- Kubernetes enabled
- 4 CPU
- 8 GiB memory

Then deploy shared infrastructure and the two groups:

```bash
export PATH="$HOME/.rd/bin:$PATH"
helm install keda kedacore/keda --namespace keda --create-namespace --wait
kubectl apply -f k8s/infra/
kubectl -n rabbitmq rollout status statefulset/rabbitmq --timeout=240s

export CONSUMER_IMAGE='cs5296-consumer:rerun-20260423-local'
./scripts/deploy-baseline.sh
./scripts/deploy-keda.sh
```

## A.6 Experiment Workflow

Install Python dependencies:

```bash
python3 -m venv load-test/.venv
load-test/.venv/bin/pip install -r load-test/requirements.txt

python3 -m venv analysis/.venv
analysis/.venv/bin/pip install -r analysis/requirements.txt
```

Run the six fresh trials:

```bash
export PATH="$HOME/.rd/bin:$PATH"
export PYTHON_BIN="$PWD/load-test/.venv/bin/python"

./scripts/run-experiment.sh baseline 1
./scripts/run-experiment.sh keda 1
./scripts/run-experiment.sh baseline 2
./scripts/run-experiment.sh keda 2
./scripts/run-experiment.sh baseline 3
./scripts/run-experiment.sh keda 3
```

Generate the figures and summary:

```bash
analysis/.venv/bin/python analysis/plot.py
```

Generate the fresh PDF report:

```bash
/Users/zhangweiyi/.cache/codex-runtimes/codex-primary-runtime/dependencies/python/bin/python3 \
  report/generate_report.py
```

## A.7 Expected Outputs

Raw files:

- `results/raw/baseline-run1.csv`
- `results/raw/baseline-run2.csv`
- `results/raw/baseline-run3.csv`
- `results/raw/keda-run1.csv`
- `results/raw/keda-run2.csv`
- `results/raw/keda-run3.csv`

Derived outputs:

- `results/summary.csv`
- `results/figures/fig1-pod-scaling-timeline.png`
- `results/figures/fig2-queue-depth-timeline.png`
- `results/figures/fig3-reaction-latency-bar.png`
- `results/figures/fig4-throughput-comparison.png`
- `report/main.pdf`

## A.8 Notes On This Fresh Rerun

- This rerun is intentionally isolated from the user's existing uncommitted
  artifacts; it lives in a new Git branch and clean worktree.
- The local rerun produced a different conclusion from the original project
  hypothesis: in this environment the HPA baseline reacted faster on average
  than KEDA.
- The producer achieved roughly 5.9k to 7.0k messages per burst instead of an
  ideal 10k, because `pika` publishing remained synchronous on this machine.
- Fresh code changes on this branch make the experiment portable to macOS and
  arm64 systems.
