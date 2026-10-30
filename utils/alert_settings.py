"""
Email alert settings shared by the dashboard (writes them) and main.py (reads them).

Stored in alert_settings.json in the project root. The file is written atomically
with owner-only permissions where the OS supports it. public_view() never contains
the app password, so the password can never be sent to a browser.
"""
import json
import os
import re
import threading
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
SETTINGS_PATH = Path(os.getenv("ALERT_SETTINGS_PATH", str(ROOT / "alert_settings.json")))
EMAIL_RE = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")
_KEYS = ("sender_email", "app_password", "recipients")
_lock = threading.Lock()


def load():
    """All stored settings, including the password. Server-side use only."""
    try:
        data = json.loads(SETTINGS_PATH.read_text(encoding="utf-8"))
        if not isinstance(data, dict):
            data = {}
    except (OSError, ValueError):
        data = {}
    return {k: str(data.get(k, "")) for k in _KEYS}


def public_view():
    """What the browser may see: no password, only whether one is saved."""
    s = load()
    return {"sender_email": s["sender_email"],
            "recipients": s["recipients"],
            "password_set": bool(s["app_password"])}


def _write(data):
    tmp = SETTINGS_PATH.with_name(SETTINGS_PATH.name + ".tmp")
    fd = os.open(str(tmp), os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
    with os.fdopen(fd, "w", encoding="utf-8") as f:
        json.dump(data, f)
    try:
        os.chmod(str(tmp), 0o600)
    except OSError:
        pass
    os.replace(str(tmp), str(SETTINGS_PATH))  # atomic: main.py never reads half a file


def save(sender_email, app_password, recipients):
    """Validate and store. A blank app_password keeps the saved one (same sender only)."""
    sender = str(sender_email or "").strip()
    new_pw = "".join(str(app_password or "").split())  # Google shows it in groups of 4; spaces aren't part of it
    emails = [e.strip() for e in str(recipients or "").split(",") if e.strip()]

    if sender and not EMAIL_RE.match(sender):
        raise ValueError("Sender email is not valid.")
    bad = [e for e in emails if not EMAIL_RE.match(e)]
    if bad:
        raise ValueError("Invalid recipient: " + ", ".join(bad))
    if new_pw and not sender:
        raise ValueError("Enter the sender email for this app password.")
    if new_pw and not 8 <= len(new_pw) <= 64:
        raise ValueError("App password length looks wrong. Gmail app passwords are 16 characters.")

    with _lock:
        current = load()
        if new_pw:
            password = new_pw
        elif sender and sender == current["sender_email"]:
            password = current["app_password"]
        else:
            password = ""
        if sender and not password:
            raise ValueError("Enter the app password for this sender.")
        _write({"sender_email": sender, "app_password": password, "recipients": ",".join(emails)})