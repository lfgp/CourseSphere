"""Headers for the JSON API; the SPA has its own document policy."""
from flask import request


def apply_security_headers(response):
    response.headers['Cache-Control'] = 'no-store'
    response.headers['X-Content-Type-Options'] = 'nosniff'
    response.headers['X-Frame-Options'] = 'DENY'
    response.headers['Referrer-Policy'] = 'no-referrer'
    response.headers['Permissions-Policy'] = 'camera=(), microphone=(), geolocation=()'
    response.headers['Content-Security-Policy'] = "default-src 'none'; frame-ancestors 'none'; base-uri 'none'; form-action 'none'"
    # No includeSubDomains/preload, and no trust in arbitrary X-Forwarded-Proto headers.
    if request.is_secure:
        response.headers['Strict-Transport-Security'] = 'max-age=31536000'
    return response
