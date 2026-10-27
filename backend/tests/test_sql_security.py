from contextlib import closing
from pathlib import Path
import sqlite3
import sys
import tempfile
import types
import unittest
from unittest.mock import Mock, patch

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / 'backend'))

class SQLSecurityTests(unittest.TestCase):
    def test_injection_is_literal_data_in_every_filter(self):
        from flask import Flask
        from backend.blueprints.courses import courses_bp
        from backend import db
        app = Flask('sql-security')
        app.register_blueprint(courses_bp)
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / 'test.sqlite'
            with closing(sqlite3.connect(path)) as connection, connection:
                connection.execute('CREATE TABLE courses (id INTEGER, semester TEXT, department TEXT, instructor TEXT)')
                connection.execute('INSERT INTO courses VALUES (1, ?, ?, ?)', ('FA26', 'CS', "O'Brien"))
            with patch.object(db, 'create_connection', side_effect=lambda: sqlite3.connect(path)):
                client = app.test_client()
                for field in ['semester', 'department', 'instructor']:
                    with self.subTest(field=field):
                        self.assertEqual(client.get(f"/courses/{field}/%27%20OR%201%3D1--").status_code, 404)
                self.assertEqual(client.get('/courses/instructor/O%27Brien').status_code, 200)
                self.assertEqual(len(client.get('/courses').json), 1)
                self.assertEqual(db.execute_query('SELECT * FROM courses WHERE department = ?', ("' OR 1=1--",)), [])

    def test_migration_rejects_sql_identifiers_before_deleting_comments(self):
        crawler_stub = types.ModuleType('reddit_crawler')
        crawler_stub.RedditCrawler = Mock()
        module = types.ModuleType('security_migration_test')
        module.__file__ = str(ROOT / 'backend/cornell-course-sphere-data/reddit-data/data-migrations.py')
        with patch.dict(sys.modules, {'reddit_crawler': crawler_stub, module.__name__: module}):
            exec(compile(Path(module.__file__).read_text(encoding='utf-8'), module.__file__, 'exec'), module.__dict__)
            manager = module.DataMigrations(':memory:')
            try:
                manager.cursor.execute('INSERT INTO reddit_posts (post_id, title) VALUES (1, ?)', ('Original',))
                manager.cursor.execute('INSERT INTO reddit_comments (post_id, body) VALUES (1, ?)', ('Comment',))
                manager.conn.commit()
                with self.assertRaises(ValueError):
                    manager.update_post(1, **{'title = NULL WHERE 1=1 --': 'injection'})
                self.assertEqual(manager.cursor.execute('SELECT count(*) FROM reddit_comments').fetchone()[0], 1)
                manager.update_post(1, title="' OR 1=1 --")
                self.assertEqual(manager.cursor.execute('SELECT title FROM reddit_posts').fetchone()[0], "' OR 1=1 --")
            finally:
                manager.conn.close()



if __name__ == "__main__":
    unittest.main()
