"""Create the Camel K platform in every workshop project.

The operator publishes a kit with an empty registry host unless the project
that owns the Integration has an IntegrationPlatform. OpenShift names the
default pull secret per namespace, so the secret cannot be rendered in Helm.
"""

import json
import os
import ssl
import time
import urllib.error
import urllib.request


REGISTRY = "image-registry.openshift-image-registry.svc:5000"
CRD = (
    "/apis/apiextensions.k8s.io/v1/customresourcedefinitions/"
    "integrationplatforms.camel.apache.org"
)


def platform(secret):
    return {
        "apiVersion": "camel.apache.org/v1",
        "kind": "IntegrationPlatform",
        "metadata": {
            "name": "camel-k",
            "labels": {
                "app.kubernetes.io/part-of": "openshift-kafka-day-roadshow",
                "app.kubernetes.io/name": "camel-k",
            },
        },
        "spec": {
            "profile": "OpenShift",
            "build": {
                "publishStrategy": "S2I",
                "timeout": "20m",
                "registry": {
                    "address": REGISTRY,
                    "secret": secret,
                    "insecure": True,
                },
                "buildConfiguration": {"strategy": "routine"},
            },
        },
    }


def same(current, desired):
    build = ((current.get("spec") or {}).get("build") or {})
    wanted = desired["spec"]["build"]
    registry = build.get("registry") or {}
    wanted_registry = wanted["registry"]
    return (
        (current.get("spec") or {}).get("profile") == "OpenShift"
        and build.get("publishStrategy") == wanted["publishStrategy"]
        and build.get("timeout") == wanted["timeout"]
        and (build.get("buildConfiguration") or {}).get("strategy") == "routine"
        and registry.get("address") == wanted_registry["address"]
        and registry.get("secret") == wanted_registry["secret"]
        and registry.get("insecure") is True
    )


def main():
    count = int(os.environ["USER_COUNT"])
    host = os.environ["KUBERNETES_SERVICE_HOST"]
    port = os.environ.get("KUBERNETES_SERVICE_PORT", "443")
    base = f"https://{host}:{port}"
    token = open(
        "/var/run/secrets/kubernetes.io/serviceaccount/token", encoding="utf-8"
    ).read().strip()
    context = ssl.create_default_context(
        cafile="/var/run/secrets/kubernetes.io/serviceaccount/ca.crt"
    )

    def request(method, path, body=None, content_type=None):
        data = None if body is None else json.dumps(body).encode()
        req = urllib.request.Request(base + path, data=data, method=method)
        req.add_header("Authorization", "Bearer " + token)
        if body is not None:
            req.add_header("Content-Type", content_type or "application/json")
        try:
            with urllib.request.urlopen(req, context=context, timeout=30) as resp:
                return resp.status, resp.read()
        except urllib.error.HTTPError as exc:
            return exc.code, exc.read()

    deadline = time.time() + 900
    while time.time() < deadline:
        status, _ = request("GET", CRD)
        if status == 200:
            break
        print("waiting for Camel K CRD", status, flush=True)
        time.sleep(10)
    else:
        raise SystemExit("integrationplatforms.camel.apache.org was not installed")

    for index in range(1, count + 1):
        namespace = f"user{index}-workshop"
        secret = wait_pull_secret(request, namespace)
        ensure(request, namespace, secret)

    # The operator installs a Camel catalog per project after the object
    # exists. That can take several minutes and must not block the rest
    # of the pattern sync. The lab runs later, when the platforms are Ready.
    print(f"IntegrationPlatform camel-k created in {count} projects", flush=True)


def wait_pull_secret(request, namespace):
    path = f"/api/v1/namespaces/{namespace}/serviceaccounts/default"
    deadline = time.time() + 180
    while time.time() < deadline:
        status, body = request("GET", path)
        if status == 200:
            secrets = json.loads(body).get("imagePullSecrets") or []
            if secrets and secrets[0].get("name"):
                return secrets[0]["name"]
        print(f"waiting for pull secret in {namespace}", status, flush=True)
        time.sleep(5)
    raise SystemExit(f"{namespace} default ServiceAccount has no imagePullSecrets")


def ensure(request, namespace, secret):
    collection = f"/apis/camel.apache.org/v1/namespaces/{namespace}/integrationplatforms"
    path = collection + "/camel-k"
    desired = platform(secret)
    status, body = request("GET", path)
    if status == 404:
        status, body = request("POST", collection, desired)
        if status not in (200, 201):
            raise SystemExit(f"create {namespace} failed {status} {body[:400]!r}")
        print(f"created IntegrationPlatform in {namespace}", flush=True)
    elif status == 200:
        current = json.loads(body)
        if not same(current, desired):
            status, body = request(
                "PATCH",
                path,
                {"spec": desired["spec"]},
                "application/merge-patch+json",
            )
            if status not in (200, 201):
                raise SystemExit(f"patch {namespace} failed {status} {body[:400]!r}")
            print(f"updated IntegrationPlatform in {namespace}", flush=True)
        else:
            print(f"IntegrationPlatform already set in {namespace}", flush=True)
    else:
        raise SystemExit(f"get {namespace} failed {status} {body[:400]!r}")


if __name__ == "__main__":
    main()
