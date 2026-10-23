#!/usr/bin/env python3
import base64
import json
import logging
import os
import ssl
import sys
import urllib.request
import urllib.error
from http.server import HTTPServer, BaseHTTPRequestHandler
from socketserver import ThreadingMixIn

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(name)s] %(levelname)s %(message)s",
)
logger = logging.getLogger("webhook")

TLS_CERT = os.environ.get('TLS_CERT_PATH', '/tls/tls.crt')
TLS_KEY = os.environ.get('TLS_KEY_PATH', '/tls/tls.key')
SERVICE_CA_PATH = os.environ.get('SERVICE_CA_PATH', '/service-ca/service-ca.crt')
KUBE_API = "https://kubernetes.default.svc"
SA_TOKEN_PATH = "/var/run/secrets/kubernetes.io/serviceaccount/token"
SA_CA_PATH = "/var/run/secrets/kubernetes.io/serviceaccount/ca.crt"
ROUTE_URL = (
    f"{KUBE_API}/apis/route.openshift.io/v1"
    "/namespaces/openshift-authentication/routes/oauth-openshift"
)
ROUTES_URL = (
    f"{KUBE_API}/apis/route.openshift.io/v1"
    "/namespaces/openshift-authentication/routes"
)
RECONCILE_INITIAL_INTERVAL = int(os.environ.get('RECONCILE_INITIAL_INTERVAL', '30'))
RECONCILE_MAX_INTERVAL = int(os.environ.get('RECONCILE_MAX_INTERVAL', '60'))
RECONCILE_API_TIMEOUT = int(os.environ.get('RECONCILE_API_TIMEOUT', '10'))
WATCH_TIMEOUT = int(os.environ.get('WATCH_TIMEOUT', '300'))

def load_service_ca():
    try:
        with open(SERVICE_CA_PATH) as f:
            ca = f.read().strip()
        if ca:
            logger.info("Loaded service CA (%d bytes)", len(ca))
            return ca
    except FileNotFoundError:
        pass
    logger.warning("No service CA found")
    return None

SERVICE_CA = load_service_ca()


# ---------------------------------------------------------------------------
# Route reconciliation — watches the oauth-openshift route and reverts it
# to reencrypt whenever the authentication operator sets it to passthrough.
#
# Phase 1 (startup): poll with backoff until the route is confirmed OK.
# Phase 2 (watch):   open a Kubernetes watch and react immediately.
#                     Reconnects indefinitely on errors or server timeouts.
# ---------------------------------------------------------------------------

class _GoneError(Exception):
    """Raised when the API server returns 410 Gone for a watch."""


def _load_sa_token():
    """Read the projected ServiceAccount token (refreshed by kubelet)."""
    try:
        with open(SA_TOKEN_PATH) as f:
            return f.read().strip()
    except FileNotFoundError:
        return None


_KUBE_SSL_CTX = None


def _kube_ssl_context():
    global _KUBE_SSL_CTX
    if _KUBE_SSL_CTX is None:
        _KUBE_SSL_CTX = ssl.create_default_context(cafile=SA_CA_PATH)
    return _KUBE_SSL_CTX


def _patch_to_reencrypt(token, ctx):
    """Patch oauth-openshift from passthrough to reencrypt."""
    patch_body = json.dumps({
        "spec": {
            "tls": {
                "termination": "reencrypt",
                "insecureEdgeTerminationPolicy": "Redirect",
                "destinationCACertificate": SERVICE_CA,
            }
        }
    }).encode()
    req = urllib.request.Request(ROUTE_URL, data=patch_body, method='PATCH')
    req.add_header("Authorization", f"Bearer {token}")
    req.add_header("Content-Type", "application/merge-patch+json")
    req.add_header("Accept", "application/json")
    with urllib.request.urlopen(req, context=ctx, timeout=RECONCILE_API_TIMEOUT) as resp:
        resp.read()
    logger.info("Patched oauth-openshift: passthrough -> reencrypt")


# ---------------------------------------------------------------------------
# Admission webhook server
# ---------------------------------------------------------------------------

class ThreadedHTTPServer(ThreadingMixIn, HTTPServer):
    daemon_threads = True
    allow_reuse_address = True

MAX_BODY_SIZE = 1_048_576  # 1 MB


class Handler(BaseHTTPRequestHandler):
    def do_GET(self):
        if self.path == '/healthz':
            if SERVICE_CA:
                self.send_response(200)
                self.send_header('Content-Type', 'text/plain')
                self.end_headers()
                self.wfile.write(b'ok')
            else:
                self.send_response(503)
                self.send_header('Content-Type', 'text/plain')
                self.end_headers()
                self.wfile.write(b'service CA not loaded')
        else:
            self.send_response(404)
            self.end_headers()

    def do_POST(self):
        uid = None
        try:
            length = int(self.headers.get('Content-Length', 0))
            if length > MAX_BODY_SIZE:
                self.send_response(413)
                self.end_headers()
                return
            body = json.loads(self.rfile.read(length))
            uid = body['request']['uid']
            resp = self.handle_review(body, uid)
        except Exception as e:
            logger.error("Error processing admission request: %s", e)
            resp = self.allow(uid or "unknown")
        self.send_response(200)
        self.send_header('Content-Type', 'application/json')
        self.end_headers()
        self.wfile.write(json.dumps(resp).encode())

    def handle_review(self, body, uid):
        obj = body['request'].get('object', {})
        name = obj.get('metadata', {}).get('name', '')
        ns = obj.get('metadata', {}).get('namespace', '')
        tls = obj.get('spec', {}).get('tls', {})
        termination = tls.get('termination', '')

        if name != 'oauth-openshift' or ns != 'openshift-authentication':
            return self.allow(uid)
        if termination != 'passthrough':
            return self.allow(uid)
        if not SERVICE_CA:
            return self.allow(uid)

        patches = [
            {"op": "replace", "path": "/spec/tls/termination", "value": "reencrypt"},
            {"op": "add", "path": "/spec/tls/insecureEdgeTerminationPolicy", "value": "Redirect"},
            {"op": "add", "path": "/spec/tls/destinationCACertificate", "value": SERVICE_CA},
        ]
        logger.info("Mutating Route/%s: passthrough -> reencrypt", name)
        return {
            "apiVersion": "admission.k8s.io/v1",
            "kind": "AdmissionReview",
            "response": {
                "uid": uid,
                "allowed": True,
                "patchType": "JSONPatch",
                "patch": base64.b64encode(json.dumps(patches).encode()).decode()
            }
        }

    def allow(self, uid):
        return {
            "apiVersion": "admission.k8s.io/v1",
            "kind": "AdmissionReview",
            "response": {"uid": uid, "allowed": True}
        }

    def log_message(self, fmt, *args):
        if self.path != '/healthz':
            logger.debug(fmt, *args)

def _reconcile_loop(stop_event):
    """Ensure the oauth-openshift route stays reencrypt.

    Phase 1 (startup): poll with exponential backoff until the route is
    confirmed as reencrypt or successfully patched.

    Phase 2 (watch): open a Kubernetes watch on the route and react to
    changes immediately.  Reconnects indefinitely on errors or
    server-side timeouts.
    """
    interval = RECONCILE_INITIAL_INTERVAL
    while not stop_event.is_set():
        try:
            result = _reconcile_once()
            if result in ('ok', 'patched'):
                logger.info("Startup check passed, switching to watch")
                break
            interval = min(interval * 2, RECONCILE_MAX_INTERVAL)
        except Exception as e:
            logger.error("Startup error: %s", e)
            interval = min(interval * 2, RECONCILE_MAX_INTERVAL)
        stop_event.wait(interval)

    backoff = 0
    while not stop_event.is_set():
        if backoff > 0:
            stop_event.wait(backoff)
            if stop_event.is_set():
                return
        try:
            _watch_route(stop_event)
            backoff = 0
        except _GoneError:
            logger.info("Watch 410 Gone, restarting")
            backoff = 0
        except Exception as e:
            logger.error("Watch error: %s", e)
            backoff = min(
                max(backoff * 2, RECONCILE_INITIAL_INTERVAL),
                RECONCILE_MAX_INTERVAL,
            )


def _watch_route(stop_event):
    """Open a Kubernetes watch on the oauth-openshift route.

    Returns normally when the server closes the stream (timeout).
    Raises _GoneError on 410 Gone so the caller can retry with a
    fresh resourceVersion.
    """
    token = _load_sa_token()
    if not token:
        raise RuntimeError("no ServiceAccount token")
    ctx = _kube_ssl_context()

    get_req = urllib.request.Request(ROUTE_URL)
    get_req.add_header("Authorization", f"Bearer {token}")
    get_req.add_header("Accept", "application/json")
    with urllib.request.urlopen(get_req, context=ctx,
                                timeout=RECONCILE_API_TIMEOUT) as resp:
        route = json.loads(resp.read())

    rv = route.get('metadata', {}).get('resourceVersion', '')

    tls = route.get('spec', {}).get('tls', {})
    if tls.get('termination') == 'passthrough' and SERVICE_CA:
        _patch_to_reencrypt(token, ctx)

    watch_url = (
        f"{ROUTES_URL}"
        f"?watch=true"
        f"&fieldSelector=metadata.name%3Doauth-openshift"
        f"&resourceVersion={rv}"
        f"&timeoutSeconds={WATCH_TIMEOUT}"
        f"&allowWatchBookmarks=true"
    )
    watch_req = urllib.request.Request(watch_url)
    watch_req.add_header("Authorization", f"Bearer {token}")
    watch_req.add_header("Accept", "application/json")

    socket_timeout = WATCH_TIMEOUT + 60
    logger.info("Watch opened (rv=%s, timeout=%ds)", rv, WATCH_TIMEOUT)

    with urllib.request.urlopen(watch_req, context=ctx,
                                timeout=socket_timeout) as resp:
        for raw_line in resp:
            if stop_event.is_set():
                return
            line = raw_line.strip()
            if not line:
                continue
            try:
                event = json.loads(line)
            except json.JSONDecodeError:
                continue

            event_type = event.get('type', '')
            obj = event.get('object', {})

            if event_type == 'ERROR':
                if obj.get('code') == 410:
                    raise _GoneError()
                logger.warning("Watch error event: %s",
                               obj.get('message', ''))
                continue

            if event_type == 'BOOKMARK':
                continue

            if event_type in ('ADDED', 'MODIFIED'):
                obj_tls = obj.get('spec', {}).get('tls', {})
                if obj_tls.get('termination') == 'passthrough' and SERVICE_CA:
                    logger.info("Watch: passthrough detected, patching")
                    try:
                        token = _load_sa_token() or token
                        _patch_to_reencrypt(token, ctx)
                    except Exception as e:
                        logger.error("Watch: patch failed: %s", e)

    logger.info("Watch closed normally")


def _reconcile_once():
    """Check and fix the oauth-openshift route.

    Returns 'ok' (already reencrypt), 'patched' (fixed), or 'retry' (error).
    """
    if not SERVICE_CA:
        return 'retry'

    token = _load_sa_token()
    if not token:
        logger.warning("No ServiceAccount token available")
        return 'retry'

    ctx = _kube_ssl_context()

    req = urllib.request.Request(ROUTE_URL)
    req.add_header("Authorization", f"Bearer {token}")
    req.add_header("Accept", "application/json")
    try:
        with urllib.request.urlopen(req, context=ctx, timeout=RECONCILE_API_TIMEOUT) as resp:
            route = json.loads(resp.read())
    except Exception as e:
        logger.error("GET oauth-openshift failed: %s", e)
        return 'retry'

    tls = route.get('spec', {}).get('tls', {})
    if tls.get('termination') != 'passthrough':
        return 'ok'

    try:
        _patch_to_reencrypt(token, ctx)
        return 'patched'
    except urllib.error.HTTPError as e:
        body = ""
        try:
            body = e.read().decode()[:500]
        except Exception:
            pass
        logger.error("PATCH oauth-openshift failed: %s %s", e, body)
        return 'retry'
    except Exception as e:
        logger.error("PATCH oauth-openshift failed: %s", e)
        return 'retry'


if __name__ == '__main__':
    import signal
    import threading

    # --- Background watch-based reconciler ---
    stop_event = threading.Event()
    reconciler = threading.Thread(target=_reconcile_loop, args=(stop_event,), daemon=True)
    reconciler.start()
    logger.info("Background reconciler started")

    # --- Webhook HTTPS server ---
    server = ThreadedHTTPServer(('0.0.0.0', 8443), Handler)
    ctx = ssl.create_default_context(ssl.Purpose.CLIENT_AUTH)
    ctx.load_cert_chain(TLS_CERT, TLS_KEY)
    server.socket = ctx.wrap_socket(server.socket, server_side=True)

    def shutdown_handler(signum, frame):
        logger.info("Received signal %s, shutting down...", signum)
        stop_event.set()
        threading.Thread(target=server.shutdown).start()

    signal.signal(signal.SIGTERM, shutdown_handler)
    signal.signal(signal.SIGINT, shutdown_handler)

    logger.info("OAuth route mutating webhook listening on :8443")
    server.serve_forever()
