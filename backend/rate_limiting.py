"""Request quotas with a local development store and a shared production store."""
import hashlib
import os
from urllib.parse import urlsplit

from flask import g, request
from flask_limiter import Limiter
from observability import PROBE_ENDPOINTS


def storage_uri_from_environment():
    local = os.environ.get('COURSESPHERE_LOCAL') == '1'
    uri = os.environ.get('COURSESPHERE_RATE_LIMIT_STORAGE_URI', '').strip()
    if local and not uri:
        return 'memory://'
    if local and uri == 'memory://':
        return uri
    try:
        url = urlsplit(uri)
        url.port  # Validate malformed ports without echoing the URI on failure.
    except ValueError:
        raise ValueError('Invalid rate-limit storage configuration.') from None
    if url.scheme == 'redis+unix':
        if url.netloc or not url.path.startswith('/') or url.path == '/' or url.query or url.fragment:
            raise ValueError('Redis Unix storage requires an absolute socket path without authority or query.')
        return uri
    if url.scheme not in {'redis', 'rediss'} or not url.hostname or url.fragment:
        raise ValueError('Set COURSESPHERE_RATE_LIMIT_STORAGE_URI to a shared Redis URL; memory:// is local-only.')
    if url.scheme == 'redis' and url.hostname not in {'localhost', '127.0.0.1', '::1'}:
        raise ValueError('Remote rate-limit storage requires rediss:// (TLS).')
    return uri


def client_ip_key():
    # Never trust X-Forwarded-For supplied by a client. No ProxyFix is enabled.
    return 'ip:' + hashlib.sha256((request.remote_addr or 'unknown').encode()).hexdigest()


def authenticated_user_key():
    return 'uid:' + hashlib.sha256(g.uid.encode()).hexdigest()


def configure_rate_limiting(app):
    uri = storage_uri_from_environment()
    app.config.setdefault('COURSESPHERE_QUERY_LIMIT', '20 per minute')
    return Limiter(
        client_ip_key,
        app=app,
        default_limits=[],
        application_limits=['120 per minute'],
        application_limits_exempt_when=lambda: request.method == 'OPTIONS' or request.endpoint in PROBE_ENDPOINTS,
        storage_uri=uri,
        storage_options={'socket_connect_timeout': 1, 'socket_timeout': 1} if uri != 'memory://' else {},
        strategy='moving-window',
        headers_enabled=True,
        retry_after='delta-seconds',
        key_prefix='coursesphere:v1',
        swallow_errors=False,
        in_memory_fallback_enabled=False,
    )
