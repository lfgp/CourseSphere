"""JSON application events with an explicit allowlist; never serialize raw messages."""
import json
import logging
import sys
from datetime import datetime, timezone

from flask import g, has_request_context, request

FIELDS = {'request_id', 'method', 'route', 'status', 'duration_ms', 'outcome', 'reason', 'kind', 'mode'}
METHODS = {'GET', 'POST', 'DELETE', 'PUT', 'PATCH', 'HEAD', 'OPTIONS'}


def request_context():
    if not has_request_context():
        return {}
    return {
        'request_id': getattr(g, 'request_id', None),
        'method': request.method if request.method in METHODS else 'OTHER',
        'route': request.url_rule.rule if request.url_rule else 'unmatched',
    }


class JSONFormatter(logging.Formatter):
    def format(self, record):
        payload = {
            'timestamp': datetime.fromtimestamp(record.created, timezone.utc).isoformat(timespec='milliseconds'),
            'level': record.levelname,
            'service': 'coursesphere-api',
            'event': getattr(record, 'event_name', 'runtime_message_suppressed'),
        }
        # Neither getMessage(), exc_info nor arbitrary extra fields enter the output.
        payload.update({key: value for key, value in getattr(record, 'event_fields', {}).items() if key in FIELDS})
        return json.dumps(payload, ensure_ascii=True, allow_nan=False, separators=(',', ':'))


def configure_logging(app):
    handler = logging.StreamHandler(sys.stdout)
    handler.setFormatter(JSONFormatter())
    for logger in (app.logger, logging.getLogger('werkzeug')):
        logger.handlers.clear()
        logger.addHandler(handler)
        logger.setLevel(logging.INFO if logger is app.logger else logging.WARNING)
        logger.propagate = False


def log_event(app, event, level=logging.INFO, **fields):
    app.logger.log(level, event, extra={'event_name': event, 'event_fields': {**request_context(), **fields}})
