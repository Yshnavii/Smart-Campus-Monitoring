import time
from collections import defaultdict


class AlertHandler:
    """Decides whether a fired alert should actually go out: VideoProcessor
    already only calls alert_callback on the rising edge (normal ->
    overcrowded), but flickering around the threshold could still retrigger
    quickly without a cooldown, so this adds a per-camera cooldown window.
    Once approved, fans the alert out to every configured notifier and logs
    it to the database.

    Pass `alert_handler.process` directly as a camera's alert_callback —
    its signature matches VideoProcessor's: (camera_name, frame_idx, count, density).
    """

    def __init__(self, notifiers, database=None, cooldown_seconds=120):
        self.notifiers = notifiers    # list of BaseNotifier instances
        self.database = database      # optional Database instance
        self.cooldown_seconds = cooldown_seconds
        self._last_alert_time = defaultdict(lambda: 0.0)

    def process(self, camera_name, frame_idx, count, density):
        now = time.time()
        elapsed = now - self._last_alert_time[camera_name]
        if elapsed < self.cooldown_seconds:
            return  # still in cooldown — suppress repeat notifications

        self._last_alert_time[camera_name] = now
        self._fire(camera_name, frame_idx, count, density)

    def _fire(self, camera_name, frame_idx, count, density):
        subject = f"[OVERCROWDED] {camera_name}"
        message = f"{camera_name}: {count} people detected (density={density:.2f} people/MP) at frame {frame_idx}."

        for notifier in self.notifiers:
            notifier.send(subject, message)

        if self.database:
            self.database.insert_alert(camera_name, frame_idx, count, density)

        print(f"[ALERT] {subject} — {message}")