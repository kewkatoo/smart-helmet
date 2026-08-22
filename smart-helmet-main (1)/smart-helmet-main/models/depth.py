import cv2
import torch
from transformers import AutoImageProcessor, AutoModelForDepthEstimation
import numpy as np

class DepthStream:
    def __init__(self, model_id="LiheYoung/depth-anything-small-hf"):
        self.device = 'cuda' if torch.cuda.is_available() else 'cpu'
        print(f"[DEPTH] Initializing Depth-Anything on device: {self.device}")
        self.processor = AutoImageProcessor.from_pretrained(model_id)
        self.model = AutoModelForDepthEstimation.from_pretrained(model_id).to(self.device)
        self.model.eval()

    def predict_depth(self, frame):
        """
        Estimate depth from an input frame.
        Returns:
            depth_colored: 3-channel BGR heatmap for visual display (INFERNO colormap)
            depth_normalized: 1-channel uint8 array (0-255) for proximity calculation
        """
        image = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
        inputs = self.processor(images=image, return_tensors="pt").to(self.model.device)
        
        with torch.no_grad():
            outputs = self.model(**inputs)
        
        depth = self.processor.post_process_depth_estimation(
            outputs, target_sizes=[(frame.shape[0], frame.shape[1])]
        )
        predicted_depth = depth[0]["predicted_depth"].cpu().numpy()
        
        max_val = np.max(predicted_depth)
        if max_val > 0:
            depth_normalized = (predicted_depth * 255.0 / max_val).astype(np.uint8)
        else:
            depth_normalized = np.zeros(predicted_depth.shape, dtype=np.uint8)

        depth_colored = cv2.applyColorMap(depth_normalized, cv2.COLORMAP_INFERNO)
        return depth_colored, depth_normalized
