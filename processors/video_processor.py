import os
import time
import cv2

from utils.snapshots import slugify
from utils.visualization import draw_overlay


class VideoProcessor:
    """Runs one detector against one video source (webcam index, video file,
    or RTSP URL) in a loop: reads frames, runs detection every `frame_stride`
    frames, draws the overlay, and optionally writes an output video and
    fires callbacks on results/alerts. Meant to be run in its own thread —
    one instance per camera, using a detector already configured with that
    camera's own thresholds (count_threshold, roi, max_capacity, etc.)."""

    def __init__(self, camera_name, source, detector, output_path=None,
                 frame_stride=5, alert_callback=None, result_callback=None,
                 is_live=True):
        self.camera_name = camera_name
        self.source = source
        self.detector = detector
        self.output_path = output_path
        self.frame_stride = frame_stride
        self.alert_callback = alert_callback      # fires on every detection while overcrowded (AlertHandler throttles it)
        self.result_callback = result_callback    # fires on every processed frame
        self.is_live = is_live                    # True: reconnect on drop (camera). False: stop at EOF (file).
        self._running = False

        # The dashboard sets SNAPSHOT_DIR when it starts main.py. Without it (plain
        # `python main.py`) no snapshots are written.
        snapshot_dir = os.getenv("SNAPSHOT_DIR", "")
        self._snapshot_path = (os.path.join(snapshot_dir, slugify(camera_name) + ".jpg")
                               if snapshot_dir else None)
        self._last_snapshot = 0.0

    def _save_snapshot(self, image):
        """Write the annotated frame for the dashboard, at most once per second."""
        if not self._snapshot_path or time.time() - self._last_snapshot < 1.0:
            return
        self._last_snapshot = time.time()
        try:
            h, w = image.shape[:2]
            if w > 960:
                image = cv2.resize(image, (960, int(h * 960 / w)))
            ok, buf = cv2.imencode(".jpg", image, [cv2.IMWRITE_JPEG_QUALITY, 70])
            if not ok:
                return
            tmp = self._snapshot_path + ".tmp"
            with open(tmp, "wb") as f:
                f.write(buf.tobytes())
            os.replace(tmp, self._snapshot_path)   # atomic: the browser never gets half a file
        except OSError:
            pass  # e.g. Windows briefly locking the file while it is being read; try again next second

    def _open_capture(self):
        # Allow plain integers ("0", "1") for local webcams
        cap_source = int(self.source) if str(self.source).isdigit() else self.source
        cap = cv2.VideoCapture(cap_source)
        if not cap.isOpened():
            raise IOError(f"Could not open video source for {self.camera_name}: {self.source}")
        return cap

    def _reconnect(self):
        """Keep trying to reopen a live source until it works or stop() is called."""
        while self._running:
            try:
                return self._open_capture()
            except IOError:
                print(f"[{self.camera_name}] Source unreachable, retrying in 5s...")
                time.sleep(5)
        return None

    def run(self, display=False):
        """Blocking loop — run in its own thread/process per camera, or
        call directly (blocking) for a single recorded file."""
        self._running = True
        # A live camera may be offline at startup: keep retrying. A file must open or fail loudly.
        cap = self._reconnect() if self.is_live else self._open_capture()
        if cap is None:
            return
        self.detector.reset()

        writer = None
        if self.output_path:
            fps = cap.get(cv2.CAP_PROP_FPS) or 25
            w = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH))
            h = int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT))
            writer = cv2.VideoWriter(self.output_path, cv2.VideoWriter_fourcc(*"mp4v"), fps, (w, h))

        frame_idx = 0
        boxes = []
        alert, avg_count, density, occupancy = False, 0.0, 0.0, None

        try:
            while self._running:
                ok, frame = cap.read()
                if not ok:
                    if self.is_live:
                        print(f"[{self.camera_name}] Stream dropped, reconnecting...")
                        time.sleep(2)
                        cap.release()
                        cap = self._reconnect()
                        if cap is None:
                            break  # stop() was called while waiting
                        continue
                    else:
                        break  # end of a finite file — done, not an error

                frame_idx += 1

                # Run detection only every `frame_stride` frames to save compute;
                # in-between frames reuse the last known boxes/alert state.
                if frame_idx % self.frame_stride == 0:
                    boxes = self.detector.detect_people(frame)
                    alert, avg_count, density = self.detector.is_overcrowded(len(boxes), frame.shape)
                    occupancy = self.detector.calculate_occupancy(avg_count)

                    if self.result_callback:
                        self.result_callback(self.camera_name, {
                            "count": len(boxes),
                            "avg_count": avg_count,
                            "density": density,
                            "occupancy_pct": occupancy,
                            "alert": alert,
                        })

                    # Called on every detection while overcrowded. AlertHandler's cooldown
                    # decides how often an email actually goes out.
                    if alert and self.alert_callback:
                        self.alert_callback(self.camera_name, frame_idx, len(boxes), density)

                annotated = draw_overlay(frame, boxes, alert, avg_count, density, occupancy)
                self._save_snapshot(annotated)

                if writer:
                    writer.write(annotated)
                if display:
                    cv2.imshow(self.camera_name, annotated)
                    if cv2.waitKey(1) & 0xFF == ord("q"):
                        break
        finally:
            if cap is not None:
                cap.release()
            if writer:
                writer.release()
            if display:
                cv2.destroyWindow(self.camera_name)
            print(f"[{self.camera_name}] Stopped after {frame_idx} frames.")

    def stop(self):
        self._running = False