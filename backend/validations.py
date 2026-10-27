"""Validation shared by HTTP handlers and privileged database writes."""
import json
import re


def validate_record(value, fields):
    if not isinstance(value, dict) or set(value) - fields:
        raise ValueError('Invalid object fields')
    return value


def validate_text(value, limit, required=False):
    if not isinstance(value, str) or len(value) > limit or (required and not value.strip()):
        raise ValueError('Invalid text')
    return value


def validate_key(value):
    # Firebase UIDs may contain Unicode and punctuation, but never path separators.
    if not isinstance(value, str) or not 1 <= len(value) <= 128 or re.search(r'[.#$\[\]/\x00-\x1f\x7f]', value):
        raise ValueError('Invalid database key')
    return value


def validate_profile(data):
    validate_record(data, {'majors', 'minors', 'courses', 'college', 'year', 'about'})
    profile = {}
    for field, limit in [('majors', 30), ('minors', 30), ('courses', 200)]:
        values = data.get(field, [])
        if not isinstance(values, list) or len(values) > limit:
            raise ValueError('Invalid profile list')
        profile[field] = [validate_text(value, 128, required=True) for value in values]
    for field, limit in [('college', 200), ('year', 16), ('about', 4000)]:
        profile[field] = validate_text(data.get(field, ''), limit)
    return profile


def validate_messages(messages):
    if not isinstance(messages, list) or not 1 <= len(messages) <= 100:
        raise ValueError('Invalid message batch')
    for message in messages:
        validate_record(message, {'sender', 'content', 'messageID', 'timestamp'})
        if message.get('sender') not in ('user', 'bot'):
            raise ValueError('Invalid sender')
        validate_key(message.get('messageID'))
        if 'timestamp' in message:
            validate_text(message['timestamp'], 40, required=True)
        content = message.get('content')
        if isinstance(content, str):
            validate_text(content, 16000, required=True)
        elif isinstance(content, dict) and message['sender'] == 'bot':
            validate_record(content, {'botResponse', 'newRecommendations'})
            validate_text(content.get('botResponse'), 16000)
            recommendations = content.get('newRecommendations', [])
            if not isinstance(recommendations, list) or len(recommendations) > 100:
                raise ValueError('Invalid recommendations')
            if len(json.dumps(content, allow_nan=False).encode('utf-8')) > 64000:
                raise ValueError('Message content too large')
            def check_keys(value, depth=0):
                if depth > 12:
                    raise ValueError('Message nesting too deep')
                if isinstance(value, dict):
                    for key, child in value.items():
                        validate_key(key)
                        check_keys(child, depth + 1)
                elif isinstance(value, list):
                    for child in value:
                        check_keys(child, depth + 1)
            check_keys(content)
        else:
            raise ValueError('Invalid content')
    return messages
