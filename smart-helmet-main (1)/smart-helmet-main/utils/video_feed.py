import cv2
import threading
import time
import numpy as np
from models.yolo import YOLOStream
from models.depth import DepthStream
from utils.proximity_analyzer import ProximityAnalyzer

class VideoFeed:
    def __init__(self, camera_index=None):
        self.yolo_stream = YOLOStream()
        self.depth_stream = DepthStream()
        self.proximity_analyzer = ProximityAnalyzer()
        
        self.cap = None
        self.camera_index = camera_index
        self.is_synthetic_camera = False
        
        self.running = False
        self.frame_lock = threading.Lock()
        self.processed_lock = threading.Lock()
        
        self.raw_frame = None
        self.yolo_jpeg = None
        self.depth_jpeg = None
        self.current_proximity = 'SAFE'
        
        self._init_camera()

    def _init_camera(self):
        """Try camera indices (0, then 1) or fall back to synthetic feed if no camera is available."""
        candidate_indices = [self.camera_index] if self.camera_index is not None else [0, 1]
        
        for idx in candidate_indices:
            print(f"[CAMERA] Attempting to open camera index {idx}...")
            cap = cv2.VideoCapture(idx, cv2.CAP_DSHOW) if hasattr(cv2, 'CAP_DSHOW') else cv2.VideoCapture(idx)
            if cap is not None and cap.isOpened():
                ret, test_frame = cap.read()
                if ret and test_frame is not None:
                    print(f"[CAMERA] Successfully opened camera index {idx}")
                    self.cap = cap
                    self.camera_index = idx
                    self.is_synthetic_camera = False
                    return
                cap.release()

        print("[CAMERA] No physical webcam detected. Enabling Synthetic Demo Camera feed.")
        self.is_synthetic_camera = True

    def _create_synthetic_frame(self, frame_count):
        """Generate an animated synthetic test frame simulating road scenery with moving obstacles."""
        frame = np.zeros((480, 640, 3), dtype=np.uint8)
        # Background: Sky & Road
        frame[:240, :] = [180, 130, 70]   # Sky (BGR)
        frame[240:, :] = [50, 50, 50]     # Road (BGR)
        
        # Road lane lines
        cv2.line(frame, (320, 240), (100, 480), (255, 255, 255), 3)
        cv2.line(frame, (320, 240), (540, 480), (255, 255, 255), 3)
        
        # Moving simulated vehicle/pedestrian
        t = (frame_count % 120) / 120.0
        # Simulates approaching object
        size = int(40 + t * 90)
        center_x = int(320 + np.sin(frame_count * 0.05) * 60)
        center_y = int(240 + t * 180)
        
        # Draw vehicle body (Blue car box)
        x1 = max(10, center_x - size)
        y1 = max(10, center_y - int(size * 0.7))
        x2 = min(630, center_x + size)
        y2 = min(470, center_y + int(size * 0.7))
        
        cv2.rectangle(frame, (x1, y1), (x2, y2), (0, 0, 220), -1)
        cv2.putText(frame, "SIMULATED VEHICLE", (x1, y1 - 8), cv2.FONT_HERSHEY_SIMPLEX, 0.5, (0, 255, 255), 2)
        
        # Overlay timestamp/info
        cv2.putText(frame, f"SMART HELMET DEMO FEED | Frame: {frame_count}", (15, 30),
                    cv2.FONT_HERSHEY_SIMPLEX, 0.6, (255, 255, 255), 2)
        return frame

    def start_capture(self):
        """Start the background frame capture and inference pipeline threads."""
        if self.running:
            return
            
        self.running = True
        self.capture_thread = threading.Thread(target=self._capture_worker, daemon=True)
        self.process_thread = threading.Thread(target=self._processing_worker, daemon=True)
        
        self.capture_thread.start()
        self.process_thread.start()
        print("[PIPELINE] Video capture and processing workers started")

    def _capture_worker(self):
        """Capture raw frames at fixed rate."""
        frame_counter = 0
        while self.running:
            if not self.is_synthetic_camera and self.cap is not None:
                ret, frame = self.cap.read()
                if ret and frame is not None:
                    with self.frame_lock:
                        self.raw_frame = frame
                else:
                    time.sleep(0.01)
            else:
                frame_counter += 1
                synthetic_frame = self._create_synthetic_frame(frame_counter)
                with self.frame_lock:
                    self.raw_frame = synthetic_frame
                time.sleep(0.033)  # ~30 fps for demo

            time.sleep(0.005)

    def _processing_worker(self):
        """Single-pass inference worker: runs YOLO and Depth-Anything once per frame."""
        last_processed_time = 0
        while self.running:
            current_frame = None
            with self.frame_lock:
                if self.raw_frame is not None:
                    current_frame = self.raw_frame.copy()

            if current_frame is None:
                time.sleep(0.01)
                continue

            try:
                # 1. Run YOLO object detection
                annotated_yolo, boxes = self.yolo_stream.detect(current_frame)

                # 2. Run Depth-Anything estimation
                depth_colored, depth_normalized = self.depth_stream.predict_depth(current_frame)

                # 3. Calculate Proximity status
                proximity = self.proximity_analyzer.get_proximity_status(depth_normalized, boxes)

                # 4. Encode JPEGs once for both streams
                _, yolo_buf = cv2.imencode('.jpg', annotated_yolo, [cv2.IMWRITE_JPEG_QUALITY, 80])
                _, depth_buf = cv2.imencode('.jpg', depth_colored, [cv2.IMWRITE_JPEG_QUALITY, 80])

                with self.processed_lock:
                    self.yolo_jpeg = yolo_buf.tobytes()
                    self.depth_jpeg = depth_buf.tobytes()
                    self.current_proximity = proximity

            except Exception as e:
                print(f"[PIPELINE ERROR] Inference failure: {e}")

            time.sleep(0.01)

    def get_proximity_status(self):
        with self.processed_lock:
            return self.current_proximity

    def generate_yolo_feed(self):
        if not self.running:
            self.start_capture()

        while self.running:
            with self.processed_lock:
                jpeg = self.yolo_jpeg

            if jpeg is None:
                time.sleep(0.02)
                continue

            yield (b'--frame\r\n'
                   b'Content-Type: image/jpeg\r\n\r\n' + jpeg + b'\r\n')
            time.sleep(0.03)

    def generate_depth_feed(self):
        if not self.running:
            self.start_capture()

        while self.running:
            with self.processed_lock:
                jpeg = self.depth_jpeg

            if jpeg is None:
                time.sleep(0.02)
                continue

            yield (b'--frame\r\n'
                   b'Content-Type: image/jpeg\r\n\r\n' + jpeg + b'\r\n')
            time.sleep(0.03)

    def stop_capture(self):
        self.running = False
        if self.cap is not None:
            self.cap.release()
            self.cap = None
        print("[PIPELINE] Video capture stopped")