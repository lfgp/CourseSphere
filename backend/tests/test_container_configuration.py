import os
from pathlib import Path
import runpy
import sys
from tempfile import TemporaryDirectory
import unittest
from unittest.mock import patch

BACKEND = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(BACKEND))

from observability import configure_observability, metrics_token_from_environment
from rate_limiting import storage_uri_from_environment
from serve import server_options


class ContainerConfigurationTests(unittest.TestCase):
    def test_metrics_secret_file_is_strict_and_never_echoes_path_or_contents(self):
        with TemporaryDirectory() as directory:
            secret = Path(directory) / 'PRIVATE_PATH.txt'
            with patch.dict(os.environ, {'COURSESPHERE_LOCAL': '1', 'COURSESPHERE_METRICS_TOKEN': '',
                                         'COURSESPHERE_METRICS_TOKEN_FILE': str(secret)}):
                secret.write_text('s' * 43 + '\n', encoding='utf-8')
                self.assertEqual(metrics_token_from_environment(), 's' * 43)
                for content in ['', 'PRIVATE_SENTINEL', 's' * 258, 's' * 43 + ' ' * 300]:
                    secret.write_text(content, encoding='utf-8')
                    with self.assertRaises(ValueError) as error:
                        metrics_token_from_environment()
                    self.assertNotIn('PRIVATE', str(error.exception))
                secret.unlink()
                with self.assertRaises(ValueError) as error:
                    metrics_token_from_environment()
                self.assertNotIn('PRIVATE', str(error.exception))

    def test_metrics_does_not_accept_ambiguous_secret_sources(self):
        with patch.dict(os.environ, {'COURSESPHERE_METRICS_TOKEN': 's' * 43,
                                     'COURSESPHERE_METRICS_TOKEN_FILE': 'PRIVATE_PATH'}):
            with self.assertRaisesRegex(ValueError, 'only one'):
                metrics_token_from_environment()

    def test_instance_identifier_cannot_inject_headers_or_sensitive_path(self):
        from flask import Flask
        for instance in ['bad\r\nX-Injected: yes', 'PRIVATE/USER', 'a' * 33, '']:
            with patch.dict(os.environ, {'COURSESPHERE_LOCAL': '1', 'COURSESPHERE_METRICS_TOKEN': '',
                                         'COURSESPHERE_METRICS_TOKEN_FILE': '', 'COURSESPHERE_INSTANCE_ID': instance}):
                with self.assertRaisesRegex(ValueError, 'INSTANCE_ID'):
                    configure_observability(Flask('invalid-instance-test'))

    def test_redis_unix_socket_is_supported_without_allowing_plaintext_remote_redis(self):
        with patch.dict(os.environ, {'COURSESPHERE_LOCAL': '0',
                                     'COURSESPHERE_RATE_LIMIT_STORAGE_URI': 'redis+unix:///run/redis/redis.sock'}):
            self.assertEqual(storage_uri_from_environment(), 'redis+unix:///run/redis/redis.sock')
        for uri in ['redis+unix://host/socket', 'redis+unix:///', 'redis+unix:///socket?db=0',
                    'redis+unix:///socket#fragment', 'redis://redis:6379/0']:
            with patch.dict(os.environ, {'COURSESPHERE_RATE_LIMIT_STORAGE_URI': uri}), self.assertRaises(ValueError):
                storage_uri_from_environment()

    def test_only_an_explicit_proxy_ip_can_supply_forwarding_headers(self):
        with patch.dict(os.environ, {'COURSESPHERE_TRUSTED_PROXY': ''}):
            self.assertNotIn('trusted_proxy', server_options())
        for invalid in ['*', 'gateway', '172.30.90.0/24', 'PRIVATE_SENTINEL']:
            with patch.dict(os.environ, {'COURSESPHERE_TRUSTED_PROXY': invalid}), self.assertRaises(ValueError):
                server_options()
        with patch.dict(os.environ, {'COURSESPHERE_TRUSTED_PROXY': '172.30.90.10'}):
            options = server_options()
            self.assertEqual(options['trusted_proxy'], '172.30.90.10')
            self.assertEqual(options['trusted_proxy_count'], 1)
            self.assertEqual(options['trusted_proxy_headers'], {'x-forwarded-for', 'x-forwarded-proto'})
            self.assertFalse(options['expose_tracebacks'])
            self.assertEqual(options['threads'], 4)

    def test_compose_emulator_hostname_requires_explicit_local_mode(self):
        with patch.dict(os.environ, {'COURSESPHERE_LOCAL': '1', 'COURSESPHERE_EMULATOR_HOST': 'firebase-emulators'}):
            with patch('firebase_admin.initialize_app'):
                runpy.run_path(str(BACKEND / 'firebase.py'))
            self.assertEqual(os.environ['FIREBASE_AUTH_EMULATOR_HOST'], 'firebase-emulators:9099')
            self.assertEqual(os.environ['FIREBASE_DATABASE_EMULATOR_HOST'], 'firebase-emulators:9000')
        with patch.dict(os.environ, {'COURSESPHERE_LOCAL': '1', 'COURSESPHERE_EMULATOR_HOST': 'untrusted.example'}):
            with self.assertRaisesRegex(ValueError, 'emulator host'):
                runpy.run_path(str(BACKEND / 'firebase.py'))


if __name__ == '__main__':
    unittest.main()
