"""
Entry point for offline processing of recorded video files (not live
cameras — see main.py for that). Runs every file through BatchProcessor
and prints a summary when done.

Usage:
    python run_batch.py --folder recordings/
    python run_batch.py --files a.mp4 b.mp4 c.mp4 --output-dir annotated/
    python run_batch.py --folder recordings/ --sahi --count-threshold 20
"""
import argparse

from processors.batch_processor import BatchProcessor
from detectors.yolo_detector import OvercrowdingDetector
from detectors.sahi_detector import SAHIOvercrowdingDetector
from config.settings import MODEL_PATH


def main():
    parser = argparse.ArgumentParser(description="Batch-process recorded videos for overcrowding")
    source_group = parser.add_mutually_exclusive_group(required=True)
    source_group.add_argument("--folder", help="Folder of video files to process")
    source_group.add_argument("--files", nargs="+", help="Specific video file paths to process")

    parser.add_argument("--output-dir", default="batch_output",
                         help="Where to write annotated output videos (default: batch_output)")
    parser.add_argument("--count-threshold", type=int, default=15)
    parser.add_argument("--density-threshold", type=float, default=None)
    parser.add_argument("--max-capacity", type=int, default=None)
    parser.add_argument("--frame-stride", type=int, default=5)
    parser.add_argument("--sahi", action="store_true", help="Use SAHI slicing inference")
    args = parser.parse_args()

    def detector_factory():
        kwargs = dict(
            model_path=MODEL_PATH,
            count_threshold=args.count_threshold,
            density_threshold=args.density_threshold,
            max_capacity=args.max_capacity,
        )
        return SAHIOvercrowdingDetector(**kwargs) if args.sahi else OvercrowdingDetector(**kwargs)

    bp = BatchProcessor(detector_factory=detector_factory,
                         output_dir=args.output_dir,
                         frame_stride=args.frame_stride)

    if args.folder:
        bp.process_folder(args.folder)
    else:
        bp.process_files(args.files)

    print("\n=== Batch summary ===")
    bp.print_summary()


if __name__ == "__main__":
    main()