"""
CrowdSense dashboard: starts/stops main.py as a background process, shows per-room
live frames and stats, and stores the email alert settings.

Run from the project root:   python -m dashboard.app
then open http://127.0.0.1:5000
"""
import atexit
import base64
import hmac
import os
import subprocess
import sys
import threading
import time
from pathlib import Path

from flask import Flask, Response, jsonify, render_template, request

from config.settings import DB_PATH, DB_LOG_INTERVAL_SECONDS, DEFAULT_CAMERAS
from utils import alert_settings
from utils.database import Database
from utils.snapshots import slugify

ROOT = Path(__file__).resolve().parent.parent
SNAPSHOT_DIR = ROOT / "snapshots"
LOG_PATH = ROOT / "monitor.log"
DASH_PASSWORD = os.getenv("DASHBOARD_PASSWORD", "")
STALE_AFTER_SECONDS = max(30, DB_LOG_INTERVAL_SECONDS * 3)
FRAME_MAX_AGE_SECONDS = 15

app = Flask(__name__)
database = Database(DB_PATH)

ROOMS = [{"name": c.name, "slug": slugify(c.name)} for c in DEFAULT_CAMERAS]


def find_room(slug):
    return next((r for r in ROOMS if r["slug"] == slug), None)


class MonitorProcess:
    """Owns the one background `python main.py` process."""

    def __init__(self):
        self._lock = threading.Lock()
        self._proc = None
        self._started_at = None
        self._stopped_by_user = False

    def _alive(self):
        return self._proc is not None and self._proc.poll() is None

    def start(self):
        with self._lock:
            if self._alive():
                return False, "Already running."
            SNAPSHOT_DIR.mkdir(exist_ok=True)
            for old in SNAPSHOT_DIR.glob("*.jpg"):
                old.unlink(missing_ok=True)
            env = dict(os.environ, SNAPSHOT_DIR=str(SNAPSHOT_DIR), PYTHONUNBUFFERED="1")
            flags = subprocess.CREATE_NEW_PROCESS_GROUP if os.name == "nt" else 0
            with open(LOG_PATH, "wb") as log:
                self._proc = subprocess.Popen(
                    [sys.executable, "main.py"],   # fixed command: nothing from the browser goes in here
                    cwd=str(ROOT), env=env,
                    stdin=subprocess.DEVNULL, stdout=log, stderr=subprocess.STDOUT,
                    creationflags=flags,
                )
            self._started_at = time.time()
            self._stopped_by_user = False
            return True, "Started."

    def stop(self):
        with self._lock:
            if not self._alive():
                return False, "Not running."
            self._stopped_by_user = True
            self._proc.terminate()
            try:
                self._proc.wait(timeout=10)
            except subprocess.TimeoutExpired:
                self._proc.kill()
                self._proc.wait(timeout=5)
            return True, "Stopped."

    def status(self):
        with self._lock:
            if self._proc is None:
                return {"running": False, "crashed": False, "exit_code": None,
                        "uptime_seconds": 0, "log_tail": ""}
            code = self._proc.poll()
            running = code is None
            crashed = (not running) and (not self._stopped_by_user)
            return {
                "running": running,
                "crashed": crashed,
                "exit_code": code,
                "uptime_seconds": round(time.time() - self._started_at) if running else 0,
                "log_tail": self._tail_log() if crashed else "",
            }

    @staticmethod
    def _tail_log(max_bytes=1500):
        try:
            with open(LOG_PATH, "rb") as f:
                f.seek(0, os.SEEK_END)
                f.seek(max(0, f.tell() - max_bytes))
                return f.read().decode("utf-8", errors="replace")
        except OSError:
            return ""


monitor = MonitorProcess()
atexit.register(lambda: monitor.stop())  # don't leave main.py running if the dashboard exits normally


@app.before_request
def guard():
    # Optional password (HTTP Basic: any username, password = DASHBOARD_PASSWORD).
    if DASH_PASSWORD:
        header = request.headers.get("Authorization", "")
        ok = False
        if header.startswith("Basic "):
            try:
                supplied = base64.b64decode(header[6:]).decode().partition(":")[2]
                ok = hmac.compare_digest(supplied, DASH_PASSWORD)
            except Exception:
                ok = False
        if not ok:
            return Response("Login required", 401, {"WWW-Authenticate": 'Basic realm="CrowdSense"'})
    # State-changing requests must be JSON. A web form on another site cannot send that.
    if request.method == "POST" and not request.is_json:
        return jsonify(error="JSON body required"), 415
    return None


@app.route("/")
def index():
    return render_template("index.html")


# ---------- master control ----------
@app.route("/api/project")
def api_project():
    return jsonify(monitor.status())


@app.route("/api/project/start", methods=["POST"])
def api_project_start():
    ok, msg = monitor.start()
    return jsonify(ok=ok, message=msg), (200 if ok else 409)


@app.route("/api/project/stop", methods=["POST"])
def api_project_stop():
    ok, msg = monitor.stop()
    return jsonify(ok=ok, message=msg), (200 if ok else 409)


# ---------- rooms ----------
@app.route("/api/rooms")
def api_rooms():
    now = time.time()
    running = monitor.status()["running"]
    out = []
    for room in ROOMS:
        item = dict(room, has_data=False, online=False)
        latest = database.latest_detection(room["name"])
        if latest:
            age = round(now - latest["timestamp"])
            item.update(latest)
            item.update(has_data=True, age_seconds=age,
                        online=running and age <= STALE_AFTER_SECONDS)
        out.append(item)
    return jsonify(out)


@app.route("/api/frame/<slug>")
def api_frame(slug):
    room = find_room(slug)  # only known rooms, so no arbitrary file paths
    if room is None:
        return Response("Unknown room", 404)
    path = SNAPSHOT_DIR / (room["slug"] + ".jpg")
    try:
        if time.time() - path.stat().st_mtime > FRAME_MAX_AGE_SECONDS:
            return Response("Stale", 404)
        data = path.read_bytes()
    except OSError:
        return Response("No frame", 404)
    return Response(data, mimetype="image/jpeg", headers={"Cache-Control": "no-store"})


@app.route("/api/history")
def api_history():
    room = find_room(request.args.get("room", ""))
    if room is None:
        return jsonify([])
    hours = min(max(request.args.get("hours", default=6.0, type=float), 0.1), 168.0)
    bucket_seconds = 60 if hours <= 24 else 300
    return jsonify(database.history(room["name"], time.time() - hours * 3600,
                                    bucket_seconds=bucket_seconds))


@app.route("/api/alerts")
def api_alerts():
    room = find_room(request.args.get("room", ""))
    limit = min(max(request.args.get("limit", default=10, type=int), 1), 100)
    rows = database.recent_alerts(limit=200)
    result = [{"id": r[0], "camera_name": r[1], "timestamp": r[2],
               "frame_idx": r[3], "count": r[4], "density": r[5]} for r in rows]
    if room is not None:
        result = [a for a in result if a["camera_name"] == room["name"]]
    return jsonify(result[:limit])


# ---------- email alert settings ----------
@app.route("/api/emails", methods=["GET", "POST"])
def api_emails():
    if request.method == "POST":
        data = request.get_json(silent=True) or {}
        try:
            alert_settings.save(data.get("sender_email"), data.get("app_password"),
                                data.get("recipients"))
        except ValueError as exc:
            return jsonify(error=str(exc)), 400
    # The password is never included in the response, only whether one is saved.
    return jsonify(alert_settings.public_view())


if __name__ == "__main__":
    host = os.getenv("DASHBOARD_HOST", "127.0.0.1")
    # This page can start the system and store mail credentials, so it must not be
    # reachable from the network without a password.
    if host not in ("127.0.0.1", "localhost", "::1") and not DASH_PASSWORD:
        sys.exit("Refusing to listen on %s without DASHBOARD_PASSWORD set." % host)
    # Keep this single-process: do not run it with several worker processes.
    app.run(host=host, port=int(os.getenv("DASHBOARD_PORT", "5000")),
            debug=False, threaded=True)