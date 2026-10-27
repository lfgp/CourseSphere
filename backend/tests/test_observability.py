import importlib
import io
import json
import logging
import os
from pathlib import Path
import sys
import threading
import unittest
from unittest.mock import patch
from urllib.request import urlopen

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from observability import configure_observability, metrics_token_from_environment
from structured_logging import JSONFormatter


class ObservabilityConfigTests(unittest.TestCase):
    def test_production_requires_separate_metrics_secret_without_echoing_it(self):
        for token in ['', 'PRIVATE_SENTINEL', 'x' * 257, 'x' * 32 + '\n']:
            with patch.dict(os.environ, {'COURSESPHERE_LOCAL': '0', 'COURSESPHERE_METRICS_TOKEN': token}):
                with self.assertRaises(ValueError) as error:
                    metrics_token_from_environment()
                self.assertNotIn('PRIVATE_SENTINEL', str(error.exception))
        with patch.dict(os.environ, {'COURSESPHERE_LOCAL': '0', 'COURSESPHERE_METRICS_TOKEN': 'x' * 32}):
            self.assertEqual(metrics_token_from_environment(), 'x' * 32)

    def test_unsupported_multiprocess_mode_is_explicitly_rejected(self):
        from flask import Flask
        with patch.dict(os.environ, {'PROMETHEUS_MULTIPROC_DIR': 'unused'}):
            with self.assertRaisesRegex(RuntimeError, 'one process'):
                configure_observability(Flask('multiprocess-test'))

    def test_formatter_discards_messages_tracebacks_and_unlisted_fields(self):
        record = logging.LogRecord('test', logging.ERROR, '', 1, 'PRIVATE_SENTINEL %s', ('SECRET',), None)
        record.exc_text = 'PRIVATE_SENTINEL traceback'
        record.event_fields = {'password': 'PRIVATE_SENTINEL', 'status': 500}
        result = JSONFormatter().format(record)
        self.assertNotIn('PRIVATE_SENTINEL', result)
        self.assertNotIn('SECRET', result)
        self.assertEqual(json.loads(result)['status'], 500)


class ObservabilityAPITests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        with patch.dict(os.environ, {'COURSESPHERE_LOCAL': '1', 'COURSESPHERE_RATE_LIMIT_STORAGE_URI': 'memory://', 'COURSESPHERE_METRICS_TOKEN': ''}):
            cls.api = importlib.import_module('endpoints')

    def setUp(self):
        self.api.limiter.reset()
        self.client = self.api.app.test_client()
        self.telemetry = self.api.telemetry
        self.registry = self.telemetry.registry
        self.headers = {'Authorization': 'Bearer PRIVATE_TOKEN'}
        self.level = self.api.app.logger.level
        self.api.app.logger.setLevel(logging.CRITICAL)
        self.addCleanup(self.api.app.logger.setLevel, self.level)
        self.token_patch = patch.dict(self.api.app.config, {'COURSESPHERE_METRICS_TOKEN': ''})
        self.token_patch.start()
        self.addCleanup(self.token_patch.stop)
        self.verify_patch = patch.object(self.api.Firebase, 'verify_id_token', return_value={'uid': 'PRIVATE_UID'})
        self.verify = self.verify_patch.start()
        self.addCleanup(self.verify_patch.stop)
        self.profile_patch = patch.object(self.api.Firebase, 'get_user_info', return_value={'about': 'PRIVATE_PROFILE'})
        self.profile = self.profile_patch.start()
        self.addCleanup(self.profile_patch.stop)

    def sample(self, metric, **labels):
        return self.registry.get_sample_value('coursesphere_' + metric, labels) or 0

    def test_json_requests_and_auth_events_correlate_without_sensitive_data(self):
        stream = io.StringIO()
        handler = logging.StreamHandler(stream)
        handler.setFormatter(JSONFormatter())
        with patch.object(self.api.app.logger, 'handlers', [handler]):
            self.api.app.logger.setLevel(logging.INFO)
            response = self.client.get('/users/info', headers={**self.headers, 'X-Request-ID': 'ATTACKER_ID'})
            rejected = self.client.get('/PRIVATE_PATH?token=PRIVATE_QUERY')
        raw = stream.getvalue()
        for secret in ['PRIVATE_TOKEN', 'PRIVATE_UID', 'PRIVATE_PROFILE', 'PRIVATE_PATH', 'PRIVATE_QUERY', 'ATTACKER_ID']:
            self.assertNotIn(secret, raw)
        events = [json.loads(line) for line in raw.splitlines()]
        completed = [event for event in events if event['event'] == 'request_completed']
        self.assertEqual([event['status'] for event in completed], [200, 404])
        self.assertEqual(completed[0]['route'], '/users/info')
        self.assertEqual(completed[1]['route'], 'unmatched')
        self.assertEqual(completed[0]['request_id'], response.headers['X-Request-ID'])
        self.assertEqual(completed[1]['request_id'], rejected.headers['X-Request-ID'])
        self.assertNotEqual(completed[0]['request_id'], completed[1]['request_id'])
        self.assertEqual(events[0]['outcome'], 'success')
        self.assertEqual(events[0]['request_id'], completed[0]['request_id'])
        self.assertGreaterEqual(completed[0]['duration_ms'], 0)
        self.assertTrue(all(event['timestamp'].endswith('+00:00') for event in events))

    def test_error_authentication_is_distinguished_from_invalid_token(self):
        for failure, status, outcome, reason in [
            (ValueError('PRIVATE_SENTINEL'), 401, 'rejected', 'invalid_or_inactive'),
            (RuntimeError('PRIVATE_SENTINEL'), 503, 'error', 'provider_unavailable'),
        ]:
            with self.subTest(status=status):
                before = self.sample('auth_events_total', outcome=outcome, reason=reason)
                self.verify.side_effect = failure
                with self.assertLogs(self.api.app.logger, level='INFO') as captured:
                    response = self.client.get('/users/info', headers=self.headers)
                self.assertEqual(response.status_code, status)
                self.assertEqual(self.sample('auth_events_total', outcome=outcome, reason=reason) - before, 1)
                encoded = '\n'.join(JSONFormatter().format(record) for record in captured.records)
                self.assertNotIn('PRIVATE_SENTINEL', encoded)
                self.assertNotIn('PRIVATE_TOKEN', encoded)
                self.assertTrue(any(record.event_name == 'authentication' for record in captured.records))
        self.profile.assert_not_called()

    def test_counter_and_exact_slo_bucket_measure_seconds(self):
        labels = {'route': '/users/info', 'method': 'GET'}
        before_count = self.sample('http_requests_total', **labels, status='200')
        before_bucket = self.sample('http_request_duration_seconds_bucket', **labels, outcome='success', le='0.5')
        before_sum = self.sample('http_request_duration_seconds_sum', **labels, outcome='success')
        with patch('observability.perf_counter', side_effect=[10, 10.04, 10.25]), patch('endpoints.perf_counter', return_value=10.01):
            self.assertEqual(self.client.get('/users/info', headers=self.headers).status_code, 200)
        self.assertEqual(self.sample('http_requests_total', **labels, status='200') - before_count, 1)
        self.assertEqual(self.sample('http_request_duration_seconds_bucket', **labels, outcome='success', le='0.5') - before_bucket, 1)
        self.assertAlmostEqual(self.sample('http_request_duration_seconds_sum', **labels, outcome='success') - before_sum, .25)
        self.assertEqual(self.sample('http_requests_in_progress'), 0)

    def test_failure_is_counted_once_and_does_not_leak_or_leave_inflight_gauge(self):
        labels = {'route': '/users/info', 'method': 'GET', 'status': '500'}
        before_count = self.sample('http_requests_total', **labels)
        before_errors = self.sample('errors_total', kind='internal')
        self.profile.side_effect = RuntimeError('PRIVATE_SENTINEL')
        with self.assertLogs(self.api.app.logger, level='INFO') as captured:
            response = self.client.get('/users/info', headers=self.headers)
        self.assertEqual(response.status_code, 500)
        self.assertEqual(self.sample('http_requests_total', **labels) - before_count, 1)
        self.assertEqual(self.sample('errors_total', kind='internal') - before_errors, 1)
        encoded = '\n'.join(JSONFormatter().format(record) for record in captured.records)
        self.assertNotIn('PRIVATE_SENTINEL', encoded)
        self.assertEqual(sum(record.event_name == 'request_completed' for record in captured.records), 1)
        self.assertEqual(self.sample('http_requests_in_progress'), 0)

    def test_dynamic_routes_and_unknown_methods_have_bounded_labels(self):
        with patch.object(self.api.Firebase, 'delete_chat'):
            for index in range(5):
                self.assertEqual(self.client.delete(f'/chats/PRIVATE_CHAT_{index}', headers=self.headers).status_code, 200)
                self.client.open(f'/PRIVATE_PATH_{index}', method=f'PRIVATE_METHOD_{index}')
        data = self.client.get('/metrics').get_data(as_text=True)
        for secret in ['PRIVATE_CHAT_', 'PRIVATE_PATH_', 'PRIVATE_METHOD_', 'PRIVATE_TOKEN', 'PRIVATE_UID']:
            self.assertNotIn(secret, data)
        self.assertIn('route="/chats/<chat_id>"', data)
        self.assertIn('method="OTHER"', data)

    def test_health_and_metrics_are_exempt_and_do_not_pollute_request_slis(self):
        before = sum(sample.value for metric in self.registry.collect() for sample in metric.samples if sample.name == 'coursesphere_http_requests_total')
        from redis.exceptions import ConnectionError
        with patch.object(self.api.limiter.storage, 'acquire_entry', side_effect=ConnectionError('PRIVATE_SENTINEL')):
            for _ in range(125):
                health = self.client.get('/health')
                self.assertEqual(health.status_code, 200)
            self.assertEqual(health.json, {'status': 'ok', 'check': 'liveness'})
            self.assertEqual(self.client.get('/metrics').status_code, 200)
            self.assertEqual(self.client.options('/users/info').status_code, 200)
            self.assertEqual(self.client.get('/users/info', headers=self.headers).status_code, 503)
        after = sum(sample.value for metric in self.registry.collect() for sample in metric.samples if sample.name == 'coursesphere_http_requests_total')
        self.assertEqual(after - before, 1)  # Only the business request failed.
        self.verify.assert_not_called()
        self.profile.assert_not_called()

    def test_local_metrics_refuses_remote_peers_and_forwarded_header_bypass(self):
        response = self.client.get('/metrics', environ_base={'REMOTE_ADDR': '192.0.2.10'}, headers={'X-Forwarded-For': '127.0.0.1'})
        self.assertEqual(response.status_code, 401)
        self.assertNotIn('coursesphere_http_requests_total', response.get_data(as_text=True))

    def test_metrics_uses_dedicated_secret_and_prometheus_wire_format(self):
        from prometheus_client.parser import text_string_to_metric_families
        self.api.app.config['COURSESPHERE_METRICS_TOKEN'] = 's' * 32
        for value in ['', 'Bearer PRIVATE_TOKEN', 'Bearer ' + 's' * 33, 'Bearer ' + '\u00e9' * 32]:
            self.assertEqual(self.client.get('/metrics', headers={'Authorization': value}).status_code, 401)
        response = self.client.get('/metrics', headers={'Authorization': 'Bearer ' + 's' * 32})
        self.assertEqual(response.status_code, 200)
        self.assertIn('text/plain', response.content_type)
        self.assertIn('version=1.0.0', response.content_type)
        self.assertTrue(list(text_string_to_metric_families(response.get_data(as_text=True))))
        self.assertEqual(response.headers['Cache-Control'], 'no-store')
        self.verify.assert_not_called()

    def test_rate_limited_request_still_emits_completion_and_counter(self):
        for _ in range(120):
            self.client.get('/users/info', headers=self.headers)
        before = self.sample('http_requests_total', route='/users/info', method='GET', status='429')
        with self.assertLogs(self.api.app.logger, level='INFO') as captured:
            response = self.client.get('/users/info', headers=self.headers)
        self.assertEqual(response.status_code, 429)
        self.assertEqual(self.sample('http_requests_total', route='/users/info', method='GET', status='429') - before, 1)
        self.assertTrue(any(record.event_name == 'request_completed' and record.event_fields['status'] == 429 for record in captured.records))
        self.assertEqual(self.sample('http_requests_in_progress'), 0)

    def test_real_http_health_and_metrics(self):
        from werkzeug.serving import make_server
        server = make_server('127.0.0.1', 0, self.api.app)
        worker = threading.Thread(target=server.serve_forever, daemon=True)
        worker.start()
        try:
            base = f'http://127.0.0.1:{server.server_port}'
            with urlopen(base + '/health', timeout=5) as response:
                self.assertEqual(json.load(response)['check'], 'liveness')
            with urlopen(base + '/metrics', timeout=5) as response:
                self.assertIn(b'# TYPE coursesphere_http_requests_total counter', response.read())
        finally:
            server.shutdown()
            worker.join(timeout=5)
            server.server_close()


if __name__ == '__main__':
    unittest.main()
