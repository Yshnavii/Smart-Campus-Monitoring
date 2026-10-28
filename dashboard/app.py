"""
Web dashboard: a small Flask app that reads the same SQLite database
main.py writes to. Run it from the project root in a second terminal:

    python -m dashboard.app

then open http://127.0.0.1:5000
"""
import os
import time

from flask import Flask, jsonify, render_template, request

from config.settings import DB_PATH, DB_LOG_INTERVAL_SECONDS
from utils.database import Database

app = Flask(__name__)
database = Database(DB_PATH)

# A camera with no new reading for this long is shown as OFFLINE.
STALE_AFTER_SECONDS = max(30, DB_LOG_INTERVAL_SECONDS * 3)


@app.route("/")
def index():
    return render_template("index.html")


@app.route("/api/cameras")
def api_cameras():
    """Latest reading for every camera, plus how old it is."""
    now = time.time()
    cameras = []
    for name in database.camera_names():
        latest = database.latest_detection(name)
        if latest is None:
            continue
        latest["camera_name"] = name
        latest["age_seconds"] = round(now - latest["timestamp"])
        latest["online"] = latest["age_seconds"] <= STALE_AFTER_SECONDS
        cameras.append(latest)
    return jsonify(cameras)


@app.route("/api/history")
def api_history():
    """Bucketed counts for one camera: /api/history?camera=Lab&hours=6"""
    camera = request.args.get("camera", "")
    hours = request.args.get("hours", default=6.0, type=float)
    hours = min(max(hours, 0.1), 168.0)
    bucket_seconds = 60 if hours <= 24 else 300
    since = time.time() - hours * 3600
    return jsonify(database.history(camera, since, bucket_seconds=bucket_seconds))


@app.route("/api/alerts")
def api_alerts():
    """Most recent alerts across all cameras."""
    limit = request.args.get("limit", default=20, type=int)
    limit = min(max(limit, 1), 200)
    rows = database.recent_alerts(limit=limit)
    return jsonify([
        {"id": r[0], "camera_name": r[1], "timestamp": r[2],
         "frame_idx": r[3], "count": r[4], "density": r[5]}
        for r in rows
    ])


if __name__ == "__main__":
    # 127.0.0.1 = only this computer. Set DASHBOARD_HOST=0.0.0.0 to let other
    # devices on the network open it (there is no login, so only do that on a trusted network).
    app.run(host=os.getenv("DASHBOARD_HOST", "127.0.0.1"),
            port=int(os.getenv("DASHBOARD_PORT", "5000")),
            debug=False)