# Consumer Application

A minimal Spring Boot service that reads messages from a RabbitMQ queue and
burns ~200 ms of CPU per message. The CPU-bound work is intentional — the
baseline HPA needs a CPU signal to react to, so a plain `Thread.sleep`
would be unfair to the baseline.

## Environment variables

| Variable | Default | Meaning |
|---|---|---|
| `RABBITMQ_HOST` | `rabbitmq.rabbitmq.svc.cluster.local` | RabbitMQ host |
| `RABBITMQ_PORT` | `5672` | AMQP port |
| `RABBITMQ_USER` | `admin` | AMQP username |
| `RABBITMQ_PASS` | `cs5296-demo` | AMQP password |
| `CONSUMER_QUEUE` | `baseline-queue` | Queue to consume |
| `CONSUMER_PROCESS_MS` | `200` | CPU-bound work per message (ms) |

Both experiment groups use the **same Docker image**; only the environment
variables differ, ensuring a controlled comparison.

## Build

```bash
mvn clean package
```

## Run locally

```bash
RABBITMQ_HOST=localhost \
RABBITMQ_USER=guest RABBITMQ_PASS=guest \
CONSUMER_QUEUE=demo \
java -jar target/consumer.jar
```

## Build and push Docker image

```bash
export DOCKERHUB_USER=<your-dockerhub>
docker build -t ${DOCKERHUB_USER}/cs5296-consumer:v1.0 .
docker push ${DOCKERHUB_USER}/cs5296-consumer:v1.0
```

## Endpoints

- `GET /actuator/health` — used by K8s liveness/readiness probes
- `GET /actuator/prometheus` — Prometheus-format metrics
- `GET /actuator/metrics/consumer.messages.processed` — Spring metric
