# OpenShift Kafka Day Roadshow

Hands-on workshop: NeuralBank needs customer emails and schema checks for PostgreSQL changes, without editing the banking app. Event-Driven Architecture with Apache Kafka, Debezium CDC, and observability on Red Hat OpenShift.

Deployed as a **Validated Pattern** (hub-only, single cluster). Duration: **2 hours**.

## Workshop Modules

| Module | Title | Duration |
|--------|-------|----------|
| 01 | Lab Setup & Overview | 10 min |
| 02 | Kafka Fundamentals | 20 min |
| 03 | Event Producer: Real Application | 15 min |
| 04 | Event Consumer: Processing Pipeline | 15 min |
| 05 | Debezium CDC | 20 min |
| 06 | Camel and Apicurio Registry | 20 min |
| 07 | Monitoring | 15 min |
| 08 | Wrap-up | 5 min |

## Components

- **AMQ Streams (Strimzi)** -- Apache Kafka 4.2 with KRaft
- **PostgreSQL 16** -- Source database with WAL logical replication
- **Debezium** -- CDC connector for PostgreSQL
- **Kafka Connect** -- Debezium source + HTTP Sink connectors
- **CDC Data Simulator** -- Python transaction generator
- **Mailpit** -- Email notification viewer
- **Kafka Console** -- Web UI for topics/messages
- **Grafana** -- Kafka metrics dashboards
- **Apicurio Registry** -- JSON Schema registry stored in Kafka
- **Camel** -- Validates CDC rows and lab messages against Apicurio

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

Participants enter their email on the registration page, get assigned `userN`, and are redirected to the lab guide with Terminal, OCP Console, Kafka Console, Mailpit, Grafana, and Registry tabs.

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
