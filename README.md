# OpenShift Kafka Day Roadshow

Hands-on workshop covering **Event-Driven Architecture** with Apache Kafka, Debezium Change Data Capture (CDC), and real-time observability on Red Hat OpenShift.

Deployed as a **Validated Pattern** (hub-only, single cluster).

## Workshop Modules

| Module | Title | Duration |
|--------|-------|----------|
| Setup | Lab Setup & Overview | 15 min |
| 01 | Kafka Fundamentals | 20 min |
| 02 | Event Producer: Real Application | 20 min |
| 03 | Event Consumer: Processing Pipeline | 15 min |
| 04 | Debezium CDC | 25 min |
| 05 | Monitoring & Traceability | 20 min |
| 06 | Wrap-up | 10 min |

## Components

- **AMQ Streams (Strimzi)** -- Kafka 3.x cluster with KRaft
- **PostgreSQL 16** -- Source database with WAL logical replication
- **Debezium** -- CDC connector for PostgreSQL
- **Kafka Connect** -- Debezium source + HTTP Sink connectors
- **CDC Data Simulator** -- Python transaction generator
- **Mailpit** -- Email notification viewer
- **Kafka Streams Console** -- Web UI for topics/messages
- **Grafana** -- Kafka metrics dashboards
- **OpenTelemetry** -- Distributed tracing collector

## Quick Start

### Prerequisites

- OpenShift 4.17+ with the **Validated Patterns Operator** installed
- **Development**: 2x m5a.4xlarge workers (32 vCPU / 128 Gi)
- **Workshop (30 users)**: 4x m5a.4xlarge workers (64 vCPU / 256 Gi)

### Install

```bash
oc apply -f examples/pattern-cr/hub-only.yaml
```

### Access

| Service | URL |
|---------|-----|
| **Workshop Registration** | `https://workshop-registration.apps.<domain>` |
| **Showroom (Lab Guide)** | `https://showroom-showroom.apps.<domain>` |
| **Registration Admin** | `https://workshop-registration.apps.<domain>/admin` (token: `workshop-admin-2024`) |

Participants enter their email on the registration page, get assigned `userN`, and are redirected to the lab guide with Terminal, OCP Console, and Kafka Console tabs.

### Users

30 pre-provisioned HTPasswd users: `user1` through `user30`, password `Welcome123!`

## Cluster Sizing

| Scenario | Workers | Instance Type | Total vCPU | Total RAM |
|----------|---------|---------------|------------|-----------|
| Development | 2 | m5a.4xlarge | 32 | 128 Gi |
| Workshop (30 users) | 4 | m5a.4xlarge | 64 | 256 Gi |

## Maintainer

**Maximiliano Pizarro** -- Specialist Solution Architect -- mapizarr@redhat.com

## License

Apache License 2.0
