import json
import os
import ssl
import time
import urllib.error
import urllib.request

WORKSHOP = {
    "name": "workshop-htpasswd",
    "mappingMethod": "claim",
    "type": "HTPasswd",
    "htpasswd": {"fileData": {"name": "workshop-htpasswd"}},
}


def desired(providers):
    """Drop the sandbox Keycloak provider and ensure the workshop HTPasswd provider."""
    kept = []
    found = False
    for provider in providers or []:
        name = provider.get("name")
        if name == "rhbk":
            continue
        if name == "workshop-htpasswd":
            kept.append(WORKSHOP)
            found = True
            continue
        kept.append(provider)
    if not found:
        kept.append(WORKSHOP)
    return kept


def already_set(providers):
    if any(provider.get("name") == "rhbk" for provider in providers or []):
        return False
    for provider in providers or []:
        if provider.get("name") != "workshop-htpasswd":
            continue
        secret = ((provider.get("htpasswd") or {}).get("fileData") or {}).get("name")
        return provider.get("type") == "HTPasswd" and secret == "workshop-htpasswd"
    return False


def main():
    host = os.environ["KUBERNETES_SERVICE_HOST"]
    port = os.environ.get("KUBERNETES_SERVICE_PORT", "443")
    base = f"https://{host}:{port}"
    token = open("/var/run/secrets/kubernetes.io/serviceaccount/token", encoding="utf-8").read().strip()
    context = ssl.create_default_context(
        cafile="/var/run/secrets/kubernetes.io/serviceaccount/ca.crt"
    )

    def request(method, path, body=None, content_type=None):
        data = None if body is None else json.dumps(body).encode()
        req = urllib.request.Request(base + path, data=data, method=method)
        req.add_header("Authorization", "Bearer " + token)
        if content_type:
            req.add_header("Content-Type", content_type)
        try:
            with urllib.request.urlopen(req, context=context, timeout=20) as resp:
                return resp.status, resp.read()
        except urllib.error.HTTPError as exc:
            return exc.code, exc.read()

    secret_path = "/api/v1/namespaces/openshift-config/secrets/workshop-htpasswd"
    deadline = time.time() + 180
    while time.time() < deadline:
        status, _ = request("GET", secret_path)
        if status == 200:
            break
        print("waiting for workshop-htpasswd", status, flush=True)
        time.sleep(5)
    else:
        raise SystemExit("workshop-htpasswd secret not found")

    status, body = request("GET", "/apis/config.openshift.io/v1/oauths/cluster")
    if status != 200:
        raise SystemExit(f"get oauth failed {status} {body[:300]!r}")
    current = ((json.loads(body).get("spec") or {}).get("identityProviders")) or []
    if already_set(current):
        print("oauth already includes workshop-htpasswd", flush=True)
        return
    updated = desired(current)
    status, body = request(
        "PATCH",
        "/apis/config.openshift.io/v1/oauths/cluster",
        {"spec": {"identityProviders": updated}},
        "application/merge-patch+json",
    )
    print("patch", status, body[:300], flush=True)
    if status != 200:
        raise SystemExit(f"patch oauth failed {status}")
    print("oauth ok", flush=True)


if __name__ == "__main__":
    main()
