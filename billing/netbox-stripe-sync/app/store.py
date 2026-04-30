import sqlite3
from contextlib import closing
from pathlib import Path


class EventStore:
    def __init__(self, db_path: str) -> None:
        self.db_path = db_path
        Path(db_path).parent.mkdir(parents=True, exist_ok=True)
        self._init()

    def _init(self) -> None:
        with closing(sqlite3.connect(self.db_path)) as conn:
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS processed_events (
                    event_id TEXT PRIMARY KEY,
                    processed_at TEXT NOT NULL
                )
                """
            )
            conn.commit()

    def seen(self, event_id: str) -> bool:
        with closing(sqlite3.connect(self.db_path)) as conn:
            row = conn.execute(
                "SELECT event_id FROM processed_events WHERE event_id = ?",
                (event_id,),
            ).fetchone()
            return row is not None

    def mark(self, event_id: str, processed_at: str) -> None:
        with closing(sqlite3.connect(self.db_path)) as conn:
            conn.execute(
                "INSERT OR IGNORE INTO processed_events(event_id, processed_at) VALUES (?, ?)",
                (event_id, processed_at),
            )
            conn.commit()
