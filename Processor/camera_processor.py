import threading

from processors.video_processor import VideoProcessor


class CameraProcessor:
    """Manages LIVE monitoring across multiple cameras at once. Each camera
    gets its own VideoProcessor (already configured with that camera's own
    detector instance/thresholds) running in its own thread, since live
    sources run indefinitely and in parallel. For offline/recorded-file
    processing, use BatchProcessor instead."""

    def __init__(self):
        self._processors = {}   # camera_name -> VideoProcessor
        self._threads = {}      # camera_name -> Thread

    def add_camera(self, camera_name, source, detector, output_path=None,
                    frame_stride=5, alert_callback=None, result_callback=None):
        """Register a camera. Call before start_camera()/start_all()."""
        if camera_name in self._processors:
            raise ValueError(f"Camera '{camera_name}' is already registered")
        self._processors[camera_name] = VideoProcessor(
            camera_name=camera_name,
            source=source,
            detector=detector,
            output_path=output_path,
            frame_stride=frame_stride,
            alert_callback=alert_callback,
            result_callback=result_callback,
            is_live=True,
        )

    def start_camera(self, camera_name, display=False):
        if camera_name not in self._processors:
            raise KeyError(f"No camera registered as '{camera_name}'")
        if camera_name in self._threads and self._threads[camera_name].is_alive():
            return  # already running

        thread = threading.Thread(target=self._run_safely,
                                   args=(camera_name, display), daemon=True)
        self._threads[camera_name] = thread
        thread.start()

    def start_all(self, display=False):
        for camera_name in self._processors:
            self.start_camera(camera_name, display=display)

    def _run_safely(self, camera_name, display):
        processor = self._processors[camera_name]
        try:
            processor.run(display=display)
        except Exception as exc:
            print(f"[{camera_name}] Crashed: {exc}")

    def stop_camera(self, camera_name):
        processor = self._processors.get(camera_name)
        if processor:
            processor.stop()

    def stop_all(self):
        for processor in self._processors.values():
            processor.stop()

    def join_all(self):
        """Block until every camera thread exits (Ctrl+C triggers stop_all)."""
        for thread in self._threads.values():
            thread.join()

    def is_camera_running(self, camera_name):
        thread = self._threads.get(camera_name)
        return thread is not None and thread.is_alive()