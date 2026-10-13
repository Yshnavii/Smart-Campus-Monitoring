import os
import glob

from processors.video_processor import VideoProcessor


class BatchProcessor:
    """Processes a set of pre-recorded video files (not live streams), one
    at a time, using the same VideoProcessor engine as CameraProcessor.
    Uses is_live=False so each file stops cleanly at its own end rather
    than being treated as a dropped connection to reconnect to. Collects
    per-file and overall summary stats once every file finishes."""

    def __init__(self, detector_factory, output_dir=None, frame_stride=5):
        """
        detector_factory: a zero-arg callable returning a FRESH detector
        instance per file, so rolling `history` smoothing from one file
        never leaks into the next file's results.
        """
        self.detector_factory = detector_factory
        self.output_dir = output_dir
        self.frame_stride = frame_stride
        self.summaries = {}   # video_path -> summary dict

    def _build_processor(self, video_path):
        video_name = os.path.splitext(os.path.basename(video_path))[0]

        output_path = None
        if self.output_dir:
            os.makedirs(self.output_dir, exist_ok=True)
            output_path = os.path.join(self.output_dir, f"{video_name}_annotated.mp4")

        stats = {"peak_count": 0, "peak_occupancy": 0.0, "alert_count": 0, "frames_processed": 0}

        def result_callback(camera_name, result):
            stats["frames_processed"] += 1
            stats["peak_count"] = max(stats["peak_count"], result["count"])
            if result["occupancy_pct"] is not None:
                stats["peak_occupancy"] = max(stats["peak_occupancy"], result["occupancy_pct"])

        def alert_callback(camera_name, frame_idx, count, density):
            stats["alert_count"] += 1
            print(f"[{video_name}] ALERT at frame {frame_idx}: {count} people, density={density:.2f}")

        processor = VideoProcessor(
            camera_name=video_name,
            source=video_path,
            detector=self.detector_factory(),
            output_path=output_path,
            frame_stride=self.frame_stride,
            alert_callback=alert_callback,
            result_callback=result_callback,
            is_live=False,
        )
        return processor, stats

    def process_file(self, video_path):
        processor, stats = self._build_processor(video_path)
        processor.run(display=False)
        self.summaries[video_path] = stats
        return stats

    def process_files(self, video_paths):
        for video_path in video_paths:
            print(f"Processing: {video_path}")
            self.process_file(video_path)
        return self.summaries

    def process_folder(self, folder_path, extensions=(".mp4", ".avi", ".mov")):
        video_paths = []
        for ext in extensions:
            video_paths.extend(glob.glob(os.path.join(folder_path, f"*{ext}")))
        return self.process_files(sorted(video_paths))

    def print_summary(self):
        for video_path, stats in self.summaries.items():
            print(f"{video_path}: peak_count={stats['peak_count']} "
                  f"peak_occupancy={stats['peak_occupancy']:.1f}% "
                  f"alerts={stats['alert_count']} frames={stats['frames_processed']}")