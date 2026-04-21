# Smoke Observations — Baseline (HPA/CPU) vs KEDA (QueueLength)

Single run of each scenario using the pattern in `smoke-pattern.yaml` (485
messages over 58 s, then 30 s drain). Polling interval for the snapshots below
was 10 s from a laptop running `kubectl` + RabbitMQ mgmt API calls.

## Baseline — HPA CPU target `50%`, `minReplicas=1`, `maxReplicas=6`

| t (s) | HPA CPU | Replicas | Pods Ready | queue msgs | consumers |
|---|---|---|---|---|---|
| 10 | 5 %  | 1   | 1/1                | 0   | 1 |
| 20 | 3 %  | 1   | 1/1                | 96  | 1 |
| **30** | **114 %** | 1→ | 1/1 + 2 booting | 305 | 1 |
| 40 | 300 % | **3** | 1/1 + 5 booting  | 314 | 1 |
| 50 | 300 % | **6** | 1/1 + 5 booting  | 240 | 1 |
| 60 | 294 % | 6   | 3/6 ready         | 144 | 3 |
| **70** | 300 % | 6 | **6/6 ready**    | **0** | 3 |
| 80 | 280 % | 6   | 6/6 ready         | 0   | 6 |

- **First scale-up decision**: ~t=30 s (metrics-server → HPA evaluation lag)
- **Peak replicas**: 6 (saturates `maxReplicas`)
- **Queue drained**: ~t=70 s
- **Final consumer count**: 6 (all pods eventually bind a consumer)

## KEDA — QueueLength trigger `value=100`, `pollingInterval=5s`, same min/max

| t (s) | Queue metric (avg/pod) | Desired | Pods Ready | queue msgs | consumers |
|---|---|---|---|---|---|
| 10 | 0/100     | 1  | 1/1                | 0   | 1 |
| **20** | **131/100** | 1→ | 1/1 + 1 booting | 125 | 1 |
| 30 | 131/100   | 1→ | 1/1 + 3 booting    | 334 | 1 |
| 40 | 169/100   | **2** | 1/1 + 3 booting | 303 | 1 |
| 50 | 69/100    | **4** | 1/1 + 3 booting | 229 | 1 |
| 60 | 49.5/100  | 4  | 2/4 ready          | 103 | 2 |
| **70** | 11.25/100 | 4 | **4/4 ready**   | **0** | 4 |
| 80 | 0/100     | 4 (cooling) | 3/4       | 0   | 3 |

- **First scale-up decision**: ~t=20 s (KEDA polls RabbitMQ mgmt API every 5 s)
- **Peak replicas**: 4 (KEDA sizes from `avg queue msgs per pod ≤ 100`)
- **Queue drained**: ~t=70 s
- **Scale-down starts**: ~t=80 s (1-pod-at-a-time decrement driven by `cooldownPeriod=60s`)

## Side-by-side summary

| metric | Baseline | KEDA | why |
|---|---|---|---|
| First decision to scale up | ~30 s | **~20 s** | QueueLength is a direct signal; CPU signal goes through metrics-server aggregation |
| Peak replicas used | **6** | **4** | HPA over-shoots to `maxReplicas`; KEDA sizes from queue-per-pod target |
| Queue drain time | ~70 s | ~70 s | Both are bottlenecked on Spring Boot pod cold-start (~30 s) and message throughput, not autoscaler latency |
| Scale-down start | ≥60 s after drain | ~10 s after drain | `cooldownPeriod=60s` kicks in once queue has been below threshold for one polling window |

**Headline take-away**: Under the same overload, KEDA uses ~33 % fewer pods to
finish at the same time, and reclaims resources faster. The formal burst run
(10 s × 1000 msg/s) should amplify this gap because the queue grows further
while Spring Boot pods are still booting, giving the direct queue metric more
headroom over the CPU metric.
