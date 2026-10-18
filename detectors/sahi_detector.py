import numpy as np
from sahi import AutoDetectionModel
from sahi.predict import get_sliced_prediction

from detectors.base_detector import BaseDetector


class SAHIOvercrowdingDetector(BaseDetector):
    """SAHI (Slicing Aided Hyper Inference) detector. Slices the frame into
    overlapping tiles and runs YOLO on each tile before merging results back
    into full-frame coordinates. Slower than plain YOLO, but catches small,
    far-away people in dense or wide-angle scenes that a single full-frame
    pass would miss."""

    def __init__(self, model_path="yolov8n.pt", slice_height=512, slice_width=512,
                 overlap_height_ratio=0.2, overlap_width_ratio=0.2, device="cpu",
                 **kwargs):
        super().__init__(**kwargs)
        self.slice_height = slice_height
        self.slice_width = slice_width
        self.overlap_height_ratio = overlap_height_ratio
        self.overlap_width_ratio = overlap_width_ratio
        self.detection_model = AutoDetectionModel.from_pretrained(
            model_type="ultralytics",
            model_path=model_path,
            confidence_threshold=self.conf_threshold,
            device=device,
        )

    def detect_people(self, frame):
        result = get_sliced_prediction(
            frame,
            self.detection_model,
            slice_height=self.slice_height,
            slice_width=self.slice_width,
            overlap_height_ratio=self.overlap_height_ratio,
            overlap_width_ratio=self.overlap_width_ratio,
            verbose=0,
        )

        boxes = []
        for pred in result.object_prediction_list:
            if pred.category.id != self.person_class_id:
                continue
            bbox = pred.bbox
            cx = (bbox.minx + bbox.maxx) / 2
            cy = (bbox.miny + bbox.maxy) / 2
            if self._point_in_roi((cx, cy)):
                boxes.append((int(bbox.minx), int(bbox.miny), int(bbox.maxx), int(bbox.maxy)))
        return boxes