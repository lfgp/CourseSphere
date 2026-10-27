import importlib
import json
import logging
import os
from pathlib import Path
import runpy
import sys
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / 'backend'))


class APISecurityTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        with patch.dict(os.environ, {'COURSESPHERE_LOCAL': '1', 'COURSESPHERE_RATE_LIMIT_STORAGE_URI': 'memory://'}):
            cls.api = importlib.import_module('endpoints')

    def setUp(self):
        self.api.limiter.reset()
        previous_level = self.api.app.logger.level
        self.api.app.logger.setLevel(logging.CRITICAL)
        self.addCleanup(self.api.app.logger.setLevel, previous_level)
        self.client = self.api.app.test_client()
        self.headers = {'Authorization': 'Bearer test-token'}
        self.verify_patch = patch.object(self.api.Firebase, 'verify_id_token', return_value={'uid': 'alice'})
        self.verify = self.verify_patch.start()
        self.addCleanup(self.verify_patch.stop)
        self.profile_patch = patch.object(self.api.Firebase, 'get_user_info', return_value={'about': 'Private profile'})
        self.profile = self.profile_patch.start()
        self.addCleanup(self.profile_patch.stop)

    def test_every_private_endpoint_requires_bearer_token(self):
        for method, url in [('get', '/users/info'), ('post', '/users/info'), ('post', '/users/query'),
                            ('post', '/hash'), ('post', '/chats/chat/messages'), ('delete', '/chats/chat')]:
            for header in ('', 'Basic token', 'Bearer', 'xBearer test-token', 'Bearer a b'):
                with self.subTest(method=method, url=url, header=header):
                    response = getattr(self.client, method)(url, json={}, headers={'Authorization': header})
                    self.assertEqual(response.status_code, 401)
                    self.assertEqual(response.headers['WWW-Authenticate'], 'Bearer')
        self.profile.assert_not_called()

    def test_invalid_revoked_and_disabled_tokens_fail_closed(self):
        for error in [ValueError('invalid'), self.api.auth.RevokedIdTokenError('revoked'),
                      self.api.auth.UserDisabledError('disabled')]:
            self.verify.side_effect = error
            response = self.client.post('/users/query', json={'query': 'courses'}, headers=self.headers)
            self.assertEqual(response.status_code, 401)
        self.profile.assert_not_called()

    def test_sdk_checks_revocation(self):
        self.verify_patch.stop()
        with patch.object(self.api.auth, 'verify_id_token', return_value={'uid': 'alice'}) as verify_sdk:
            self.api.Firebase.verify_id_token('test-token')
        verify_sdk.assert_called_once_with('test-token', check_revoked=True)

    def test_credentials_in_url_or_body_cannot_authenticate(self):
        self.assertEqual(self.client.get('/users/info?id_token=test-token').status_code, 401)
        self.assertEqual(self.client.post('/users/query', json={'query': 'courses', 'id_token': 'test-token'}).status_code, 401)
        self.assertEqual(self.client.get('/users/info?id_token=test-token', headers=self.headers).status_code, 400)

    def test_query_uses_verified_identity(self):
        response = self.client.post('/users/query', json={'query': 'courses'}, headers=self.headers)
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json['botResponse'], 'Fake implementation')
        self.profile.assert_called_once_with('alice')

    def test_public_admin_signup_is_removed(self):
        with patch.object(self.api.Firebase, 'create_user') as create:
            response = self.client.post('/users/create', json={'email': 'someone@example.test', 'password': 'test'})
        self.assertEqual(response.status_code, 404)
        create.assert_not_called()

    def test_database_failure_does_not_fall_back_to_anonymous_query(self):
        self.profile.side_effect = RuntimeError('database unavailable')
        with patch.object(self.api, 'QueryManager') as manager:
            response = self.client.post('/users/query', json={'query': 'courses'}, headers=self.headers)
        self.assertEqual(response.status_code, 500)
        manager.assert_not_called()

    def test_profile_is_scoped_to_verified_uid_and_rejects_mass_assignment(self):
        with patch.object(self.api.Firebase, 'set_user_info') as save:
            response = self.client.post('/users/info', json={'about': 'hello'}, headers=self.headers)
            self.assertEqual(response.status_code, 200)
            self.assertEqual(save.call_args.args[0], 'alice')
            save.reset_mock()
            for data in [{'uid': 'bob', 'about': 'overwrite'}, {'admin': True}, {'about': {'nested': True}}, {'courses': 'CS'}]:
                self.assertEqual(self.client.post('/users/info', json=data, headers=self.headers).status_code, 400)
            save.assert_not_called()

    def test_json_type_content_type_and_size_are_validated(self):
        for payload in [[], None, 'text', 3, {'query': []}, {'query': ''}, {'query': 'x' * 8001}]:
            response = self.client.post('/users/query', data=json.dumps(payload), content_type='application/json', headers=self.headers)
            self.assertEqual(response.status_code, 400)
        self.assertEqual(self.client.post('/users/query', data='broken', content_type='application/json', headers=self.headers).status_code, 400)
        self.assertEqual(self.client.post('/users/query', data='text', headers=self.headers).status_code, 415)
        self.assertEqual(self.client.post('/users/query', json={'query': 'x' * 300000}, headers=self.headers).status_code, 413)

    def test_error_responses_and_logs_do_not_contain_secrets(self):
        secret = 'PRIVATE_SENTINEL'
        self.profile.side_effect = RuntimeError(secret)
        with self.assertLogs(self.api.app.logger, level='ERROR') as logs:
            response = self.client.get('/users/info', headers={'Authorization': f'Bearer {secret}'})
        self.assertEqual(response.status_code, 500)
        self.assertNotIn(secret, response.get_data(as_text=True) + '\n'.join(logs.output))
        self.assertNotIn('Traceback', response.get_data(as_text=True))
        self.assertEqual(response.headers['Cache-Control'], 'no-store')
        self.assertEqual(response.headers['X-Content-Type-Options'], 'nosniff')
        self.assertEqual(response.headers['X-Request-ID'], response.json['request_id'])

    def test_rejected_auth_is_logged_without_token(self):
        self.verify.side_effect = ValueError('PRIVATE_SENTINEL')
        with self.assertLogs(self.api.app.logger, level='WARNING') as logs:
            response = self.client.get('/users/info', headers=self.headers)
        self.assertEqual(response.status_code, 401)
        self.assertTrue(any(record.event_name == 'request_rejected' for record in logs.records))
        self.assertNotIn('PRIVATE_SENTINEL', '\n'.join(logs.output))
        self.assertNotIn('test-token', '\n'.join(logs.output))

    def test_cors_only_allows_exact_local_origins(self):
        for origin, permitted in [('https://untrusted.example', False), ('http://localhost:5173.evil.example', False),
                                  ('http://localhost:5173', True), ('http://127.0.0.1:5173', True)]:
            response = self.client.options('/users/info', headers={'Origin': origin, 'Access-Control-Request-Method': 'POST'})
            self.assertEqual(response.headers.get('Access-Control-Allow-Origin'), origin if permitted else None)

    def test_production_cors_defaults_to_same_origin_and_rejects_wildcards(self):
        with patch.dict(os.environ, {'COURSESPHERE_LOCAL': '0', 'COURSESPHERE_ALLOWED_ORIGINS': ''}):
            self.assertEqual(self.api.allowed_origins(), [])
        for value in ['*', 'https://*.example.test', 'http://example.test', 'https://example.test/path']:
            with patch.dict(os.environ, {'COURSESPHERE_ALLOWED_ORIGINS': value}), self.assertRaises(ValueError):
                self.api.allowed_origins()

    def test_chat_validation_happens_before_any_write(self):
        valid = {'sender': 'user', 'content': 'Hello', 'messageID': 'safe-id'}
        with patch.object(self.api.Firebase, 'save_chat') as save:
            for messages in [[valid, 'invalid'], [valid, {**valid, 'sender': 'admin'}], [{**valid, 'messageID': {}}], [valid] * 101]:
                self.assertEqual(self.client.post('/chats/chat/messages', json={'messages': messages}, headers=self.headers).status_code, 400)
            save.assert_not_called()
            response = self.client.post('/chats/chat/messages', json={'messages': [valid]}, headers=self.headers)
            self.assertEqual(response.status_code, 200)
            save.assert_called_once_with('alice', 'chat', [valid])

    def test_privileged_chat_storage_enforces_user_paths_and_batch_validation(self):
        valid = {'sender': 'user', 'content': 'Hello', 'messageID': 'safe-id'}
        with patch('firebase.db.reference') as reference:
            with self.assertRaises(ValueError):
                self.api.Firebase.save_chat('alice', 'chat', [valid, 'bad'])
            with self.assertRaises(ValueError):
                self.api.Firebase.delete_chat('alice', '../bob')
            reference.assert_not_called()
            self.api.Firebase.save_chat('alice', 'chat', [valid])
            reference.assert_called_once_with('users/alice/chats/chat/messages')

    def test_chat_deletion_uses_current_user(self):
        with patch.object(self.api.Firebase, 'delete_chat') as delete:
            self.assertEqual(self.client.delete('/chats/chat', headers=self.headers).status_code, 200)
            delete.assert_called_once_with('alice', 'chat')

    def test_message_ids_are_fixed_length_database_safe_and_distinct(self):
        ids = {self.client.post('/hash', json='message', headers=self.headers).json['messageID'] for _ in range(10)}
        self.assertEqual(len(ids), 10)
        for value in ids:
            self.assertRegex(value, r'^[0-9a-f]{64}$')



class ProductionConfigSecurityTests(unittest.TestCase):
    def test_import_refuses_unsigned_emulator_tokens_in_production(self):
        for variable in ['FIREBASE_AUTH_EMULATOR_HOST', 'FIREBASE_DATABASE_EMULATOR_HOST']:
            with patch.dict(os.environ, {'COURSESPHERE_LOCAL': '0', variable: '127.0.0.1:9099'}):
                with self.assertRaisesRegex(RuntimeError, 'forbidden'):
                    runpy.run_path(str(ROOT / 'backend/firebase.py'))


if __name__ == '__main__':
    unittest.main()
