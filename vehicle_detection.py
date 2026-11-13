import cv2
import numpy as np
import pandas as pd
from datetime import datetime
from ultralytics import YOLO

# Initialize model and output paths
model = YOLO("yolov8n.pt")  # Loads the YOLOv8 file visible in your project workspace
csv_path = "outputs/traffic_telemetry.csv"

# 1. Map input sources dynamically using your project's folder layout
video_sources = {
    0: "videos/lane_1/traffic_video1.mp4",
    1: "videos/lane_2/traffic_video2.mp4",
    2: "videos/lane_3/traffic_video3.mp4",
    3: "videos/lane_4/traffic_video4.mp4"
}

# Open all video files simultaneously
caps = {idx: cv2.VideoCapture(path) for idx, path in video_sources.items()}

# Telemetry data storage placeholder
telemetry_data = []
frame_count = 0

print("🚀 Starting Smart Traffic Management System - Ingesting Multi-Lane Feed...")

while True:
    processed_frames = []
    current_time = datetime.now().strftime("%Y-%m-%dT%H:%M:%SZ")
    frame_count += 1
    
    # Process all 4 lanes sequentially inside this frame loop iteration
    for idx in range(4):
        cap = caps[idx]
        success, frame = cap.read()
        
        # If any video reaches its end, reset/loop it automatically
        if not success:
            cap.set(cv2.CAP_PROP_POS_FRAMES, 0)
            success, frame = cap.read()
            
        # Resize frame to standard dimension (e.g., 400x300) to keep grid aligned perfectly
        frame = cv2.resize(frame, (400, 300))
        
        # 2. Run object detection engine
        results = model(frame, verbose=False)[0]
        
        vehicle_count = 0
        ambulance_detected = False
        
        # Target COCO dataset classes: 2: car, 3: motorcycle, 5: bus, 7: truck
        target_classes = [2, 3, 5, 7]
        
        for box in results.boxes:
            cls_id = int(box.cls[0])
            label = model.names[cls_id]
            
            # Simple simulation check: classify large vehicles or specific flags as emergency overrides
            if label == "truck" and box.conf[0] > 0.65:  # Mock rule to treat high-conf trucks as emergency for display
                ambulance_detected = True
                
            if cls_id in target_classes:
                vehicle_count += 1
                
                # Draw bounding box and label
                x1, y1, x2, y2 = map(int, box.xyxy[0])
                box_color = (0, 0, 255) if ambulance_detected else (0, 255, 0)
                cv2.rectangle(frame, (x1, y1), (x2, y2), box_color, 2)
        
        # 3. Calculate dynamic metrics profile
        road_capacity = 15  # Assume max capacity of lane field is 15 vehicles
        congestion_index = round(min(1.0, vehicle_count / road_capacity), 2)
        
        # Log telemetry details incrementally every 30 frames (~1 second interval)
        if frame_count % 30 == 0:
            telemetry_data.append({
                "Timestamp": current_time,
                "Lane_ID": f"Lane_{idx + 1}",
                "Vehicle_Count": vehicle_count,
                "Congestion_Index": congestion_index,
                "Emergency_Override": 1 if ambulance_detected else 0
            })
            
        # Draw on-screen telemetry stats for each quadrant window panel
        status_text = f"Lane {idx+1} | Vehicles: {vehicle_count} | Index: {int(congestion_index*100)}%"
        cv2.putText(frame, status_text, (10, 25), cv2.FONT_HERSHEY_SIMPLEX, 0.6, (255, 255, 255), 2)
        
        if ambulance_detected:
            cv2.putText(frame, "🚨 EMERGENCY PRIORITY CORRIDOR ACTIVE", (10, 50), 
                        cv2.FONT_HERSHEY_SIMPLEX, 0.5, (0, 0, 255), 2)
            
        processed_frames.append(frame)

    # 4. Matrix Row Stitching (Matches lines 168-173 in your file screenshot precisely)
    top_row = np.hstack((processed_frames[0], processed_frames[1]))
    bottom_row = np.hstack((processed_frames[2], processed_frames[3]))
    dashboard = np.vstack((top_row, bottom_row))

    # Display the unified master central dashboard window console
    cv2.imshow("Smart Traffic Management System - Central Command Dashboard", dashboard)
    
    # Clear waitKey conditional loop escape trigger
    if cv2.waitKey(30) & 0xFF == ord('q'):
        break

# --- Cleanup Layer Outside the Execution Loop ---
for cap in caps.values():
    cap.release()
cv2.destroyAllWindows()

# Export clean text matrix to file directory
df = pd.DataFrame(telemetry_data)
df.to_csv(csv_path, index=False)
print(f"\n⚙️ Telemetry file updated at: {csv_path}")