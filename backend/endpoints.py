import argparse
import os
import re
import secrets
from functools import wraps
from time import perf_counter
from urllib.parse import urlsplit

if __name__ == '__main__':
    parser = argparse.ArgumentParser(description='CourseSphere API')
    mode = parser.add_mutually_exclusive_group()
    mode.add_argument('--local', dest='local', action='store_true', help='Use local Firebase emulators without credentials (default)')
    mode.add_argument('--firebase', dest='local', action='store_false', help='Use a real Firebase project with service account credentials')
    parser.set_defaults(local=True)
    local_mode = parser.parse_args().local
    os.environ['COURSESPHERE_LOCAL'] = '1' if local_mode else '0'
    if not local_mode:
        os.environ.pop('FIREBASE_AUTH_EMULATOR_HOST', None)
        os.environ.pop('FIREBASE_DATABASE_EMULATOR_HOST', None)

from flask import Flask, g, jsonify, request
from flask_cors import CORS
from firebase_admin import auth
from werkzeug.exceptions import BadRequest, HTTPException, ServiceUnavailable, Unauthorized
from limits.errors import StorageError
from redis.exceptions import RedisError

from firebase import Firebase
from query_manager import QueryManager
from observability import configure_observability
from rate_limiting import authenticated_user_key, configure_rate_limiting
from security_headers import apply_security_headers
from structured_logging import log_event
from validation import validate_messages, validate_profile, validate_record, validate_text, validate_key

app = Flask(__name__)
app.config['MAX_CONTENT_LENGTH'] = 256 * 1024


def allowed_origins():
    defaults = 'http://localhost:5173,http://127.0.0.1:5173' if os.environ.get('COURSESPHERE_LOCAL') == '1' else ''
    origins = [origin.strip() for origin in os.environ.get('COURSESPHERE_ALLOWED_ORIGINS', defaults).split(',') if origin.strip()]
    for origin in origins:
        url = urlsplit(origin)
        local_http = url.scheme == 'http' and url.hostname in {'localhost', '127.0.0.1', '::1'}
        if (url.scheme != 'https' and not local_http) or not url.hostname or '*' in origin or url.path or url.query or url.fragment or url.username or url.password:
            raise ValueError('COURSESPHERE_ALLOWED_ORIGINS must contain exact HTTPS origins (HTTP only on loopback).')
    return origins


CORS(app, origins=[re.compile(r'\A' + re.escape(origin) + r'\Z') for origin in allowed_origins()], methods=['GET', 'POST', 'DELETE'],
     allow_headers=['Authorization', 'Content-Type'], supports_credentials=False)


telemetry = configure_observability(app)
limiter = configure_rate_limiting(app)


@app.after_request
def secure_response(response):
    apply_security_headers(response)
    response.headers['X-Request-ID'] = g.request_id
    response.headers['X-Backend-Instance'] = app.config['COURSESPHERE_INSTANCE_ID']
    return response


@app.errorhandler(HTTPException)
def handle_http_error(error):
    messages = {400: 'Invalid request', 401: 'Authentication required', 403: 'Access denied',
                404: 'Not found', 405: 'Method not allowed', 413: 'Request too large',
                415: 'Content-Type must be application/json', 429: 'Too many requests',
                503: 'Service temporarily unavailable'}
    telemetry.error(app, 'request_rejected', 'http', error.code)
    response = error.get_response()
    response.data = app.json.dumps({'error': messages.get(error.code, 'Request rejected'), 'request_id': g.request_id})
    response.content_type = 'application/json'
    if error.code == 401:
        response.headers['WWW-Authenticate'] = 'Bearer'
    return response


@app.errorhandler(ValueError)
def handle_validation_error(error):
    return handle_http_error(BadRequest())


@app.errorhandler(Exception)
def handle_internal_error(error):
    # Never record exception messages, tokens, passwords, query strings or bodies.
    telemetry.error(app, 'request_failed', 'internal', 500)
    return jsonify({'error': 'Internal server error', 'request_id': g.request_id}), 500


@app.errorhandler(StorageError)
@app.errorhandler(RedisError)
def handle_rate_limit_storage_error(error):
    telemetry.error(app, 'rate_limit_storage_unavailable', 'rate_limit_storage', 503)
    response = jsonify({'error': 'Service temporarily unavailable', 'request_id': g.request_id})
    response.headers['Retry-After'] = '5'
    return response, 503


def require_auth(view):
    @wraps(view)
    def authenticated(*args, **kwargs):
        started = perf_counter()
        parts = request.headers.get('Authorization', '').split()
        if len(parts) != 2 or parts[0].lower() != 'bearer' or len(parts[1]) > 8192:
            telemetry.authentication(app, 'rejected', 'missing_or_malformed', started)
            raise Unauthorized()
        try:
            token = Firebase.verify_id_token(parts[1])
            uid = token.get('uid')
            validate_key(uid)
        except (ValueError, auth.InvalidIdTokenError, auth.RevokedIdTokenError, auth.UserDisabledError, auth.UserNotFoundError):
            telemetry.authentication(app, 'rejected', 'invalid_or_inactive', started)
            raise Unauthorized() from None
        except Exception:
            telemetry.authentication(app, 'error', 'provider_unavailable', started)
            raise ServiceUnavailable() from None
        g.uid = uid
        telemetry.authentication(app, 'success', 'verified', started)
        return view(*args, **kwargs)
    return authenticated


def json_record(allowed_fields):
    data = request.get_json()
    validate_record(data, allowed_fields)
    return data


# Account registration belongs to the Firebase client SDK, never public Admin provisioning.
@app.route('/users/info', methods=['POST'])
@require_auth
def set_user_info():
    data = json_record({'majors', 'minors', 'courses', 'college', 'year', 'about'})
    profile = validate_profile(data)
    Firebase.set_user_info(g.uid, profile)
    return jsonify({'message': 'User info set successfully', 'uid': g.uid})


@app.route('/users/info', methods=['GET'])
@require_auth
def get_user_info():
    if request.args:
        raise BadRequest()
    return jsonify(Firebase.get_user_info(g.uid) or {})


@app.route('/users/query', methods=['POST'])
@require_auth
def get_user_query():
    data = json_record({'query'})
    query = validate_text(data.get('query'), 8000, required=True)
    # This block runs after require_auth: no client-supplied UID or token string is the quota key.
    with limiter.limit(app.config['COURSESPHERE_QUERY_LIMIT'], key_func=authenticated_user_key):
        user_info = Firebase.get_user_info(g.uid)
        result = QueryManager(query, user_info).response
    if isinstance(result, str):
        result = {'botResponse': result, 'newRecommendations': []}
    return jsonify(result)


@app.route('/hash', methods=['POST'])
@require_auth
def generate_message_id():
    request.get_json()  # Enforce JSON and the global body size limit.
    return jsonify({'messageID': secrets.token_hex(32)})


@app.route('/chats/<chat_id>/messages', methods=['POST'])
@require_auth
def save_chat(chat_id):
    validate_key(chat_id)
    data = json_record({'messages'})
    messages = validate_messages(data.get('messages'))
    Firebase.save_chat(g.uid, chat_id, messages)
    return jsonify({'message': 'Messages saved successfully'})


@app.route('/chats/<chat_id>', methods=['DELETE'])
@require_auth
def delete_chat(chat_id):
    validate_key(chat_id)
    Firebase.delete_chat(g.uid, chat_id)
    return jsonify({'message': 'Message deleted successfully'})


if __name__ == '__main__':
    log_event(app, 'application_started', mode='local mode' if local_mode else 'firebase')
    app.run(host='127.0.0.1', debug=False)
