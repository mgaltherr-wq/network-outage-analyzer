"""Persistent reachability and outage history, behind the Trends page.

Stored in SQLite (stdlib, so nothing extra to install or bundle) as
history.db in the per-user data directory, next to .env.

Raw per-sweep samples would be ~2.9M rows a day for 500 devices at the
default 15s interval, so samples are rolled up as they arrive instead: one
device_hourly row per device per hour counts how many checks it had and how
many succeeded. Every trend view is an aggregate of those rows. Outage
episodes (a location at or above the outage threshold) are kept as one row
each, from when it crossed the threshold until it recovered.
"""

import json
import sqlite3
import threading
import time

from app.paths import user_data_dir

HOUR = 3600
DAY = 24 * HOUR

DEFAULT_DB_PATH = user_data_dir() / "history.db"

_SCHEMA = """
CREATE TABLE IF NOT EXISTS device_hourly (
    ip TEXT NOT NULL,
    hour INTEGER NOT NULL,          -- epoch seconds, start of the UTC hour
    location TEXT NOT NULL DEFAULT '',
    checks INTEGER NOT NULL,
    up INTEGER NOT NULL,
    PRIMARY KEY (ip, hour)
);
CREATE INDEX IF NOT EXISTS device_hourly_hour ON device_hourly (hour);

CREATE TABLE IF NOT EXISTS outage_episodes (
    id INTEGER PRIMARY KEY,
    location TEXT NOT NULL,
    location_key TEXT NOT NULL,     -- casefolded, matching the dashboard's grouping
    started_at REAL NOT NULL,
    last_seen_at REAL NOT NULL,     -- last sweep that still saw it down
    ended_at REAL,                  -- NULL while ongoing
    devices INTEGER NOT NULL,
    peak_percent_down REAL NOT NULL,
    confidence TEXT,                -- JSON, from the dashboard's cause assessment
    ticket_number TEXT,
    ticket_action TEXT
);
CREATE INDEX IF NOT EXISTS outage_episodes_started ON outage_episodes (started_at);
"""


def _availability(up, checks):
    return up / checks if checks else None


class HistoryStore:
    def __init__(self, path=DEFAULT_DB_PATH):
        self.path = path
        self._lock = threading.Lock()
        self._conn = None

    def _db(self):
        # Opened lazily so importing the dashboard (tests, --selftest) doesn't
        # create a database. One connection shared across threads, serialized
        # by self._lock.
        if self._conn is None:
            self._conn = sqlite3.connect(self.path, check_same_thread=False)
            self._conn.row_factory = sqlite3.Row
            self._conn.execute("PRAGMA journal_mode=WAL")
            self._conn.executescript(_SCHEMA)
        return self._conn

    def close(self):
        with self._lock:
            if self._conn is not None:
                self._conn.close()
                self._conn = None

    # -- recording ---------------------------------------------------------

    def record_sweep(self, results, locations, checked_at):
        """Add one sweep's {ip: reachable} *results* to the hourly rollups.
        *locations* maps ip -> location name (missing/blank is fine)."""
        hour = int(checked_at) // HOUR * HOUR
        rows = [(ip, hour, locations.get(ip, ""), int(bool(up))) for ip, up in results.items()]
        with self._lock, self._db() as db:
            db.executemany(
                """
                INSERT INTO device_hourly (ip, hour, location, checks, up) VALUES (?, ?, ?, 1, ?)
                ON CONFLICT (ip, hour) DO UPDATE SET
                    checks = checks + 1, up = up + excluded.up, location = excluded.location
                """,
                rows,
            )

    def update_outages(self, location_status, threshold, at):
        """Open, extend, or close outage episodes from one sweep.

        *location_status* maps location name -> (percent_down, device_count)
        for every location that has devices. A location at or above
        *threshold* opens an episode (or extends its open one); one below it,
        or no longer present at all, closes its open episode at *at*.
        """
        with self._lock, self._db() as db:
            open_by_key = {
                row["location_key"]: row
                for row in db.execute("SELECT * FROM outage_episodes WHERE ended_at IS NULL")
            }
            seen = set()
            for location, (percent_down, devices) in location_status.items():
                key = location.casefold()
                seen.add(key)
                episode = open_by_key.get(key)
                if percent_down >= threshold:
                    if episode:
                        db.execute(
                            "UPDATE outage_episodes SET last_seen_at = ?, devices = ?,"
                            " peak_percent_down = MAX(peak_percent_down, ?) WHERE id = ?",
                            (at, devices, percent_down, episode["id"]),
                        )
                    else:
                        db.execute(
                            "INSERT INTO outage_episodes (location, location_key, started_at,"
                            " last_seen_at, devices, peak_percent_down) VALUES (?, ?, ?, ?, ?, ?)",
                            (location, key, at, at, devices, percent_down),
                        )
                elif episode:
                    db.execute("UPDATE outage_episodes SET ended_at = ? WHERE id = ?", (at, episode["id"]))

            for key, episode in open_by_key.items():
                if key not in seen:
                    db.execute("UPDATE outage_episodes SET ended_at = ? WHERE id = ?", (at, episode["id"]))

    def close_stale_episodes(self):
        """Close episodes left open by a previous run at the last time they
        were seen, rather than stretching them across the downtime. If the
        outage is still going, the next sweep opens a fresh episode."""
        with self._lock, self._db() as db:
            db.execute("UPDATE outage_episodes SET ended_at = last_seen_at WHERE ended_at IS NULL")

    def annotate_outage(self, location, confidence, ticket):
        """Attach the dashboard's cause assessment and ServiceNow ticket to
        *location*'s open episode, if there is one."""
        with self._lock, self._db() as db:
            db.execute(
                """
                UPDATE outage_episodes SET
                    confidence = COALESCE(?, confidence),
                    ticket_number = COALESCE(ticket_number, ?),
                    ticket_action = COALESCE(ticket_action, ?)
                WHERE location_key = ? AND ended_at IS NULL
                """,
                (
                    json.dumps(confidence) if confidence else None,
                    ticket.get("number") if ticket else None,
                    ticket.get("action") if ticket else None,
                    location.casefold(),
                ),
            )

    def prune(self, retention_days, now=None):
        cutoff = (now or time.time()) - retention_days * DAY
        with self._lock, self._db() as db:
            db.execute("DELETE FROM device_hourly WHERE hour < ?", (cutoff,))
            db.execute("DELETE FROM outage_episodes WHERE ended_at IS NOT NULL AND ended_at < ?", (cutoff,))

    # -- querying ----------------------------------------------------------

    def trends(self, since, bucket_seconds, now=None, utc_offset_seconds=0, device_limit=10):
        """Everything the Trends page shows for the window [since, now].

        Buckets are aligned to *utc_offset_seconds* so daily buckets start at
        the viewer's local midnight rather than UTC's. Buckets with no data
        (the app wasn't running) are omitted, not reported as 0% or 100%.
        """
        now = now or time.time()
        since_hour = int(since) // HOUR * HOUR
        offset = int(utc_offset_seconds)
        bucket_expr = "((hour + :offset) / :bucket) * :bucket - :offset"
        params = {"since": since_hour, "bucket": int(bucket_seconds), "offset": offset}

        with self._lock:
            db = self._db()
            fleet = [
                {"t": row["t"], "availability": _availability(row["up"], row["checks"])}
                for row in db.execute(
                    f"SELECT {bucket_expr} AS t, SUM(up) AS up, SUM(checks) AS checks"
                    " FROM device_hourly WHERE hour >= :since GROUP BY t ORDER BY t",
                    params,
                )
            ]
            fleet_totals = db.execute(
                "SELECT SUM(up) AS up, SUM(checks) AS checks FROM device_hourly WHERE hour >= :since",
                params,
            ).fetchone()

            locations = {}
            for row in db.execute(
                f"SELECT lower(location) AS key, MAX(location) AS location, {bucket_expr} AS t,"
                " SUM(up) AS up, SUM(checks) AS checks FROM device_hourly"
                " WHERE hour >= :since AND location != '' GROUP BY key, t ORDER BY key, t",
                params,
            ):
                entry = locations.setdefault(
                    row["key"], {"location": row["location"], "up": 0, "checks": 0, "series": []}
                )
                entry["up"] += row["up"]
                entry["checks"] += row["checks"]
                entry["series"].append({"t": row["t"], "availability": _availability(row["up"], row["checks"])})

            devices = [
                {
                    "ip_address": row["ip"],
                    "location": row["location"],
                    "availability": _availability(row["up"], row["checks"]),
                }
                for row in db.execute(
                    "SELECT ip, MAX(location) AS location, SUM(up) AS up, SUM(checks) AS checks"
                    " FROM device_hourly WHERE hour >= :since GROUP BY ip HAVING SUM(up) < SUM(checks)"
                    " ORDER BY CAST(SUM(up) AS REAL) / SUM(checks), ip LIMIT :limit",
                    {**params, "limit": device_limit},
                )
            ]

            episodes = [
                self._episode(row, now)
                for row in db.execute(
                    "SELECT * FROM outage_episodes WHERE COALESCE(ended_at, :now) >= :since"
                    " ORDER BY started_at DESC",
                    {"since": since, "now": now},
                )
            ]

        outages_by_key = {}
        for episode in episodes:
            stats = outages_by_key.setdefault(episode["location"].casefold(), {"outages": 0, "outage_seconds": 0})
            stats["outages"] += 1
            stats["outage_seconds"] += episode["duration_seconds"]

        location_rows = []
        for key, entry in locations.items():
            stats = outages_by_key.get(entry["location"].casefold(), {"outages": 0, "outage_seconds": 0})
            location_rows.append({
                "location": entry["location"],
                "availability": _availability(entry["up"], entry["checks"]),
                "series": entry["series"],
                **stats,
            })
        location_rows.sort(key=lambda row: (row["availability"], row["location"].casefold()))

        return {
            "availability": _availability(fleet_totals["up"] or 0, fleet_totals["checks"] or 0),
            "fleet": fleet,
            "locations": location_rows,
            "devices": devices,
            "outages": episodes,
        }

    @staticmethod
    def _episode(row, now):
        ended_at = row["ended_at"]
        return {
            "location": row["location"],
            "started_at": row["started_at"],
            "ended_at": ended_at,
            "ongoing": ended_at is None,
            "duration_seconds": (ended_at or now) - row["started_at"],
            "devices": row["devices"],
            "peak_percent_down": row["peak_percent_down"],
            "confidence": json.loads(row["confidence"]) if row["confidence"] else None,
            "ticket": {"number": row["ticket_number"], "action": row["ticket_action"]}
            if row["ticket_number"] else None,
        }
