"""Request telemetry and protected Prometheus exposition, one process per target."""
import logging
import os
import re
import secrets
from time import perf_counter

from flask import Response, g, jsonify, request
from prometheus_client import CollectorRegistry, Counter, Gauge, Histogram, generate_latest
from prometheus_client.exposition import CONTENT_TYPE_LATEST
from werkzeug.exceptions import Unauthorized

from structured_logging import configure_logging, log_event, request_context

PROBE_ENDPOINTS = {'health', 'metrics'}
BUCKETS = (.005, .01, .025, .05, .1, .25, .5, 1, 2.5, 5, 10)


def metrics_token_from_environment():
    token = os.environ.get('COURSESPHERE_METRICS_TOKEN', '')
    if not token and os.environ.get('COURSESPHERE_LOCAL') == '1':
        return ''  # Local development only, and only from a loopback peer.
    if not re.fullmatch(r'[A-Za-z0-9_-]{32,256}', token):
        raise ValueError('Set COURSESPHERE_METRICS_TOKEN to a random URL-safe token of 32 to 256 characters.')
    return token


class Telemetry:
    def __init__(self):
        self.registry = CollectorRegistry()
        labels = ['route', 'method', 'status']
        self.requests = Counter('coursesphere_http_requests_total', 'Completed API requests, excluding probes and OPTIONS.', labels, registry=self.registry)
        self.duration = Histogram('coursesphere_http_request_duration_seconds', 'Time inside Flask through response finalization (not streaming or network).', ['route', 'method', 'outcome'], buckets=BUCKETS, registry=self.registry)
        self.in_progress = Gauge('coursesphere_http_requests_in_progress', 'API requests currently executing, excluding probes and OPTIONS.', registry=self.registry)
        self.auth_events = Counter('coursesphere_auth_events_total', 'Firebase ID token verification outcomes, not password logins.', ['outcome', 'reason'], registry=self.registry)
        self.auth_duration = Histogram('coursesphere_auth_verification_duration_seconds', 'Firebase ID token verification duration.', ['outcome'], buckets=BUCKETS, registry=self.registry)
        self.errors = Counter('coursesphere_errors_total', 'Handled request errors.', ['kind'], registry=self.registry)

    def authentication(self, app, outcome, reason, started):
        self.auth_events.labels(outcome, reason).inc()
        self.auth_duration.labels(outcome).observe(max(0, perf_counter() - started))
        level = {'success': logging.INFO, 'rejected': logging.WARNING, 'error': logging.ERROR}[outcome]
        log_event(app, 'authentication', level, outcome=outcome, reason=reason)

    def error(self, app, event, kind, status):
        self.errors.labels(kind).inc()
        log_event(app, event, logging.ERROR if status >= 500 else logging.WARNING, kind=kind, status=status)


def configure_observability(app):
    if os.environ.get('PROMETHEUS_MULTIPROC_DIR'):
        raise RuntimeError('This telemetry configuration requires one process per scrape target; multiprocess mode is not supported.')
    app.config['COURSESPHERE_METRICS_TOKEN'] = metrics_token_from_environment()
    telemetry = Telemetry()
    app.extensions['telemetry'] = telemetry
    configure_logging(app)

    @app.before_request
    def begin_request():
        g.request_id = secrets.token_hex(16)  # Do not trust a caller-provided ID.
        g.request_started = perf_counter()
        g.track_request = request.endpoint not in PROBE_ENDPOINTS and request.method != 'OPTIONS'
        if g.track_request:
            telemetry.in_progress.inc()

    @app.after_request
    def finish_request(response):
        elapsed = max(0, perf_counter() - g.request_started)
        if g.track_request:
            context = request_context()
            status = response.status_code
            outcome = 'server_error' if status >= 500 else 'client_error' if status >= 400 else 'success'
            telemetry.requests.labels(context['route'], context['method'], str(status)).inc()
            telemetry.duration.labels(context['route'], context['method'], outcome).observe(elapsed)
        log_event(app, 'request_completed', status=response.status_code, duration_ms=round(elapsed * 1000, 3))
        return response

    @app.teardown_request
    def release_request(error):
        if getattr(g, 'track_request', False):
            telemetry.in_progress.dec()
            g.track_request = False

    @app.get('/health')
    def health():
        # Process liveness only: do not imply that Firebase or Redis is available.
        return jsonify(status='ok', check='liveness')

    @app.get('/metrics')
    def metrics():
        token = app.config['COURSESPHERE_METRICS_TOKEN']
        if token:
            parts = request.headers.get('Authorization', '').split()
            if (len(parts) != 2 or parts[0].lower() != 'bearer' or len(parts[1]) > 256
                    or not secrets.compare_digest(parts[1].encode('utf-8'), token.encode('ascii'))):
                raise Unauthorized()
        elif request.remote_addr not in {'127.0.0.1', '::1'}:
            raise Unauthorized()
        return Response(generate_latest(telemetry.registry), content_type=CONTENT_TYPE_LATEST)

    return telemetry
