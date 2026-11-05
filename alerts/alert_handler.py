import threading
import time
from collections import defaultdict
from datetime import datetime


class AlertHandler:
    """Decides whether a fired alert should actually go out. VideoProcessor
    calls alert_callback on every detection while a room is overcrowded, so
    this applies a per-camera cooldown: the first detection sends an alert
    immediately, then a reminder goes out every `cooldown_seconds` for as long
    as the room stays overcrowded. Once approved, fans the alert out to every
    configured notifier (in a background thread, so a slow mail server never
    stalls the camera) and logs it to the database.

    Pass `alert_handler.process` directly as a camera's alert_callback —
    its signature matches VideoProcessor's: (camera_name, frame_idx, count, density).
    """

    def __init__(self, notifiers, database=None, cooldown_seconds=60):
        self.notifiers = notifiers    # list of BaseNotifier instances
        self.database = database      # optional Database instance
        self.cooldown_seconds = cooldown_seconds
        self._last_alert_time = defaultdict(lambda: 0.0)

    def process(self, camera_name, frame_idx, count, density, alert_type="overcrowding"):
        now = time.time()
        alert_key = (camera_name, alert_type)
        elapsed = now - self._last_alert_time[alert_key]
        if elapsed < self.cooldown_seconds:
            return  # still in cooldown — suppress repeat notifications

        self._last_alert_time[alert_key] = now
        self._fire(camera_name, frame_idx, count, density, alert_type)

    def _fire(self, camera_name, frame_idx, count, density, alert_type="overcrowding"):
        now = datetime.now().strftime("%d %b %Y, %I:%M:%S %p")
        if alert_type == "unauthorised_access":
            subject = f"[RESTRICTED AREA ALERT] Person detected - {camera_name}"
            message = (
                "RESTRICTED-AREA SECURITY NOTIFICATION\n\n"
                f"A person has been detected by the restricted-access camera: {camera_name}.\n"
                f"Detected persons: {count} (alert threshold: 1 person).\n"
                f"Time: {now}\nCamera frame: {frame_idx}\n\n"
                "Please review the live camera feed and verify whether this entry is authorised.\n"
                "This is an automated person-detection alert; it does not verify identity or access permission."
            )
        else:
            subject = f"[OVERCROWDING ALERT] {camera_name}"
            message = (f"{camera_name}: {count} people detected "
                       f"(density={density:.2f} people/MP) at {now} (frame {frame_idx}).")

        if self.database:
            self.database.insert_alert(camera_name, frame_idx, count, density, alert_type)

        threading.Thread(target=self._notify_all, args=(subject, message), daemon=True).start()

        print(f"[ALERT] {subject} — {message}")

    def _notify_all(self, subject, message):
        for notifier in self.notifiers:
            try:
                notifier.send(subject, message)
            except Exception as exc:
                print(f"[AlertHandler] {type(notifier).__name__} failed: {exc}")