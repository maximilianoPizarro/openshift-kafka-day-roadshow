<p align="left">
<img src="https://img.shields.io/badge/OpenShift-EE0000?style=for-the-badge&logo=redhatopenshift&logoColor=white" alt="OpenShift">
<img src="https://img.shields.io/badge/Apache%20Kafka-231F20?style=for-the-badge&logo=apachekafka&logoColor=white" alt="Apache Kafka">
<img src="https://img.shields.io/badge/Debezium-EF3B2D?style=for-the-badge&logo=debezium&logoColor=white" alt="Debezium">
</p>

# OpenShift Kafka Day Roadshow

Lab guide: [https://maximilianopizarro.github.io/openshift-kafka-day-roadshow/kafka-day-roadshow/main/](https://maximilianopizarro.github.io/openshift-kafka-day-roadshow/kafka-day-roadshow/main/)

## TL;DR

NeuralBank's banking app keeps writing customers and orders to PostgreSQL. In about **2 hours 10 minutes**, participants follow one row change into Kafka, see the notification email, reject a bad event with a JSON Schema, open that route in Kaoto, apply a Camel K `Integration`, and read the pipeline in Grafana. An optional **25 minutes** adds a SCRAM `KafkaUser` exercise and a read-only Keycloak identity map. The banking app is not modified.

Hub-only Validated Pattern, one OpenShift cluster. For 30 people, request **4 workers, `m5a.4xlarge`** (64 vCPU / 256 Gi). Development fits on **2× `m5a.4xlarge`**.

## What the activity explores

You stay inside one business path and light it up piece by piece:

1. **The cluster and your project.** Log in, find the shared `kafka-cdc` namespace, and confirm your own project `userN-workshop`.
2. **Kafka itself.** Topics, partitions, a message you produce, a message you consume, and the same publish through the Kafka Bridge.
3. **The producer.** A banking simulator inserts a customer and an order in PostgreSQL. The write-ahead log is on, so the change can leave the database.
4. **The consumer.** That change becomes an email in Mailpit. You see who read it (the sink consumer group) and run your own consumer.
5. **Debezium.** The Kafka record is the PostgreSQL change: operation, `before`, and `after`. A bad connector event would land on the dead-letter topic; an empty read there means the pipeline is keeping up.
6. **The contract.** Apicurio Registry holds the customer and order JSON Schemas. Camel accepts a valid row and sends an invalid one to `camel.schema-errors` without stopping the route.
7. **The health view.** Grafana shows broker traffic, consumer lag, Debezium, and Connect tasks for the same pipeline.
8. **Your Kafka identity.** Create a SCRAM `KafkaUser` and consume on the TLS listener. Port 9092 stays open for the CDC path.
9. **Keycloak in production.** Read how Red Hat build of Keycloak would issue tokens for an OAuth listener. Nothing is installed on this cluster.

The wrap-up asks what you would harden before this served real customers. No component replaces the banking app. Mail is the HTTP sink, the email transformer, and Mailpit.

## What you learn

| You can explain | Because you did this |
|-----------------|----------------------|
| A database change can become an event without editing the application | Watched PostgreSQL, then the Kafka topic, then the email |
| Topic, partition, consumer group, and lag | Produced, consumed, and described the sink group |
| What a CDC record contains | Read a Debezium `before` / `after` payload |
| A schema is a contract, not a hope | Published one valid and one invalid customer and saw where each went |
| Where to look when the pipeline is quiet or stuck | Ran the Grafana queries for rate, lag, Debezium, and Connect tasks |
| SCRAM proves who you are on a TLS listener | Created a `KafkaUser` and consumed on port 9093 |
| Keycloak belongs in production identity design | Mapped today's path to an OAuth listener without installing Keycloak |

## Workshop Modules

| Module | Title | Duration |
|--------|-------|----------|
| 01 | Lab Setup & Overview | 10 min |
| 02 | Kafka Fundamentals | 20 min |
| 03 | Event Producer: Real Application | 15 min |
| 04 | Event Consumer: Processing Pipeline | 15 min |
| 05 | Debezium CDC | 20 min |
| 06 | Camel and Apicurio Registry | 30 min |
| 07 | Monitoring | 15 min |
| 08 | Kafka Users | 15 min |
| 09 | Authentication with Keycloak | 10 min |
| 10 | Wrap-up | 5 min |

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
- **Camel K + Kaoto** -- Personal `Integration` that mirrors the schema-check route

## Quick Start

### Prerequisites

- OpenShift 4.17+ with the **Validated Patterns Operator** installed
- The **Community Operators** catalog enabled (Grafana is installed from it)
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

Cluster admin on the same login form: `kubeadmin` / `Welcome123!` (`cluster-admin`).

The pattern adds the `workshop-htpasswd` identity provider and removes a sandbox Keycloak provider named `rhbk` when it is present. Other identity providers stay. No Keycloak setup is required.

## Cluster Sizing

| Scenario | Workers | Instance Type | Total vCPU | Total RAM |
|----------|---------|---------------|------------|-----------|
| Development | 2 | m5a.4xlarge | 32 | 128 Gi |
| Workshop (30 users) | 4 | m5a.4xlarge | 64 | 256 Gi |

## Maintainer

**Maximiliano Pizarro** -- Specialist Solution Architect -- mapizarr@redhat.com

## License

Apache License 2.0
