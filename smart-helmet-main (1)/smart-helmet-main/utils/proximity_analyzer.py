import numpy as np
from typing import List, Tuple

class ProximityAnalyzer:
    def __init__(self, danger_threshold: float = 160.0, warning_threshold: float = 100.0):
        # In Depth-Anything disparity maps (0-255), higher values = closer objects
        self.DANGER_THRESHOLD = danger_threshold
        self.WARNING_THRESHOLD = warning_threshold

    def get_proximity_status(self, depth_map: np.ndarray, boxes: List[Tuple[int, int, int, int]]) -> str:
        """
        Get overall proximity status based on detected objects' depth regions.
        
        Args:
            depth_map: Normalized depth map (0-255), where higher values denote closer objects
            boxes: List of bounding boxes (x1, y1, x2, y2)
        
        Returns:
            'DANGER', 'WARNING', or 'SAFE'
        """
        if depth_map is None or not boxes:
            return 'SAFE'
            
        avg_depths = []
        h, w = depth_map.shape[:2]

        for box in boxes:
            x1, y1, x2, y2 = box
            # Clamp coordinates to frame boundaries
            x1 = max(0, min(w - 1, x1))
            x2 = max(0, min(w, x2))
            y1 = max(0, min(h - 1, y1))
            y2 = max(0, min(h, y2))

            if x2 > x1 and y2 > y1:
                region = depth_map[y1:y2, x1:x2]
                if region.size > 0:
                    avg_depths.append(float(np.mean(region)))
        
        if not avg_depths:
            return 'SAFE'
            
        # The closest object will have the highest depth intensity
        closest_intensity = max(avg_depths)

        if closest_intensity >= self.DANGER_THRESHOLD:
            return 'DANGER'
        elif closest_intensity >= self.WARNING_THRESHOLD:
            return 'WARNING'
        else:
            return 'SAFE'