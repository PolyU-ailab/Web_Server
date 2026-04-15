import socket
import threading
import time
from collections import deque
from flask import Flask, Response
from waitress import serve

app = Flask(__name__)

# --- Configuration ---
# Add your ports here. The key is the URL slug, the value is the UDP port.
CAM_CONFIG = {
    "cam1": 5005,
    "cam2": 5006,
    "cam3": 5007
}

# Dictionary to hold a deque for each camera
# Example: {'cam1': deque([...]), 'cam2': deque([...])}
buffers = {name: deque(maxlen=5) for name in CAM_CONFIG}

def udp_receiver(name, port):
    """Background thread to catch UDP packets for a specific camera."""
    udp_socket = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    udp_socket.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    udp_socket.setsockopt(socket.SOL_SOCKET, socket.SO_RCVBUF, 1048576)
    
    try:
        udp_socket.bind(("0.0.0.0", port))
        udp_socket.settimeout(1.0)
        print(f"[INFO] Thread started: {name} listening on UDP {port}")
    except Exception as e:
        print(f"[ERROR] Could not bind {name} to port {port}: {e}")
        return

    while True:
        try:
            data, addr = udp_socket.recvfrom(65536)
            if data:
                buffers[name].append(data)
        except socket.timeout:
            continue
        except Exception as e:
            print(f"[ERROR] {name} receiver error: {e}")
            time.sleep(0.1)

def generate_frames(cam_name):
    """Generator for a specific camera buffer."""
    while True:
        # Check if the requested camera exists and has data
        if cam_name in buffers and buffers[cam_name]:
            frame = buffers[cam_name][-1]
            yield (b'--frame\r\n'
                   b'Content-Type: image/jpeg\r\n\r\n' + frame + b'\r\n')
            time.sleep(0.03) # Limit to ~30 FPS
        else:
            time.sleep(0.1) # Wait for first frame to arrive

@app.route('/<cam_id>')
def video_feed(cam_id):
    """
    Dynamic route to handle /cam1, /cam2, etc.
    """
    if cam_id not in CAM_CONFIG:
        return f"Camera {cam_id} not found", 404
        
    return Response(generate_frames(cam_id),
                    mimetype='multipart/x-mixed-replace; boundary=frame')

if __name__ == '__main__':
    # 1. Start a thread for every camera defined in CAM_CONFIG
    for name, port in CAM_CONFIG.items():
        thread = threading.Thread(target=udp_receiver, args=(name, port), daemon=True)
        thread.start()

    # 2. Start Waitress Production Server
    print(f"[INFO] Production server active on ports {list(CAM_CONFIG.values())}")
    print("[INFO] Routes: " + ", ".join([f"http://localhost:5000/{k}" for k in CAM_CONFIG.keys()]))
    
    # Increase threads to handle multiple simultaneous viewers across different cams
    serve(app, host='0.0.0.0', port=5000, threads=20, channel_timeout=3600)
