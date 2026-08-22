import cv2
import torch
from ultralytics import YOLO

class YOLOStream:
    def __init__(self, model_path="yolov8n.pt"):
        self.device = 'cuda' if torch.cuda.is_available() else 'cpu'
        print(f"[YOLO] Initializing YOLOv8 ({model_path}) on device: {self.device}")
        self.model = YOLO(model_path)

    def detect(self, frame):
        """
        Run inference on frame.
        Returns:
            annotated_frame (BGR image for display),
            boxes (list of [x1, y1, x2, y2] integers)
        """
        rgb_frame = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
        results = self.model(rgb_frame, verbose=False, device=self.device)

        boxes = []
        if results and results[0].boxes is not None:
            for box in results[0].boxes.data:
                x1, y1, x2, y2 = map(int, box[:4])
                boxes.append((x1, y1, x2, y2))

        # Annotate and convert back to BGR for OpenCV / web streaming
        annotated_bgr = cv2.cvtColor(results[0].plot(), cv2.COLOR_RGB2BGR)
        return annotated_bgr, boxes
