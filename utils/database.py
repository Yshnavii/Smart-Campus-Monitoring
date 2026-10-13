import sqlite3
import time
from contextlib import contextmanager


class Database:
    """SQLite persistence for detection readings and fired alerts.

    insert_detection(camera_name, result) matches VideoProcessor's
    result_callback signature exactly, so you can pass it straight in as
    result_callback=database.insert_detection.

    insert_alert(camera_name, frame_idx, count, density) matches
    VideoProcessor's alert_callback signature, but is normally called
    FROM AlertHandler.process() (after its cooldown check) rather than
    wired directly as alert_callback — see alerts/alert_handler.py.
    """

    def __init__(self, db_path="campus_monitoring.db"):
        self.db_path = db_path
        self._init_schema()

    @contextmanager
    def _connect(self):
        conn = sqlite3.connect(self.db_path)
        try:
            yield conn
            conn.commit()
        finally:
            conn.close()

    def _init_schema(self):
        with self._connect() as conn:
            conn.execute("""
                CREATE TABLE IF NOT EXISTS detections (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    camera_name TEXT NOT NULL,
                    timestamp REAL NOT NULL,
                    count INTEGER NOT NULL,
                    avg_count REAL NOT NULL,
                    density REAL NOT NULL,
                    occupancy_pct REAL,
                    alert INTEGER NOT NULL
                )
            """)
            conn.execute("""
                CREATE TABLE IF NOT EXISTS alerts (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    camera_name TEXT NOT NULL,
                    timestamp REAL NOT NULL,
                    frame_idx INTEGER NOT NULL,
                    count INTEGER NOT NULL,
                    density REAL NOT NULL
                )
            """)
            conn.execute("CREATE INDEX IF NOT EXISTS idx_det_cam_ts ON detections(camera_name, timestamp)")
            conn.execute("CREATE INDEX IF NOT EXISTS idx_alert_cam_ts ON alerts(camera_name, timestamp)")

    def insert_detection(self, camera_name, result):
        with self._connect() as conn:
            conn.execute(
                "INSERT INTO detections (camera_name, timestamp, count, avg_count, density, occupancy_pct, alert) "
                "VALUES (?, ?, ?, ?, ?, ?, ?)",
                (camera_name, time.time(), result["count"], result["avg_count"],
                 result["density"], result["occupancy_pct"], int(result["alert"])),
            )

    def insert_alert(self, camera_name, frame_idx, count, density):
        with self._connect() as conn:
            conn.execute(
                "INSERT INTO alerts (camera_name, timestamp, frame_idx, count, density) "
                "VALUES (?, ?, ?, ?, ?)",
                (camera_name, time.time(), frame_idx, count, density),
            )

    def recent_detections(self, camera_name, limit=100):
        with self._connect() as conn:
            cur = conn.execute(
                "SELECT timestamp, count, avg_count, density, occupancy_pct, alert FROM detections "
                "WHERE camera_name = ? ORDER BY timestamp DESC LIMIT ?",
                (camera_name, limit),
            )
            return cur.fetchall()

    def recent_alerts(self, camera_name=None, limit=50):
        with self._connect() as conn:
            if camera_name:
                cur = conn.execute(
                    "SELECT * FROM alerts WHERE camera_name = ? ORDER BY timestamp DESC LIMIT ?",
                    (camera_name, limit),
                )
            else:
                cur = conn.execute("SELECT * FROM alerts ORDER BY timestamp DESC LIMIT ?", (limit,))
            return cur.fetchall()

    def peak_occupancy(self, camera_name, since_timestamp=None):
        """Highest occupancy_pct recorded for a camera, optionally since a given time."""
        with self._connect() as conn:
            if since_timestamp:
                cur = conn.execute(
                    "SELECT MAX(occupancy_pct) FROM detections WHERE camera_name = ? AND timestamp >= ?",
                    (camera_name, since_timestamp),
                )
            else:
                cur = conn.execute(
                    "SELECT MAX(occupancy_pct) FROM detections WHERE camera_name = ?",
                    (camera_name,),
                )
            row = cur.fetchone()
            return row[0] if row else None