import numpy as np
from ultralytics import YOLO

from detectors.base_detector import BaseDetector


class OvercrowdingDetector(BaseDetector):
    def __init__(self, model_path = "yolov8n.pt", **kwargs):
        super().__init__(**kwargs)
        self.model = YOLO(model_path)

    def detect_people(self, frame):
        results = self.model(frame, conf=self.conf_threshold, imgsz=self.imgsz,
                              classes=[self.person_class_id], verbose=False)[0]
        boxes = []
        for box in results.boxes:
            x1, y1, x2, y2 = box.xyxy[0].cpu().numpy()
            cx, cy = (x1 + x2) / 2, (y1 + y2) / 2
            if self._point_in_roi((cx, cy)):
                boxes.append((int(x1), int(y1), int(x2), int(y2)))
        return boxes