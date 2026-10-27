import importlib
import logging
import os
from pathlib import Path
import sys
import unittest
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))


class SecurityHeadersTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        with patch.dict(os.environ, {'COURSESPHERE_LOCAL': '1', 'COURSESPHERE_RATE_LIMIT_STORAGE_URI': 'memory://'}):
            cls.api = importlib.import_module('endpoints')

    def setUp(self):
        self.api.limiter.reset()
        self.client = self.api.app.test_client()
        self.headers = {'Authorization': 'Bearer test-token'}
        previous_level = self.api.app.logger.level
        self.api.app.logger.setLevel(logging.CRITICAL)
        self.addCleanup(self.api.app.logger.setLevel, previous_level)
        verify = patch.object(self.api.Firebase, 'verify_id_token', return_value={'uid': 'alice'})
        verify.start()
        self.addCleanup(verify.stop)
        profile = patch.object(self.api.Firebase, 'get_user_info', return_value={})
        self.profile = profile.start()
        self.addCleanup(profile.stop)

    def assert_security_headers(self, response):
        self.assertEqual(response.headers['X-Frame-Options'], 'DENY')
        self.assertEqual(response.headers['X-Content-Type-Options'], 'nosniff')
        self.assertEqual(response.headers['Cache-Control'], 'no-store')
        self.assertEqual(response.headers['Referrer-Policy'], 'no-referrer')
        self.assertIn("default-src 'none'", response.headers['Content-Security-Policy'])
        self.assertIn("frame-ancestors 'none'", response.headers['Content-Security-Policy'])
        self.assertEqual(response.headers['Permissions-Policy'], 'camera=(), microphone=(), geolocation=()')

    def test_policy_applies_to_success_and_client_error_responses(self):
        responses = [self.client.get('/users/info', headers=self.headers),
                     self.client.get('/users/info'), self.client.get('/unknown'),
                     self.client.post('/users/query', json=[], headers=self.headers),
                     self.client.put('/users/info', json={}, headers=self.headers)]
        self.assertEqual([response.status_code for response in responses], [200, 401, 404, 400, 405])
        for response in responses:
            self.assert_security_headers(response)

    def test_policy_applies_to_rate_limit_and_internal_errors(self):
        self.profile.side_effect = RuntimeError('PRIVATE_SENTINEL')
        response = self.client.get('/users/info', headers=self.headers)
        self.assertEqual(response.status_code, 500)
        self.assert_security_headers(response)
        self.profile.side_effect = None
        with patch.dict(self.api.app.config, {'COURSESPHERE_QUERY_LIMIT': '1 per minute'}):
            self.client.post('/users/query', json={'query': 'courses'}, headers=self.headers)
            response = self.client.post('/users/query', json={'query': 'courses'}, headers=self.headers)
        self.assertEqual(response.status_code, 429)
        self.assert_security_headers(response)

    def test_hsts_is_only_sent_on_https(self):
        secure = self.client.get('/users/info', base_url='https://localhost', headers=self.headers)
        self.assertEqual(secure.headers['Strict-Transport-Security'], 'max-age=31536000')
        insecure = self.client.get('/users/info', base_url='http://localhost', headers={
            **self.headers, 'X-Forwarded-Proto': 'https',
        })
        self.assertNotIn('Strict-Transport-Security', insecure.headers)


if __name__ == '__main__':
    unittest.main()
