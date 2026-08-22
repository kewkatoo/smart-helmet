import atexit
import json
import math
import os
import queue
import threading
import time
from flask import Flask, Response, render_template, jsonify, request
import serial
import serial.tools.list_ports

from utils.video_feed import VideoFeed

app = Flask(__name__)
video_feed = VideoFeed()

# ==========================================
# SERIAL & SENSOR STATE
# ==========================================
BAUD_RATE = 115200  # Standardized to match ESP32 smart_helmet.ino
DEFAULT_PORTS = ['COM7', 'COM3', 'COM4', 'COM5', '/dev/ttyUSB0', '/dev/ttyACM0']

sensor_data_lock = threading.Lock()
sensor_data = {
    'latitude': "12.9716",
    'longitude': "77.5946",
    'speed': "0.0",
    'mq3_value': "120",
    'hardware_connected': False,
    'port_name': "None",
    'last_updated': time.time()
}

serial_write_queue = queue.Queue(maxsize=15)
ser = None
ser_lock = threading.Lock()

def initialize_serial():
    """Scan and connect to the best available serial port, or return None."""
    global ser
    # Check available ports
    available_ports = [p.device for p in serial.tools.list_ports.comports()]
    print(f"[SERIAL SCAN] Detected system serial ports: {available_ports}")

    # Prioritize candidate list
    candidate_ports = available_ports + [p for p in DEFAULT_PORTS if p not in available_ports]

    for port in candidate_ports:
        try:
            print(f"[SERIAL] Attempting connection to {port} @ {BAUD_RATE} baud...")
            connection = serial.Serial(port, BAUD_RATE, timeout=0.1, write_timeout=0.1)
            if connection.is_open:
                print(f"[SERIAL SUCCESS] Connected to ESP32 on {port}")
                with sensor_data_lock:
                    sensor_data['hardware_connected'] = True
                    sensor_data['port_name'] = port
                return connection
        except (serial.SerialException, OSError) as e:
            # Port not available
            continue

    print("[SERIAL] No physical ESP32 connected. Running in SIMULATED TELEMETRY mode.")
    with sensor_data_lock:
        sensor_data['hardware_connected'] = False
        sensor_data['port_name'] = "Simulated / Disconnected"
    return None

ser = initialize_serial()

def read_sensor_data_worker():
    """Thread for reading live sensor lines from physical ESP32."""
    global ser, sensor_data
    print("[THREAD] Live serial reader worker started")
    while True:
        if ser and ser.is_open:
            try:
                if ser.in_waiting > 0:
                    raw_line = ser.readline().decode('utf-8', errors='ignore').strip()
                    if not raw_line:
                        continue

                    with sensor_data_lock:
                        if raw_line.startswith("GPS:"):
                            parts = raw_line[4:].split(",")
                            if len(parts) >= 3:
                                sensor_data['latitude'] = parts[0]
                                sensor_data['longitude'] = parts[1]
                                sensor_data['speed'] = parts[2]
                                sensor_data['last_updated'] = time.time()
                                print(f"[GPS LIVE] Lat: {parts[0]}, Lon: {parts[1]}, Speed: {parts[2]} km/h")
                        elif raw_line.startswith("MQ3:"):
                            mq3_val = raw_line[4:].strip()
                            sensor_data['mq3_value'] = mq3_val
                            sensor_data['last_updated'] = time.time()
                            print(f"[MQ3 LIVE] Value: {mq3_val}")
            except Exception as e:
                print(f"[SERIAL READ ERROR] {e}")
                time.sleep(0.5)
        time.sleep(0.02)

def simulated_telemetry_worker():
    """Simulate realistic GPS coordinates, speed changes, and MQ-3 values when hardware is absent."""
    global sensor_data
    print("[THREAD] Simulated telemetry generator started")
    base_lat = 12.971598
    base_lon = 77.594566
    angle = 0.0

    while True:
        with sensor_data_lock:
            is_connected = sensor_data['hardware_connected']

        # Only simulate when hardware is disconnected
        if not is_connected:
            angle += 0.04
            sim_lat = base_lat + 0.003 * math.sin(angle)
            sim_lon = base_lon + 0.003 * math.cos(angle)
            sim_speed = round(max(0.0, 35.0 + 15.0 * math.sin(angle * 1.5) + (angle % 5)), 1)
            sim_mq3 = int(140 + 20 * math.sin(angle * 0.8))

            with sensor_data_lock:
                sensor_data.update({
                    'latitude': f"{sim_lat:.6f}",
                    'longitude': f"{sim_lon:.6f}",
                    'speed': str(sim_speed),
                    'mq3_value': str(sim_mq3),
                    'last_updated': time.time()
                })

        time.sleep(1.0)

def serial_write_worker():
    """Thread for writing proximity commands to physical serial port (non-blocking)."""
    global ser
    print("[THREAD] Serial write worker started")
    while True:
        try:
            command = serial_write_queue.get(timeout=0.5)
            if ser and ser.is_open:
                try:
                    ser.write(command.encode('utf-8'))
                    ser.flush()
                except Exception as err:
                    print(f"[SERIAL WRITE ERROR] {err}")
            serial_write_queue.task_done()
        except queue.Empty:
            pass

# ==========================================
# FLASK WEB ROUTES
# ==========================================
@app.route('/')
def index():
    return render_template('index.html')

@app.route('/yolo_feed')
def yolo_feed():
    return Response(video_feed.generate_yolo_feed(),
                    mimetype='multipart/x-mixed-replace; boundary=frame')

@app.route('/depth_feed')
def depth_feed():
    return Response(video_feed.generate_depth_feed(),
                    mimetype='multipart/x-mixed-replace; boundary=frame')

@app.route('/proximity_status')
def proximity_status():
    proximity_value = video_feed.get_proximity_status()
    # Non-blocking queue put to avoid deadlocking Flask threads
    try:
        serial_write_queue.put_nowait(f"PROXIMITY:{proximity_value}\n")
    except queue.Full:
        pass
    return proximity_value

@app.route('/sensor_data')
def get_sensor_data():
    with sensor_data_lock:
        current_data = sensor_data.copy()
    return jsonify(current_data)

@app.route('/system_status')
def get_system_status():
    with sensor_data_lock:
        is_hw = sensor_data['hardware_connected']
        port = sensor_data['port_name']
    
    return jsonify({
        'status': 'online',
        'camera_synthetic': video_feed.is_synthetic_camera,
        'camera_index': video_feed.camera_index,
        'hardware_connected': is_hw,
        'serial_port': port,
        'proximity': video_feed.get_proximity_status()
    })

# ==========================================
# CLEANUP & INITIALIZATION
# ==========================================
def cleanup():
    print("[CLEANUP] Stopping video feed & serial connections...")
    video_feed.stop_capture()
    global ser
    if ser and ser.is_open:
        ser.close()
    print("[CLEANUP] Cleanup complete.")

atexit.register(cleanup)

if __name__ == '__main__':
    # Launch worker threads
    if ser and ser.is_open:
        threading.Thread(target=read_sensor_data_worker, daemon=True).start()
    
    threading.Thread(target=simulated_telemetry_worker, daemon=True).start()
    threading.Thread(target=serial_write_worker, daemon=True).start()

    # Pre-start video feed capture
    video_feed.start_capture()

    print("[MAIN] Starting Smart Helmet Server on http://127.0.0.1:5000 ...")
    app.run(host='0.0.0.0', port=5000, threaded=True, use_reloader=False)