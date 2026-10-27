import importlib
import logging
import os
from pathlib import Path
import sys
import time
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / 'backend'))

from rate_limiting import storage_uri_from_environment


class RateLimitConfigurationTests(unittest.TestCase):
    def test_memory_is_only_allowed_in_explicit_local_mode(self):
        with patch.dict(os.environ, {'COURSESPHERE_LOCAL': '1', 'COURSESPHERE_RATE_LIMIT_STORAGE_URI': ''}):
            self.assertEqual(storage_uri_from_environment(), 'memory://')
        for uri in ['', 'memory://', 'http://cache.example', 'redis://cache.example:6379/0']:
            with self.subTest(uri=uri), patch.dict(os.environ, {
                'COURSESPHERE_LOCAL': '0', 'COURSESPHERE_RATE_LIMIT_STORAGE_URI': uri,
            }), self.assertRaises(ValueError):
                storage_uri_from_environment()

    def test_shared_storage_and_tls_are_supported_without_echoing_credentials(self):
        for uri in ['redis://127.0.0.1:6379/0', 'rediss://cache.example:6379/0']:
            with patch.dict(os.environ, {'COURSESPHERE_LOCAL': '0', 'COURSESPHERE_RATE_LIMIT_STORAGE_URI': uri}):
                self.assertEqual(storage_uri_from_environment(), uri)
        with patch.dict(os.environ, {
            'COURSESPHERE_LOCAL': '0', 'COURSESPHERE_RATE_LIMIT_STORAGE_URI': 'invalid://PRIVATE_SENTINEL@cache',
        }), self.assertRaises(ValueError) as error:
            storage_uri_from_environment()
        self.assertNotIn('PRIVATE_SENTINEL', str(error.exception))


class RateLimitingTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        with patch.dict(os.environ, {'COURSESPHERE_LOCAL': '1', 'COURSESPHERE_RATE_LIMIT_STORAGE_URI': 'memory://'}):
            cls.api = importlib.import_module('endpoints')

    def setUp(self):
        self.api.limiter.reset()
        self.client = self.api.app.test_client()
        self.headers = {'Authorization': 'Bearer token-alice'}
        previous_level = self.api.app.logger.level
        self.api.app.logger.setLevel(logging.CRITICAL)
        self.addCleanup(self.api.app.logger.setLevel, previous_level)
        verify = patch.object(self.api.Firebase, 'verify_id_token', side_effect=lambda token: {'uid': token.removeprefix('token-')})
        self.verify = verify.start()
        self.addCleanup(verify.stop)
        profile = patch.object(self.api.Firebase, 'get_user_info', return_value={})
        self.profile = profile.start()
        self.addCleanup(profile.stop)
        config = patch.dict(self.api.app.config, {'COURSESPHERE_QUERY_LIMIT': '2 per minute'})
        config.start()
        self.addCleanup(config.stop)

    def query(self, headers=None, ip='127.0.0.1'):
        return self.client.post('/users/query', json={'query': 'CS 1110'}, headers=headers or self.headers,
                                environ_overrides={'REMOTE_ADDR': ip})

    def test_query_quota_blocks_before_profile_or_query_processing(self):
        self.assertEqual(self.query().status_code, 200)
        self.assertEqual(self.query().status_code, 200)
        self.profile.reset_mock()
        response = self.query()
        self.assertEqual(response.status_code, 429)
        self.assertEqual(response.json['error'], 'Too many requests')
        self.assertGreater(int(response.headers['Retry-After']), 0)
        self.assertEqual(response.headers['Cache-Control'], 'no-store')
        self.assertEqual(response.headers['X-Request-ID'], response.json['request_id'])
        self.profile.assert_not_called()

    def test_user_quota_is_independent_of_ip_and_of_other_users(self):
        self.assertEqual(self.query(ip='192.0.2.1').status_code, 200)
        self.assertEqual(self.query(ip='192.0.2.2').status_code, 200)
        self.assertEqual(self.query(ip='192.0.2.3').status_code, 429)
        self.assertEqual(self.query(headers={'Authorization': 'Bearer token-bob'}).status_code, 200)

    def test_all_endpoints_share_ip_quota_and_headers_cannot_spoof_it(self):
        for index in range(120):
            endpoint = '/users/info' if index % 2 else '/hash'
            response = self.client.open(endpoint, method='GET' if index % 2 else 'POST',
                                        json={}, headers={'X-Forwarded-For': f'192.0.2.{index}'})
            self.assertEqual(response.status_code, 401)
        self.assertEqual(self.client.get('/users/info', headers=self.headers).status_code, 429)
        self.assertEqual(self.query(ip='198.51.100.1').status_code, 200)
        self.assertEqual(self.verify.call_count, 1)  # Only the permitted request reaches token verification.

    def test_cors_preflight_does_not_consume_quota(self):
        for _ in range(121):
            response = self.client.options('/users/info', headers={
                'Origin': 'http://localhost:5173', 'Access-Control-Request-Method': 'GET',
            })
            self.assertEqual(response.status_code, 200)
        self.assertEqual(self.client.get('/users/info', headers=self.headers).status_code, 200)

    def test_query_quota_recovers_after_window_expires_without_sleep(self):
        self.query()
        self.query()
        self.assertEqual(self.query().status_code, 429)
        future = time.time() + 61
        with patch('limits.storage.memory.time.time', return_value=future):
            self.assertEqual(self.query().status_code, 200)

    def test_storage_failure_denies_request_without_exposing_connection_details(self):
        from redis.exceptions import ConnectionError
        self.profile.reset_mock()
        with patch.object(self.api.limiter.storage, 'acquire_entry', side_effect=ConnectionError('PRIVATE_SENTINEL')):
            with self.assertLogs(self.api.app.logger, level='ERROR') as logs:
                response = self.client.get('/users/info', headers=self.headers)
        self.assertEqual(response.status_code, 503)
        self.assertEqual(response.headers['Retry-After'], '5')
        self.assertNotIn('PRIVATE_SENTINEL', response.get_data(as_text=True) + '\n'.join(logs.output))
        self.profile.assert_not_called()


if __name__ == '__main__':
    unittest.main()
