# Camel and Apicurio Registry module

Date: 2026-10-22
Status: approved design, pending spec review

## Goal

Add one workshop module, between Debezium and Monitoring, where the student explores a pre-deployed Red Hat build of Apicurio Registry 3 and a Camel Quarkus route. The route validates CDC rows and lab-published JSON against schemas stored in the registry.

The shared namespace remains `kafka-cdc`. Students do not install operators and do not register their own schemas.

## Decisions

- Install the Red Hat operator `apicurio-registry-3` from `redhat-operators`, channel `3.x`, into `openshift-operators`.
- Do not install `service-registry-operator` (2.x) or `red-hat-camel-k`.
- Store registry data with `kafkasql` on the existing cluster `cdc-cluster`, listener plain `cdc-cluster-kafka-bootstrap:9092`.
- Run Camel as a Deployment built in-cluster from this repo. The image is Camel Quarkus on UBI9 OpenJDK 21, dependencies from Maven Central. The route YAML is a ConfigMap mounted into the pod.
- Leave Argo CD automated sync as `selfHeal: true` only. Do not enable prune on `cdc-pipeline`, `observability`, or any other app. Do not add or remove a Namespace manifest.

## Data flow

```text
PostgreSQL -> Debezium -> cdc.public.customers / cdc.public.orders
                                |
                                v
                         Camel (reads "after")
                                |
                    fetches the schema from Apicurio
                                |
              valid   -> camel.public.customers / camel.public.orders
              invalid -> camel.schema-errors

Kafka Bridge -> camel.schema-check -> the same Camel deployment
                                |
              valid   -> camel.validated
              invalid -> camel.schema-errors
```

`camel.schema-check` is validated only against `customers-value`. Orders are validated from `cdc.public.orders`.

## Schemas

Group `workshop`. Artifact type `JSON`. Version `1` is set explicitly. A compatibility rule `BACKWARD` is created on each artifact. Students can read the rule. They do not change it.

`customers-value`:

```json
{
  "$schema": "https://json-schema.org/draft/2020-12/schema",
  "type": "object",
  "title": "Customer",
  "required": ["first_name", "last_name", "email"],
  "properties": {
    "id": { "type": "integer" },
    "first_name": { "type": "string", "minLength": 1 },
    "last_name": { "type": "string", "minLength": 1 },
    "email": { "type": "string", "pattern": "^[^@]+@[^@]+\\.[^@]+$" }
  }
}
```

`orders-value`:

```json
{
  "$schema": "https://json-schema.org/draft/2020-12/schema",
  "type": "object",
  "title": "Order",
  "required": ["product", "amount", "status", "customer_id"],
  "properties": {
    "id": { "type": "integer" },
    "product": { "type": "string", "minLength": 1 },
    "amount": { "type": "string", "pattern": "^[0-9]+(\\.[0-9]+)?$" },
    "status": { "type": "string" },
    "customer_id": { "type": "integer" }
  }
}
```

`additionalProperties` is left at the JSON Schema default (allowed). Debezium `decimal.handling.mode` is `string`, so `amount` is a string. An extra column such as `phone` still validates.

## Cluster resources

### Subscription

Add this entry under `clusterGroup.subscriptions` in `values-hub.yaml`:

```yaml
apicurio-registry-3:
  name: apicurio-registry-3
  namespace: openshift-operators
  channel: 3.x
  source: redhat-operators
```

### Template

New file `charts/all/cdc-pipeline/templates/camel-apicurio.yaml`. Every object sets `argocd.argoproj.io/sync-options: SkipDryRunOnMissingResource=true` where the CRD or image may be absent on the first sync.

Sync waves:

| Wave | Objects |
|------|---------|
| 3 | KafkaTopics |
| 4 | ApicurioRegistry3, schema ConfigMap, Camel route ConfigMap, BuildConfig, ImageStream |
| 5 | Schema seed Job |
| 6 | Camel Deployment |

### Topics

All topics use `strimzi.io/cluster: cdc-cluster`, 3 partitions, replication factor 3.

`kafkasql-journal` is the registry journal. Its config is exactly:

```yaml
config:
  cleanup.policy: delete
  retention.ms: -1
  retention.bytes: -1
```

Lab topics. Do not set `cleanup.policy` or retention on these; Strimzi's default retention applies:

- `camel.schema-check`
- `camel.validated`
- `camel.schema-errors`
- `camel.public.customers`
- `camel.public.orders`

### ApicurioRegistry3

```yaml
apiVersion: registry.apicur.io/v1
kind: ApicurioRegistry3
metadata:
  name: cdc-registry
  namespace: kafka-cdc
spec:
  app:
    replicas: 1
    storage:
      type: kafkasql
      kafkasql:
        bootstrapServers: cdc-cluster-kafka-bootstrap:9092
    ingress:
      host: cdc-registry-kafka-cdc.<clusterDomain>
    podDisruptionBudget:
      enabled: false
    podTemplateSpec:
      spec:
        containers:
          - name: apicurio-registry-app
            resources:
              requests:
                memory: 512Mi
                cpu: 100m
              limits:
                memory: 1Gi
                cpu: "500m"
  ui:
    replicas: 1
    ingress:
      host: cdc-registry-ui-kafka-cdc.<clusterDomain>
    env:
      - name: REGISTRY_API_URL
        value: https://cdc-registry-kafka-cdc.<clusterDomain>/apis/registry/v3
    podDisruptionBudget:
      enabled: false
    podTemplateSpec:
      spec:
        containers:
          - name: apicurio-registry-ui
            resources:
              requests:
                memory: 256Mi
                cpu: 50m
              limits:
                memory: 512Mi
                cpu: 200m
```

`<clusterDomain>` is `.Values.clusterDomain`, the same value the other routes already use. Auth is omitted, so the API and UI stay anonymous. `spec.consolePlugin` stays unset, which defaults to disabled.

The operator creates the Routes. The chart does not create a second Route or a second Ingress.

In-cluster API base URL: `http://cdc-registry-app-service.kafka-cdc.svc:8080`. The operator names the app Deployment `{cr-name}-app-deployment` and the Service `{cr-name}-app-service`. During verification, `oc get svc -n kafka-cdc -l app.kubernetes.io/component=app` must return that Service. If the Service name differs, the seed Job and `APICURIO_BASE_URL` change to the Service that exists before the module is marked done.

Port 8080 is already allowed by `kafka-cdc-allow-internal`. Add a port to that policy only if the UI Service listens on a port other than 8080.

### Schema seed Job

ConfigMap `cdc-registry-schemas` holds the two schema documents above.

A Job `cdc-registry-seed` uses `registry.access.redhat.com/ubi9/python-311:latest`. `restartPolicy: OnFailure`, `backoffLimit: 20`. It retries the API until a TCP connection succeeds.

For each artifact it POSTs `Content-Type: application/json` to:

`/apis/registry/v3/groups/workshop/artifacts`

```json
{
  "artifactId": "<id>",
  "artifactType": "JSON",
  "firstVersion": {
    "version": "1",
    "content": {
      "content": "<schema document as a string>",
      "contentType": "application/json"
    }
  }
}
```

HTTP 200 and 409 are success. Any other status fails the attempt.

It then ensures the compatibility rule. POST `Content-Type: application/json` to `/apis/registry/v3/groups/workshop/artifacts/<id>/rules` with body `{"ruleType":"COMPATIBILITY","config":"BACKWARD"}`. HTTP 200, 204, and 409 are success.

It finishes only after both contents return HTTP 200 from:

`/apis/registry/v3/groups/workshop/artifacts/<id>/versions/1/content`

### Camel application

Source directory: `camel/cdc-router`.

- BOM: `org.apache.camel.quarkus:camel-quarkus-bom:3.20.0` from Maven Central, Java 21.
- Dependencies: `camel-quarkus-yaml-dsl`, `camel-quarkus-kafka`, `camel-quarkus-jackson`, `camel-quarkus-bean`, and `com.networknt:json-schema-validator:1.5.6`.
- Dockerfile build stage `registry.access.redhat.com/ubi9/openjdk-21:latest`, runtime stage `registry.access.redhat.com/ubi9/openjdk-21-runtime:latest`.
- BuildConfig `cdc-camel-router`, Docker strategy, context dir `camel/cdc-router`, git URI `https://github.com/maximilianoPizarro/openshift-kafka-day-roadshow.git`, ref `main`.
- Build resources: request 1Gi memory, limit 2Gi memory.
- Output ImageStream `cdc-camel-router:latest` in `kafka-cdc`.
- Deployment `cdc-camel-router`, one replica, image `image-registry.openshift-image-registry.svc:5000/kafka-cdc/cdc-camel-router:latest`, `imagePullPolicy: Always`.
- Container resources: request 256Mi, limit 512Mi.
- Env `APICURIO_BASE_URL=http://cdc-registry-app-service.kafka-cdc.svc:8080` and `KAFKA_BOOTSTRAP=cdc-cluster-kafka-bootstrap:9092`.
- ConfigMap `cdc-camel-routes` mounted at `/etc/camel`. Camel loads `file:/etc/camel/routes.yaml`.

The image contains one bean, `schemaGuard`. It fetches version `1` of an artifact, caches the parsed schema for 30 seconds, and validates the JSON object with networknt. A fetch or network failure throws an exception that the route does not catch, so Camel retries the exchange. A schema mismatch, a JSON parse error, or a CDC event whose `after` is null throws `SchemaValidationException`, which the route catches.

`routes.yaml` defines three routes. All use `cdc-cluster-kafka-bootstrap:9092` and `autoOffsetReset=earliest`.

| Route id | Input | groupId | Schema | Valid output |
|----------|-------|---------|--------|----------------|
| `schema-check` | `camel.schema-check` | `camel-schema-check` | `customers-value` | `camel.validated` |
| `cdc-customers` | `cdc.public.customers` | `camel-cdc-customers` | `customers-value` | `camel.public.customers` |
| `cdc-orders` | `cdc.public.orders` | `camel-cdc-orders` | `orders-value` | `camel.public.orders` |

CDC routes unmarshal the Debezium JSON envelope and replace the body with `after` before validation. The check route validates the record body as the customer row.

Valid body written to Kafka:

```json
{"schema":"customers-value","source":"bridge","after":{"first_name":"Workshop","last_name":"User","email":"workshop.user1@neuralbank.io"}}
```

`schema` is the artifact id used for that route. `source` is `bridge` for `schema-check` and `debezium` for the CDC routes. `after` is the validated row.

Invalid body written to `camel.schema-errors`:

```json
{"error":"<exception message>","source":"bridge|debezium","payload":"<original record text>"}
```

The consumer continues after an invalid record.

### RBAC

Add this rule to Role `workshop-lab` in `charts/all/cdc-pipeline/templates/workshop-rbac.yaml`:

```yaml
- apiGroups: ["registry.apicur.io"]
  resources: ["apicurioregistries3"]
  verbs: ["get", "list", "watch"]
```

Existing RoleBindings for `user1` through `user30` already point at that Role.

## Lab module

New page `content/modules/ROOT/pages/06-camel-apicurio.adoc`, title **Red Hat build of Apache Camel and Apicurio Registry**, about 20 minutes.

Rename:

- `06-monitoring.adoc` to `07-monitoring.adoc`
- `07-summary.adoc` to `08-summary.adoc`

Update the module list in:

- `content/modules/ROOT/nav.adoc`
- `content/modules/ROOT/pages/index.adoc` (module table and the component table)
- `content/modules/ROOT/pages/08-summary.adoc` (takeaways and the ASCII diagram)
- `ui-config.yml` (`antora.modules` stems and labels)
- `README.md` (module table and component list)

`content/modules/ROOT/assets/images/cdc-architecture.jpg` stays as the CDC overview. The new components are described in the welcome table and the wrap-up diagram.

The wrap-up no longer lists Apicurio as future work. It lists what the new module covered.

Showroom userdata in `charts/all/showroom/templates/showroom-deploy.yaml` and the placeholders in `content/antora.yml` gain:

- `registry_url`: `https://cdc-registry-kafka-cdc.<domain>`
- `registry_ui_url`: `https://cdc-registry-ui-kafka-cdc.<domain>`

`ui-config.yml` gains a tab:

```yaml
- name: Registry
  url: 'https://cdc-registry-ui-kafka-cdc.${DOMAIN}'
```

If the UI response includes `X-Frame-Options: DENY` or `frame-ancestors 'none'`, set `external: true` on that tab.

Every lab source block that contains an attribute uses `subs="+attributes"`. Registry and bridge curls use `curl -sk`.

Lab steps, in order:

1. Explain the registry and the Camel route with the data-flow diagram from this spec.
2. `oc get apicurioregistry3 cdc-registry -n kafka-cdc`, followed by the expected CR YAML (storage, hosts, replicas).
3. `oc get kafkatopic kafkasql-journal -n kafka-cdc`, followed by the expected topic YAML including infinite retention.
4. Open the Registry tab and find group `workshop`, artifacts `customers-value` and `orders-value`.
5. `curl -sk {registry_url}/apis/registry/v3/groups/workshop/artifacts/customers-value/versions/1/content`
6. `curl -sk {registry_url}/apis/registry/v3/groups/workshop/artifacts/customers-value/rules` and read `BACKWARD`.
7. `oc get configmap cdc-camel-routes -n kafka-cdc -o yaml`, followed by the expected route YAML.
8. `oc get kafkatopic -n kafka-cdc` and point at the five `camel.*` topics.
9. POST a valid customer to `{bridge_url}/topics/camel.schema-check` with `Content-Type: application/vnd.kafka.json.v2+json` and body `{"records":[{"value":{"first_name":"Workshop","last_name":"User","email":"workshop.user1@neuralbank.io"}}]}`.
10. Consume `camel.validated` with `oc run` in `kafka-cdc`, image `registry.redhat.io/amq-streams/kafka-38-rhel9:latest`, `--rm`, `--from-beginning`, a small `--max-messages`.
11. POST an invalid customer, value `{"first_name":"Schema","last_name":"Test"}`, to the same topic.
12. Consume `camel.schema-errors` the same way and find that record.
13. Consume `camel.public.customers` and find a Debezium row whose output `source` is `debezium`.

The page states that all 30 users share these topics. The Deployment is the only validating consumer. Each student reads with a new consumer group and looks for their own email.

Expected YAML blocks match the chart. They are offline copies, same pattern as the Debezium page.

## Failure behavior

| Condition | Behavior |
|-----------|----------|
| Registry CRD missing on first Argo sync | `SkipDryRunOnMissingResource` lets the sync continue; a later reconcile creates the CR |
| Journal topic missing infinite retention | Registry must not be left in that state; the topic manifest above is applied at wave 3, before the CR at wave 4 |
| Seed POST returns 409 | Treated as success |
| Registry API not ready | Seed Job retries up to `backoffLimit` 20 |
| Camel image not built yet | Deployment stays in `ImagePullBackOff` until the Build completes; Argo may show the app degraded during the build |
| Schema fetch fails | Exchange is not caught as a validation error; Camel retries it |
| Invalid JSON, schema mismatch, or CDC `after: null` | One record is produced to `camel.schema-errors`; the consumer continues |
| UI cannot call the API from the browser | `REGISTRY_API_URL` points at the public API route |
| UI cannot be iframed | Registry tab is `external: true` |

## Verification

After the change is pushed to `main`:

1. Hard-refresh Applications `cdc-pipeline` and `showroom` in `vp-gitops`. Roll the showroom Deployment so the content pod reclones `main`. Do not enable prune.
2. Subscription `apicurio-registry-3` in `openshift-operators` reaches `Succeeded`.
3. `ApicurioRegistry3` `cdc-registry` is Ready. App and UI pods are Running. `kafkasql-journal` has `retention.ms=-1` and `retention.bytes=-1`.
4. API route and UI route return HTTP 200. The two artifacts exist and the compatibility rule is `BACKWARD`.
5. Build `cdc-camel-router` completes and Deployment `cdc-camel-router` becomes Ready.
6. A valid bridge record appears on `camel.validated` with `source` `bridge`. An invalid bridge record appears on `camel.schema-errors`. A CDC customer appears on `camel.public.customers` with `source` `debezium`.
7. `oc auth can-i get apicurioregistries3.registry.apicur.io -n kafka-cdc --as=user1` is `yes`.
8. The showroom page `06-camel-apicurio.html` returns HTTP 200, the registry curl shows the real host, and the Registry tab loads or is external.

## Out of scope

- Avro, Protobuf, and a second schema version published during the lab.
- Per-user schemas or per-user Camel Integrations.
- Camel K `Integration` custom resources.
- Changing the CDC architecture image.
- Enabling Argo CD prune or recreating the `kafka-cdc` namespace.
