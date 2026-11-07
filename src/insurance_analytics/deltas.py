"""Transactional, version-ordered field deltas with durable replay protection."""

import json
import sqlite3
from pathlib import Path

FIELDS = ("decision", "risk_class", "channel")


class DeltaStore:
    def __init__(self, path: str | Path):
        self.path = str(path)
        with self.connect() as db:
            db.executescript("""
                CREATE TABLE IF NOT EXISTS events(event_id TEXT PRIMARY KEY, payload TEXT NOT NULL);
                CREATE TABLE IF NOT EXISTS current(application_id TEXT PRIMARY KEY,
                    version INTEGER NOT NULL, payload TEXT NOT NULL);
                CREATE TABLE IF NOT EXISTS deltas(event_id TEXT, application_id TEXT,
                    version INTEGER, field TEXT, old_value TEXT, new_value TEXT,
                    PRIMARY KEY(event_id, field));
            """)

    def connect(self):
        return sqlite3.connect(self.path, timeout=30)

    def apply(self, event: dict) -> int:
        required = {"event_id", "application_id", "version", "values"}
        if not required <= event.keys() or not isinstance(event["values"], dict):
            raise ValueError("Event needs id, application, version, and values")
        if not all(isinstance(event[k], str) and event[k] for k in ["event_id", "application_id"]):
            raise ValueError("Identifiers must be nonempty strings")
        if type(event["version"]) is not int or event["version"] < 1:
            raise ValueError("Version must be a positive integer")
        if set(event["values"]) - set(FIELDS):
            raise ValueError("Unknown decision fields")
        if any(v is not None and not isinstance(v, str) for v in event["values"].values()):
            raise ValueError("Decision values must be strings or null")
        canonical = json.dumps(event, sort_keys=True, allow_nan=False)
        with self.connect() as db:
            db.execute("BEGIN IMMEDIATE")
            replay = db.execute(
                "SELECT payload FROM events WHERE event_id=?", (event["event_id"],)
            ).fetchone()
            if replay:
                if replay[0] != canonical:
                    raise ValueError("Conflicting replay of event id")
                return 0
            previous = db.execute(
                "SELECT version,payload FROM current WHERE application_id=?",
                (event["application_id"],),
            ).fetchone()
            if previous and event["version"] <= previous[0]:
                raise ValueError("Stale version: source must replay in version order")
            old = json.loads(previous[1]) if previous else {}
            new = old | event["values"]
            count = 0
            for field in FIELDS:
                if old.get(field) != new.get(field):
                    db.execute(
                        "INSERT INTO deltas VALUES (?,?,?,?,?,?)",
                        (
                            event["event_id"],
                            event["application_id"],
                            event["version"],
                            field,
                            old.get(field),
                            new.get(field),
                        ),
                    )
                    count += 1
            db.execute("INSERT INTO events VALUES (?,?)", (event["event_id"], canonical))
            db.execute(
                "INSERT INTO current VALUES (?,?,?) ON CONFLICT(application_id) DO UPDATE SET version=excluded.version,payload=excluded.payload",
                (event["application_id"], event["version"], json.dumps(new, sort_keys=True)),
            )
            return count
