"""
Smart Helmet Unified Launcher
Launches the Flask AI dashboard & video processing pipeline.
"""
import sys
import os

project_dir = os.path.join(os.path.dirname(__file__), "smart-helmet-main (1)", "smart-helmet-main")
if os.path.exists(project_dir):
    os.chdir(project_dir)
    sys.path.insert(0, project_dir)

if __name__ == "__main__":
    from app import app, video_feed, ser, read_sensor_data_worker, simulated_telemetry_worker, serial_write_worker
    import threading

    if ser and ser.is_open:
        threading.Thread(target=read_sensor_data_worker, daemon=True).start()

    threading.Thread(target=simulated_telemetry_worker, daemon=True).start()
    threading.Thread(target=serial_write_worker, daemon=True).start()

    video_feed.start_capture()

    print("\n" + "="*60)
    print("🚀 SMART HELMET AI SAFETY SYSTEM RUNNING")
    print("👉 Open Dashboard: http://127.0.0.1:5000")
    print("="*60 + "\n")

    app.run(host='0.0.0.0', port=5000, threaded=True, use_reloader=False)
