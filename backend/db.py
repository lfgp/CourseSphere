import sqlite3
from pathlib import Path 

def create_connection():
    path = Path(__file__).resolve().parent / 'cornell-course-sphere-data' / 'course-roster-kaggle' / 'roster_reviews.sqlite.db'
    return sqlite3.connect(path)

def execute_query(query, parameters=()): # correção da sql injection utilizada anteriormente
    conn = create_connection()
    conn.row_factory = sqlite3.Row
    try:
        with conn:
            cursor = conn.execute(query, parameters)
            return [dict(row) for row in cursor.fetchall()]
    finally:
        conn.close()
