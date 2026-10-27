import json
import os
from pathlib import Path
import runpy
import subprocess
import sys
import unittest
from unittest.mock import patch
from urllib.error import HTTPError
from urllib.request import Request, urlopen
from uuid import uuid4

import firebase_admin


BACKEND_DIR = Path(__file__).resolve().parents[1]


class BackendStartupTests(unittest.TestCase):
    def startup_environment(self, local_mode):
        return {
            **os.environ,
            "COURSESPHERE_LOCAL": local_mode,
            "GOOGLE_APPLICATION_CREDENTIALS": str(BACKEND_DIR / "missing-test-credentials.json"),
        }

    def test_plain_command_starts_locally_without_credentials(self):
        script = '''
import runpy
import sys
from unittest.mock import patch

sys.argv = ["endpoints.py"]
with patch("flask.Flask.run") as serve:
    namespace = runpy.run_path("endpoints.py", run_name="__main__")
    from firebase import firebase_app
    assert firebase_app.project_id == "demo-coursesphere"
    serve.assert_called_once_with(host='127.0.0.1', debug=False)
'''
        result = subprocess.run(
            [sys.executable, "-B", "-c", script], cwd=BACKEND_DIR,
            env=self.startup_environment("0"), capture_output=True, text=True, timeout=30,
        )
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertIn("local mode", result.stdout)

    def test_explicit_firebase_mode_requires_real_credentials(self):
        result = subprocess.run(
            [sys.executable, "-B", "endpoints.py", "--firebase"], cwd=BACKEND_DIR,
            env=self.startup_environment("1"), capture_output=True, text=True, timeout=30,
        )
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("Firebase service account JSON not found", result.stderr)


class FirebaseConfigTests(unittest.TestCase):
    def test_local_mode_needs_no_service_account_and_uses_only_loopback(self):
        with patch.dict(os.environ, {
            "COURSESPHERE_LOCAL": "1",
            "GOOGLE_APPLICATION_CREDENTIALS": "missing-service-account.json",
            "FIREBASE_AUTH_EMULATOR_HOST": "unexpected.example:9099",
            "FIREBASE_DATABASE_EMULATOR_HOST": "unexpected.example:9000",
        }), patch("firebase_admin.credentials.Certificate") as certificate:
            namespace = runpy.run_path(str(BACKEND_DIR / "firebase.py"))
            try:
                certificate.assert_not_called()
                self.assertEqual(namespace["firebase_app"].project_id, "demo-coursesphere")
                self.assertEqual(os.environ["FIREBASE_AUTH_EMULATOR_HOST"], "127.0.0.1:9099")
                self.assertEqual(os.environ["FIREBASE_DATABASE_EMULATOR_HOST"], "127.0.0.1:9000")
            finally:
                firebase_admin.delete_app(namespace["firebase_app"])

    def test_missing_cloud_credentials_do_not_enable_local_mode(self):
        with patch.dict(os.environ, {
            "COURSESPHERE_LOCAL": "0",
            "GOOGLE_APPLICATION_CREDENTIALS": str(BACKEND_DIR / "missing-test-credentials.json"),
            "FIREBASE_AUTH_EMULATOR_HOST": "",
            "FIREBASE_DATABASE_EMULATOR_HOST": "",
        }):
            with self.assertRaisesRegex(FileNotFoundError, "local mode by default"):
                runpy.run_path(str(BACKEND_DIR / "firebase.py"))


@unittest.skipUnless(os.environ.get("RUN_FIREBASE_EMULATOR_TESTS") == "1", "Start emulators and set RUN_FIREBASE_EMULATOR_TESTS=1")
class FirebaseLocalFlowTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.environment = patch.dict(os.environ, {
            "COURSESPHERE_LOCAL": "1", "COURSESPHERE_RATE_LIMIT_STORAGE_URI": "memory://",
        })
        cls.environment.start()
        cls.addClassCleanup(cls.environment.stop)
        sys.path.insert(0, str(BACKEND_DIR))
        cls.addClassCleanup(sys.path.remove, str(BACKEND_DIR))
        import endpoints
        from firebase import Firebase, firebase_app

        cls.firebase = Firebase
        cls.app = endpoints.app
        cls.addClassCleanup(firebase_admin.delete_app, firebase_app)

    def auth_request(self, action, data):
        request = Request(
            f"http://127.0.0.1:9099/identitytoolkit.googleapis.com/v1/accounts:{action}?key=demo-coursesphere-key",
            data=json.dumps(data).encode(),
            headers={"Content-Type": "application/json"},
        )
        try:
            with urlopen(request, timeout=10) as response:
                return response.status, json.load(response)
        except HTTPError as error:
            return error.code, json.load(error)

    def setUp(self):
        import endpoints
        endpoints.limiter.reset()
        self.client = self.app.test_client()
        self.email = f"test-{uuid4().hex}@example.test"
        self.password = "local-test-password"
        status, created = self.auth_request('signUp', {
            'email': self.email, 'password': self.password, 'returnSecureToken': True,
        })
        self.assertEqual(status, 200, created)
        self.uid = created['localId']
        self.addCleanup(self.firebase.delete_user, self.uid)
        status, signed_in = self.auth_request("signInWithPassword", {
            "email": self.email, "password": self.password, "returnSecureToken": True,
        })
        self.assertEqual(status, 200, signed_in)
        self.id_token = signed_in["idToken"]
        self.headers = {"Authorization": f"Bearer {self.id_token}"}

    def test_profile_and_chat_round_trip(self):
        profile = {
            "majors": ["Computer Science"], "minors": ["Mathematics"],
            "courses": ["CS 1110"], "college": "Engineering", "year": "2026", "about": "Local test",
        }
        saved = self.client.post("/users/info", json=profile, headers=self.headers)
        self.assertEqual(saved.status_code, 200, saved.get_json())
        loaded = self.client.get("/users/info", headers=self.headers)
        self.assertEqual(loaded.status_code, 200)
        self.assertEqual(loaded.get_json(), profile)

        hashed = self.client.post("/hash", json="local message", headers=self.headers)
        self.assertEqual(hashed.status_code, 200, hashed.get_json())
        message = {"sender": "user", "content": "local message", "messageID": hashed.get_json()["messageID"]}
        saved_chat = self.client.post("/chats/local-test/messages", json={"messages": [message]}, headers=self.headers)
        self.assertEqual(saved_chat.status_code, 200, saved_chat.get_json())
        messages = self.firebase.get_document(f"users/{self.uid}/chats/local-test", "messages")
        self.assertEqual(list(messages.values()), [message])
        deleted = self.client.delete("/chats/local-test", headers=self.headers)
        self.assertEqual(deleted.status_code, 200)
        self.assertIsNone(self.firebase.get_document(f"users/{self.uid}/chats", "local-test"))

    def test_invalid_login_and_token_are_rejected(self):
        status, _ = self.auth_request("signInWithPassword", {
            "email": self.email, "password": "wrong-password", "returnSecureToken": True,
        })
        self.assertEqual(status, 400)
        response = self.client.get("/users/info", headers={'Authorization': 'Bearer invalid-token'})
        self.assertEqual(response.status_code, 401)

    def test_other_user_cannot_read_or_delete_private_data(self):
        from firebase_admin import auth
        self.firebase.set_user_info(self.uid, {'about': 'Private profile'})
        message = {'sender': 'user', 'content': 'Private message', 'messageID': 'private-id'}
        self.firebase.save_chat(self.uid, 'private-chat', [message])
        status, other = self.auth_request('signUp', {
            'email': f'other-{uuid4().hex}@example.test', 'password': self.password, 'returnSecureToken': True,
        })
        self.assertEqual(status, 200, other)
        self.addCleanup(self.firebase.delete_user, other['localId'])
        headers = {'Authorization': f"Bearer {other['idToken']}"}
        self.assertEqual(self.client.get('/users/info', headers=headers).json, {})
        self.assertEqual(self.client.delete('/chats/private-chat', headers=headers).status_code, 200)
        self.assertIsNotNone(self.firebase.get_document(f'users/{self.uid}/chats', 'private-chat'))
        self.assertEqual(self.client.post('/users/info', json={'uid': self.uid, 'about': 'overwrite'}, headers=headers).status_code, 400)

        # The emulator REST API uses auth= by protocol; the application API rejects URL tokens.
        database_url = f'http://127.0.0.1:9000/users/{self.uid}/info.json?ns=demo-coursesphere-default-rtdb'
        for token in ['', other['idToken']]:
            with self.assertRaises(HTTPError) as rejected:
                urlopen(database_url + f'&auth={token}', timeout=10)
            self.assertIn(rejected.exception.code, (401, 403))

        auth.update_user(other['localId'], disabled=True)
        self.assertEqual(self.client.get('/users/info', headers=headers).status_code, 401)


if __name__ == "__main__":
    unittest.main()
