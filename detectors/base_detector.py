import cv2
import numpy as np
from abc import ABC, abstractmethod
from collections import deque

class BaseDetector(ABC):
    def __init__(self, person_class_id=0, conf_threshold=0.25,
                 count_threshold=15, density_threshold=None,
                 roi=None, smoothing_window=5, imgsz=1280,
                 max_capacity=None):
        if not (0.0 < conf_threshold <= 1.0):
            raise ValueError(f"conf_threshold must be in (0, 1], got {conf_threshold}")
        if count_threshold <= 0:
            raise ValueError(f"count_threshold must be > 0, got {count_threshold}")
        if smoothing_window <= 0:
            raise ValueError(f"smoothing_window must be > 0, got {smoothing_window}")
        if max_capacity is not None and max_capacity <= 0:
            raise ValueError(f"max_capacity must be > 0 if set, got {max_capacity}")

        self.person_class_id = person_class_id
        self.conf_threshold = conf_threshold
        self.count_threshold = count_threshold
        self.density_threshold = density_threshold
        self.roi = np.array(roi, dtype=np.int32) if roi else None
        self.history = deque(maxlen=smoothing_window)
        self.imgsz = imgsz
        self.max_capacity = max_capacity

    def __repr__(self):
        return (f"{self.__class__.__name__}(count_threshold={self.count_threshold}, "
                f"density_threshold={self.density_threshold}, "
                f"max_capacity={self.max_capacity})")

    @abstractmethod
    def detect_people(self, frame):
        """Each backend (YOLO, SAHI, ...) implements
        this differently — everything else in this class is shared."""
        raise NotImplementedError

    def warmup(self):
        """Run one dummy inference so model init cost doesn't land on the
        first real frame."""
        dummy = np.zeros((self.imgsz, self.imgsz, 3), dtype=np.uint8)
        self.detect_people(dummy)

    def _point_in_roi(self, point):
        if self.roi is None:
            return True
        return cv2.pointPolygonTest(self.roi, point, False) >= 0

    def set_roi(self, roi):
        """Update the monitored zone without reloading the model."""
        self.roi = np.array(roi, dtype=np.int32) if roi else None

    def reset(self):
        """Clear rolling history. Call before processing a new video/stream."""
        self.history.clear()

    def compute_density(self, num_people, frame_shape):
        h, w = frame_shape[:2]
        area_mp = (h * w) / 1_000_000
        return num_people / area_mp if area_mp > 0 else 0.0

    def calculate_occupancy(self, person_count):
        """Input: number of people -> Output: occupancy percentage (0-100),
        or None if max_capacity was never set."""
        if not self.max_capacity or self.max_capacity <= 0:
            return None
        occupancy_pct = (person_count / self.max_capacity) * 100
        return round(min(max(occupancy_pct, 0.0), 100.0), 1)

    def is_overcrowded(self, num_people, frame_shape):
        self.history.append(num_people)
        avg_count = sum(self.history) / len(self.history)
        alert = (avg_count >= self.count_threshold)
        density = self.compute_density(num_people, frame_shape)
        if self.density_threshold is not None:
            alert = alert or (density >= self.density_threshold)
        return alert, avg_count, density

    def get_stats(self, num_people, frame_shape):
        """Convenience wrapper: runs is_overcrowded + calculate_occupancy
        and returns everything as one dict (handy for logging/JSON/APIs)."""
        alert, avg_count, density = self.is_overcrowded(num_people, frame_shape)
        occupancy = self.calculate_occupancy(avg_count)
        return {
            "count": num_people,
            "avg_count": round(avg_count, 1),
            "density": round(density, 2),
            "occupancy_pct": occupancy,
            "alert": alert,
        }