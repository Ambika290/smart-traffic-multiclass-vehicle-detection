from traffic_db import save_vehicle_detection, save_traffic_metrics, save_traffic_violation, check_live_signal_state
from traffic_notifier import send_traffic_alert
import os
os.environ["YOLO_VERBOSE"] = "False"  # Silences internal model logs

import time
import cv2
import numpy as np
from ultralytics import YOLO

# Load the pretrained model
model = YOLO("yolov8n.pt")

# Vehicle class ID filters (2=car, 3=motorcycle, 5=bus, 7=truck)
VEHICLE_CLASSES = [2, 3, 5, 7]

# Initialize individual unique seen tracing sets for each separate lane independently
lane_trackers = {
    "Lane 1": set(),
    "Lane 2": set(),
    "Lane 3": set(),
    "Lane 4": set()
}

# Persistent structures to manage continuous multi-stream tracking manually
prev_vehicles = {"Lane 1": [], "Lane 2": [], "Lane 3": [], "Lane 4": []}
next_global_id = 1

# Tracks which vehicles have already been logged for a violation to avoid duplicate database inserts
logged_violations = {
    "Lane 1": set(),
    "Lane 2": set(),
    "Lane 3": set(),
    "Lane 4": set()
}

def compute_iou(box1, box2):
    """Calculates Spatial Overlap (Intersection over Union) between two bounding boxes"""
    x1 = max(box1[0], box2[0])
    y1 = max(box1[1], box2[1])
    x2 = min(box1[2], box2[2])
    y2 = min(box1[3], box2[3])
    
    intersection = max(0, x2 - x1) * max(0, y2 - y1)
    area1 = (box1[2] - box1[0]) * (box1[3] - box1[1])
    area2 = (box2[2] - box2[0]) * (box2[3] - box2[1])
    union = area1 + area2 - intersection
    
    return intersection / union if union > 0 else 0

def process_tracking_frame(frame, lane_name, current_timestamp_secs):
    global next_global_id
    if frame is None:
        return None

    # Get frame properties to place stop line configurations dynamically
    frame_h, frame_w, _ = frame.shape
    stop_line_y = int(frame_h * 0.70)  # Virtual line at 70% frame height

    # Query the PostgreSQL table for the current light signal color state configuration
    current_light_state = check_live_signal_state(lane_name)

    # Run standard YOLO detection
    results = model(frame, classes=VEHICLE_CLASSES, conf=0.10, verbose=False)
    
    current_detections = []
    boxes_container = results[0].boxes if len(results) > 0 else []
    
    if len(boxes_container) > 0:
        for box in boxes_container:
            x1, y1, x2, y2 = map(int, box.xyxy[0].tolist())
            conf = float(box.conf[0])
            cls_id = int(box.cls[0])
            current_detections.append({"box": [x1, y1, x2, y2], "cls_id": cls_id, "conf": conf, "id": None})

    # Match current detections with previous frame vehicles using spatial overlap
    updated_vehicles = []
    
    # Initialize real-time classification metric accumulation counters
    car_cnt = 0
    moto_cnt = 0
    bus_cnt = 0
    truck_cnt = 0
    
    for cur in current_detections:
        best_iou = 0
        best_match_id = None
        
        for prev in prev_vehicles[lane_name]:
            iou = compute_iou(cur["box"], prev["box"])
            if iou > best_iou and cur["cls_id"] == prev["cls_id"]:
                best_iou = iou
                best_match_id = prev["id"]
        
        # If matching overlap is found, keep the persistent vehicle track ID
        if best_iou > 0.35:
            cur["id"] = best_match_id
        else:
            # Assign a fresh tracking index to a newly arriving vehicle profile
            cur["id"] = next_global_id
            next_global_id += 1
            
            # Map standard readable type label name string for the database records
            detected_name = model.names[cur["cls_id"]]
            
            # Save new vehicle to PostgreSQL database
            save_vehicle_detection(
                lane_id=lane_name,
                video_time_seconds=current_timestamp_secs,
                vehicle_id=cur["id"],
                vehicle_type=detected_name,
                confidence=float(cur["conf"])
            )
# Calculate bounding box dimensions for your custom road rules
        x1, y1, x2, y2 = cur["box"]
        vid = cur["id"]
        conf = cur["conf"]
        cls_id = cur["cls_id"]
        
        width = x2 - x1
        height = y2 - y1
        aspect_ratio = width / height if height > 0 else 0
        box_area = width * height

        # Compute bottom center point coordinates of the bounding box to check stop-line crossings
        bottom_y = y2

        # --- AUTOMATED VIOLATION INSPECTION ENGINE HOOK ---
        # Trigger entry if the vehicle crosses the stop line threshold while light phase is explicitly RED
        if current_light_state == "RED" and bottom_y > stop_line_y:
            if vid not in logged_violations[lane_name]:
                detected_name = model.names[cls_id]
                
                # Check for auto-rickshaw or ambulance classification override adjustments
                if cls_id == 7 and (0.45 <= aspect_ratio <= 0.82):
                    detected_name = "auto-rickshaw"
                elif cls_id == 5 and box_area < 38000:
                    detected_name = "ambulance"

                # Automatically save confirmed infraction data matrix to PostgreSQL database
                save_traffic_violation(
                    lane_id=lane_name,
                    vehicle_id=vid,
                    vehicle_type=detected_name,
                    violation_type="Red-light violation",
                    details=f"AI System Automated Capture: Crossed virtual stop line ({bottom_y}px > {stop_line_y}px) during active RED signal status phase window."
                )
                logged_violations[lane_name].add(vid)
                print(f"[ALERT] Automated Red-Light Violation logged for Vehicle {vid} ({detected_name}) on {lane_name}!")

        # CALIBRATED LOCAL SEPARATION LABELS AND COUNTER INCREMENTS
        if cls_id == 7 and (0.45 <= aspect_ratio <= 0.82):
            label = f"id:{vid} auto-rickshaw {conf:.2f}"
            color = (0, 165, 255)  # Orange for autos
            truck_cnt += 1         
        elif cls_id == 5 and box_area < 38000:
            label = f"id:{vid} ambulance {conf:.2f}"
            color = (0, 0, 255)    # Red for emergency priority
            bus_cnt += 1           
            
            # --- EMERGENCY VEHICLE IMMEDIATE EMAIL ALERT HOOK ---
            # Triggers exactly once per unique vehicle ID lifetime to prevent email spamming
            if vid not in lane_trackers[lane_name]:
                send_traffic_alert(
                    incident_type="AMBULANCE DETECTED (PRIORITY PASS)",
                    lane_id=lane_name,
                    metric_value=f"Confidence: {conf:.2f} | Footprint: {box_area}px"
                )
        elif cls_id == 3:
            label = f"id:{vid} motorcycle {conf:.2f}"
            color = (0, 255, 0)    # Green for bikes
            moto_cnt += 1
        elif cls_id == 2:
            label = f"id:{vid} car {conf:.2f}"
            color = (255, 0, 0)    # Blue for standard cars
            car_cnt += 1
        else:
            label = f"id:{vid} {model.names[cls_id]} {conf:.2f}"
            color = (255, 0, 0)
            if cls_id == 5: bus_cnt += 1
            if cls_id == 7: truck_cnt += 1

        lane_trackers[lane_name].add(vid)
        updated_vehicles.append(cur)

        # Render custom boxes and tracker data labels cleanly onto the video surface
        cv2.rectangle(frame, (x1, y1), (x2, y2), color, 2)
        cv2.putText(frame, label, (x1, y1 - 10),
                    cv2.FONT_HERSHEY_SIMPLEX, 0.5, color, 2)

    # Draw the dynamic virtual stop line overlay on the tracking window frame surface canvas layout
    line_color = (0, 0, 255) if current_light_state == "RED" else (0, 255, 0)
    cv2.line(frame, (0, stop_line_y), (frame_w, stop_line_y), line_color, 2)
    cv2.putText(frame, f"STOP LINE ({current_light_state})", (10, stop_line_y - 8),
                cv2.FONT_HERSHEY_SIMPLEX, 0.5, line_color, 1)

    # Save tracking history state for the upcoming frame calculation
    prev_vehicles[lane_name] = updated_vehicles
    in_view_count = len(updated_vehicles)

    # Render visual telemetry counters layer text seamlessly across each grid slot
    cv2.putText(frame, f"{lane_name} ({current_light_state})", (20, 40), 
                cv2.FONT_HERSHEY_SIMPLEX, 0.9, (255, 255, 255), 2)
                
    cv2.putText(frame, f"In view: {in_view_count}", (20, 80), 
                cv2.FONT_HERSHEY_SIMPLEX, 0.7, (0, 255, 0), 2)
                
    cv2.putText(frame, f"Unique seen: {len(lane_trackers[lane_name])}", (20, 110), 
                cv2.FONT_HERSHEY_SIMPLEX, 0.7, (0, 255, 0), 2)

    current_total = len(current_detections)
    unique_total = len(lane_trackers[lane_name])
    
    # Save frame details to metrics table
    save_traffic_metrics(
        lane_id=lane_name,
        video_time_seconds=current_timestamp_secs,
        car_count=car_cnt,
        motorcycle_count=moto_cnt,
        bus_count=bus_cnt,
        truck_count=truck_cnt,
        current_vehicle_count=current_total,
        unique_vehicle_count=unique_total,
        pcu=float(current_total * 1.0),
        congestion_level="Low" if current_total <= 4 else "Heavy"
    )

    return frame

# Multi-video input streams mapping configuration
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
    active_threads = 0

    for lane_name, cap in lane_streams.items():
        # Capture precise video timeline offset to feed database sync logs
        time_ms = cap.get(cv2.CAP_PROP_POS_MSEC)
        current_secs = round(time_ms / 1000.0, 2)
        
        ok, frame = cap.read()
        if not ok:
            # If the video stream reaches the end, reset it to the beginning frame
            cap.set(cv2.CAP_PROP_POS_FRAMES, 0)
            ok, frame = cap.read()
        if ok:
            active_threads += 1
            output_f = process_tracking_frame(frame, lane_name, current_secs)
            processed_quadrants[lane_name] = cv2.resize(output_f, (GRID_W, GRID_H))
        else:
            processed_quadrants[lane_name] = blank_placeholder

    if active_threads == 0:
        print("All 4 lane tracking feeds have finished processing.")
        break

    # Stacking matrix grid frames row layout inside a clean 2x2 multi-camera screen layout
    top_row = np.hstack((processed_quadrants["Lane 1"], processed_quadrants["Lane 2"]))
    bottom_row = np.hstack((processed_quadrants["Lane 3"], processed_quadrants["Lane 4"]))
    single_window_grid = np.vstack((top_row, bottom_row))

    cv2.imshow("Smart Multi-Lane Tracking System", single_window_grid)
    
    if cv2.waitKey(1) & 0xFF == ord("q"):
        break

for cap in lane_streams.values():
    cap.release()
cv2.destroyAllWindows()