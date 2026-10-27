"""
Local sanity test — exercises OUR code (VideoProcessor's loop/EOF handling,
CameraProcessor's thread lifecycle, BatchProcessor's aggregation, AlertHandler's
cooldown, Database's writes) without needing real YOLO weights or network
access. A FakeDetector stands in for OvercrowdingDetector/SAHIOvercrowdingDetector,
implementing the same BaseDetector interface with a scripted person-count
sequence instead of real inference.
"""
import os
import sys
import time
import numpy as np
import cv2

sys.path.insert(0, os.path.dirname(__file__))

from detectors.base_detector import BaseDetector
from processors.video_processor import VideoProcessor
from processors.batch_processor import BatchProcessor
from processors.camera_processor import CameraProcessor
from alerts.alert_handler import AlertHandler
from alerts.notifiers import BaseNotifier
from utils.database import Database


class FakeDetector(BaseDetector):
    """Stands in for a real YOLO/SAHI detector: returns a scripted number of
    boxes per call instead of running inference, so we can test the pipeline
    logic (smoothing, alerting, callbacks) deterministically."""

    def __init__(self, counts_sequence, **kwargs):
        super().__init__(**kwargs)
        self.counts_sequence = counts_sequence
        self._call_idx = 0

    def detect_people(self, frame):
        n = self.counts_sequence[min(self._call_idx, len(self.counts_sequence) - 1)]
        self._call_idx += 1
        return [(10, 10, 20, 20)] * n


class FakeNotifier(BaseNotifier):
    def __init__(self):
        self.sent = []

    def send(self, subject, message):
        self.sent.append((subject, message))
        return True


def make_test_video(path, num_frames, size=(320, 240)):
    w, h = size
    writer = cv2.VideoWriter(path, cv2.VideoWriter_fourcc(*"mp4v"), 10, (w, h))
    rng = np.random.default_rng(0)
    for _ in range(num_frames):
        frame = rng.integers(0, 255, (h, w, 3), dtype=np.uint8)
        writer.write(frame)
    writer.release()


results = {"pass": 0, "fail": 0}


def check(label, condition, detail=""):
    status = "PASS" if condition else "FAIL"
    results["pass" if condition else "fail"] += 1
    print(f"[{status}] {label}" + (f" — {detail}" if detail and not condition else ""))


# ---------------------------------------------------------------------------
print("=== Test 1: BatchProcessor + VideoProcessor EOF handling ===")
tmp_dir = "/tmp/pipeline_test"
os.makedirs(tmp_dir, exist_ok=True)
video_path = os.path.join(tmp_dir, "sample.mp4")

# Ramp: normal -> crosses count_threshold(10) -> stays over -> drops back down
counts = [2, 2, 3, 5, 11, 13, 14, 14, 13, 6, 3, 2]
make_test_video(video_path, num_frames=len(counts))

start = time.time()
bp = BatchProcessor(
    detector_factory=lambda: FakeDetector(counts, count_threshold=10, smoothing_window=1, max_capacity=15),
    output_dir=os.path.join(tmp_dir, "annotated"),
    frame_stride=1,
)
stats = bp.process_file(video_path)
elapsed = time.time() - start

check("BatchProcessor.process_file() returns without hanging", elapsed < 10, f"took {elapsed:.1f}s")
check("processed all frames exactly once (no EOF reconnect loop)",
      stats["frames_processed"] == len(counts),
      f"expected {len(counts)}, got {stats['frames_processed']}")
check("peak_count matches scripted max", stats["peak_count"] == max(counts),
      f"expected {max(counts)}, got {stats['peak_count']}")
check("alert fired at least once", stats["alert_count"] >= 1, f"alert_count={stats['alert_count']}")
check("annotated output video was written",
      os.path.exists(os.path.join(tmp_dir, "annotated", "sample_annotated.mp4")))
check("peak_occupancy computed (max_capacity=15)", stats["peak_occupancy"] > 0,
      f"peak_occupancy={stats['peak_occupancy']}")


# ---------------------------------------------------------------------------
print("\n=== Test 2: CameraProcessor thread lifecycle (start/stop) ===")
cam = CameraProcessor()
live_detector = FakeDetector(counts, count_threshold=10, smoothing_window=1)
cam.add_camera("test_cam", video_path, live_detector, frame_stride=1)
cam.start_camera("test_cam")
check("camera reports running right after start", cam.is_camera_running("test_cam"))
time.sleep(1.0)  # let it process + hit EOF + go into reconnect-retry loop (is_live=True)
cam.stop_camera("test_cam")
time.sleep(2.5)  # give the 2s reconnect sleep time to notice _running=False and exit
check("camera thread exits cleanly after stop()", not cam.is_camera_running("test_cam"))


# ---------------------------------------------------------------------------
print("\n=== Test 3: AlertHandler cooldown + notifier fan-out ===")
db_path = os.path.join(tmp_dir, "test.db")
if os.path.exists(db_path):
    os.remove(db_path)
database = Database(db_path)
fake_notifier = FakeNotifier()
handler = AlertHandler([fake_notifier], database=database, cooldown_seconds=0.3)

handler.process("cam_a", frame_idx=1, count=20, density=5.0)
handler.process("cam_a", frame_idx=2, count=21, density=5.1)  # should be suppressed (cooldown)
check("second alert within cooldown is suppressed", len(fake_notifier.sent) == 1,
      f"notifier.sent={len(fake_notifier.sent)}")

time.sleep(0.4)
handler.process("cam_a", frame_idx=3, count=22, density=5.2)  # cooldown expired, should fire
check("alert after cooldown expiry fires again", len(fake_notifier.sent) == 2,
      f"notifier.sent={len(fake_notifier.sent)}")

alerts_in_db = database.recent_alerts("cam_a")
check("only non-suppressed alerts were logged to DB", len(alerts_in_db) == 2,
      f"db rows={len(alerts_in_db)}")


# ---------------------------------------------------------------------------
print("\n=== Test 4: Database round trip ===")
database.insert_detection("cam_b", {"count": 5, "avg_count": 4.5, "density": 1.2,
                                     "occupancy_pct": 33.3, "alert": False})
rows = database.recent_detections("cam_b")
check("detection round-trips through SQLite", len(rows) == 1 and rows[0][1] == 5,
      f"rows={rows}")


# ---------------------------------------------------------------------------
print(f"\n=== Summary: {results['pass']} passed, {results['fail']} failed ===")
sys.exit(1 if results["fail"] else 0)