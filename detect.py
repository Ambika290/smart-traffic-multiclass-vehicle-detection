import cv2
import numpy as np
import os
import sqlite3
import time
import requests  # Used to broadcast metrics to the live map server API
from ultralytics import YOLO

# Load the pretrained model
model = YOLO("yolov8n.pt")

# Vehicle class ID filters (2=car, 3=motorcycle, 5=bus, 7=truck)
VEHICLE_CLASSES = [2, 3, 5, 7]

# Database Setup: Create directory and SQLite connection for violation logging
os.makedirs("violations_snapshots", exist_ok=True)
db_conn = sqlite3.connect("traffic_violations.db")
db_cursor = db_conn.cursor()
db_cursor.execute("""
    CREATE TABLE IF NOT EXISTS violations (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        timestamp TEXT,
        lane_name TEXT,
        vehicle_type TEXT,
        snapshot_path TEXT
    )
""")
db_conn.commit()

# Geographic coordinate references for where your 4 cameras are physically installed in Bengaluru
LANE_GPS_LOCATIONS = {
    "Lane 1": {"lat": 12.9716, "lng": 77.5946, "road": "MG Road, Bengaluru"},
    "Lane 2": {"lat": 12.9279, "lng": 77.6271, "road": "Koramangala 80ft Rd"},
    "Lane 3": {"lat": 12.9784, "lng": 77.6408, "road": "Indiranagar 100ft Rd"},
    "Lane 4": {"lat": 12.9345, "lng": 77.6101, "road": "Hosur Road, Madiwala"}
}

# The address where your upcoming frontend dashboard web server will receive updates
LIVE_MAP_SERVER_API = "http://127.0.0"

# Traffic Signal Management Configuration
current_green_lane = "Lane 1"
next_green_lane = "Lane 1"
signal_state = "GREEN"  # Can be "GREEN", "YELLOW", or "RED"
last_signal_switch = time.time()

SIGNAL_CYCLE_TIME = 5.0     # Time to stay green before checking densities
YELLOW_DURATION = 2.0       # Duration of the yellow light transition phase

def process_lane_frame(frame, lane_name):
    global current_green_lane, next_green_lane, signal_state
    if frame is None:
        return 0, False, frame

    # Run standard YOLO detection directly on the raw frame
    results = model(frame, classes=VEHICLE_CLASSES, verbose=False)
    
    vehicle_count = 0
    ambulance_present = False

    # Process bounding boxes matching your threshold logic
    for box in results[0].boxes:
        x1, y1, x2, y2 = map(int, box.xyxy[0].tolist())
        conf = float(box.conf)
        cls_id = int(box.cls)
        
        # Calculate bounding box footprint
        width = x2 - x1
        height = y2 - y1
        aspect_ratio = width / height if height > 0 else 0
        box_area = width * height

        # Custom mapping rules for Indian roads
        if cls_id == 7 and aspect_ratio < 0.85:
            label = f"auto-rickshaw {conf:.2f}"
            color = (0, 165, 255)
            vehicle_count += 1
        elif cls_id == 5 and box_area < 45000:
            label = f"ambulance {conf:.2f}"
            color = (0, 0, 255)
            ambulance_present = True
            vehicle_count += 1
            
            # Log ambulance track snapshot
            if conf > 0.60:
                timestamp = time.strftime("%Y-%m-%d %H:%M:%S")
                snapshot_filename = f"violations_snapshots/{lane_name}_ambulance_{int(time.time())}.jpg"
                cv2.imwrite(snapshot_filename, frame)
                db_cursor.execute(
                    "INSERT INTO violations (timestamp, lane_name, vehicle_type, snapshot_path) VALUES (?, ?, ?, ?)",
                    (timestamp, lane_name, "Ambulance Pass", snapshot_filename)
                )
                db_conn.commit()
        elif cls_id == 3:
            label = f"motorcycle {conf:.2f}"
            color = (0, 255, 0)
            vehicle_count += 1
        else:
            label = f"{model.names[cls_id]} {conf:.2f}"
            color = (255, 0, 0)
            vehicle_count += 1

        # Render labels and bounding box lines onto the frame
        cv2.rectangle(frame, (x1, y1), (x2, y2), color, 2)
        cv2.putText(frame, label, (x1, y1 - 10),
                    cv2.FONT_HERSHEY_SIMPLEX, 0.5, color, 2)
        
    # Draw Lane Identifier header
    cv2.putText(frame, f"{lane_name} - Q: {vehicle_count}", (20, 40), cv2.FONT_HERSHEY_SIMPLEX, 0.8, (255, 255, 255), 2)
    
    # Draw physical rectangular signal housing
    cv2.rectangle(frame, (20, 60), (52, 160), (30, 30, 30), -1)
    cv2.rectangle(frame, (20, 60), (52, 160), (200, 200, 200), 1)
    
    # Default dim lamps values
    red_color = (0, 0, 80)
    yellow_color = (0, 60, 80)
    green_color = (0, 80, 0)
    
    # Apply active signal colors dynamically based on state machine values
    if lane_name == current_green_lane:
        if signal_state == "GREEN":
            green_color = (0, 255, 0)
        elif signal_state == "YELLOW":
            yellow_color = (0, 215, 255)
    else:
        if lane_name == next_green_lane and signal_state == "YELLOW":
            yellow_color = (0, 215, 255)
        else:
            red_color = (0, 0, 255)
            
    # Draw the three functional signal circles (Red, Yellow, Green)
    cv2.circle(frame, (36, 78), 10, red_color, -1)
    cv2.circle(frame, (36, 110), 10, yellow_color, -1)
    cv2.circle(frame, (36, 142), 10, green_color, -1)
    
    return vehicle_count, ambulance_present, frame

# Dynamic multi-video stream mapping configuration
lane_streams = {
    "Lane 1": cv2.VideoCapture("videos/lane_1/traffic_video1.mp4"),
    "Lane 2": cv2.VideoCapture("videos/lane_2/traffic_video2.mp4"),
    "Lane 3": cv2.VideoCapture("videos/lane_3/traffic_video3.mp4"),
    "Lane 4": cv2.VideoCapture("videos/lane_4/traffic_video4.mp4")
}

GRID_W, GRID_H = 640, 480
blank_placeholder = np.zeros((GRID_H, GRID_W, 3), dtype=np.uint8)

while True:
    processed_quadrants = {}
    lane_densities = {}
    ambulances_tracked = {}
    active_threads = 0

    for lane_name, cap in lane_streams.items():
        ok, frame = cap.read()
        if ok:
            active_threads += 1
            v_count, amb_flag, output_f = process_lane_frame(frame, lane_name)
            processed_quadrants[lane_name] = cv2.resize(output_f, (GRID_W, GRID_H))
            lane_densities[lane_name] = v_count
            ambulances_tracked[lane_name] = amb_flag
            
            # --- WEB MAP BROADCAST BROADCAST MODULE ---
            # package active telemetry data into a transmission payload
            current_lamp = "GREEN" if current_green_lane == lane_name else signal_state if next_green_lane == lane_name else "RED"
            telemetry_payload = {
                "lane_name": lane_name,
                "location": LANE_GPS_LOCATIONS[lane_name],
                "vehicle_count": v_count,
                "ambulance_active": bool(amb_flag),
                "current_signal": current_lamp,
                "timestamp": time.time()
            }
            
            # Transmit telemetry out to the local network port
            try:
                requests.post(LIVE_MAP_SERVER_API, json=telemetry_payload, timeout=0.01)
            except requests.exceptions.RequestException:
                pass  # Ignore drops if the dashboard web server is not running yet
        else:
            processed_quadrants[lane_name] = blank_placeholder
            lane_densities[lane_name] = 0
            ambulances_tracked[lane_name] = False

    if active_threads == 0:
        print("All 4 lane feeds have finished processing.")
        break

    # DENSITY AUTOMATION CONTROL ALGORITHM WITH TIMING PHASES
    current_time = time.time()
    
    # Priority Override: Instant check for active ambulances
    ambulance_target = None
    for lane, actively_detected in ambulances_tracked.items():
        if actively_detected:
            ambulance_target = lane
            break

    if ambulance_target:
        if current_green_lane != ambulance_target:
            if signal_state == "GREEN":
                next_green_lane = ambulance_target
                signal_state = "YELLOW"
                last_signal_switch = current_time
    else:
        # Standard structural density loop time evaluation
        if signal_state == "GREEN" and (current_time - last_signal_switch > SIGNAL_CYCLE_TIME):
            if lane_densities:
                highest_density_lane = max(lane_densities, key=lane_densities.get)
                if lane_densities[highest_density_lane] > 0 and highest_density_lane != current_green_lane:
                    next_green_lane = highest_density_lane
                    signal_state = "YELLOW"
                    last_signal_switch = current_time

    # State Transition: Handle yellow timing expiration steps
    if signal_state == "YELLOW" and (current_time - last_signal_switch > YELLOW_DURATION):
        current_green_lane = next_green_lane
        signal_state = "GREEN"
        last_signal_switch = current_time

    # Stacking matrix arrays into a single dashboard panel row layout
    top_row = np.hstack((processed_quadrants["Lane 1"], processed_quadrants["Lane 2"]))
    bottom_row = np.hstack((processed_quadrants["Lane 3"], processed_quadrants["Lane 4"]))
    single_window_grid = np.vstack((top_row, bottom_row))

    cv2.imshow("Smart Multi-Lane Traffic System", single_window_grid)
    
    if cv2.waitKey(1) & 0xFF == ord("q"):
        break

# Resource cleanup and connection teardown
for cap in lane_streams.values():
    cap.release()
db_conn.close()
cv2.destroyAllWindows()