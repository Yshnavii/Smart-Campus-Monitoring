import time
import cv2

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
        self.alert_callback = alert_callback      # fires once when alert state turns True
        self.result_callback = result_callback    # fires on every processed frame
        self.is_live = is_live                    # True: reconnect on drop (camera). False: stop at EOF (file).
        self._running = False

    def _open_capture(self):
        # Allow plain integers ("0", "1") for local webcams
        cap_source = int(self.source) if str(self.source).isdigit() else self.source
        cap = cv2.VideoCapture(cap_source)
        if not cap.isOpened():
            raise IOError(f"Could not open video source for {self.camera_name}: {self.source}")
        return cap

    def run(self, display=False):
        """Blocking loop — run in its own thread/process per camera, or
        call directly (blocking) for a single recorded file."""
        cap = self._open_capture()
        self.detector.reset()

        writer = None
        if self.output_path:
            fps = cap.get(cv2.CAP_PROP_FPS) or 25
            w = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH))
            h = int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT))
            writer = cv2.VideoWriter(self.output_path, cv2.VideoWriter_fourcc(*"mp4v"), fps, (w, h))

        self._running = True
        frame_idx = 0
        last_alert_state = False
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
                        cap = self._open_capture()
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

                    if alert and not last_alert_state and self.alert_callback:
                        self.alert_callback(self.camera_name, frame_idx, len(boxes), density)

                    last_alert_state = alert

                annotated = draw_overlay(frame, boxes, alert, avg_count, density, occupancy)

                if writer:
                    writer.write(annotated)
                if display:
                    cv2.imshow(self.camera_name, annotated)
                    if cv2.waitKey(1) & 0xFF == ord("q"):
                        break
        finally:
            cap.release()
            if writer:
                writer.release()
            if display:
                cv2.destroyWindow(self.camera_name)
            print(f"[{self.camera_name}] Stopped after {frame_idx} frames.")

    def stop(self):
        self._running = False