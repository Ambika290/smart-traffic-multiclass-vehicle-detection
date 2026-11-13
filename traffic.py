import os
os.environ["YOLO_VERBOSE"] = "False"  # Silences internal model logs to keep terminal clean

import cv2
import csv
import numpy as np
from collections import deque
from ultralytics import YOLO

# ==============================================================================
# CORE CONFIGURATION LOGIC
# ==============================================================================
NUM_LANES = 4
VEHICLE_CLASSES = [2, 3, 5, 7]     # car, motorcycle, bus, truck
CLASS_NAMES = {2: "car", 3: "motorcycle", 5: "bus", 7: "truck"}
WIDTH = 640

STOPPED_PX_PER_SEC = 20            # below this speed a vehicle counts as "stopped"
METERS_PER_PIXEL = None            # set later for real km/h calculations

# ==============================================================================
# STEP 8 CONFIGURATION: PCU Weights and Congestion Levels
# ==============================================================================
PCU = {
    "motorcycle": 0.5,
    "car": 1.0,
    "auto-rickshaw": 1.0,
    "ambulance": 2.0,
    "bus": 3.0,
    "truck": 3.0
}

def congestion_level(pcu):
    """PCU-in-view thresholds for traffic congestion classification levels"""
    if pcu < 8:
        return "LOW"
    elif pcu < 16:
        return "MEDIUM"
    elif pcu < 24:
        return "HIGH"
    else:
        return "CRITICAL"

# ==============================================================================
# MULTI-LANE MANAGEMENT OBJECT CLASS (PART 1)
# ==============================================================================
class Lane:
    def __init__(self, lane_id):  
        self.id = f"Lane {lane_id}"
        # Paths configured to read your exact workspace subfolder video streams
        self.cap = cv2.VideoCapture(f"videos/lane_{lane_id}/traffic_video{lane_id}.mp4")
        self.fps = self.cap.get(cv2.CAP_PROP_FPS) or 30
        self.frame_no = 0
        self.finished = False

        # Individual isolated tracking containers for this specific lane instance  
        self.seen_ids = set()  
        self.prev_vehicles = []  
        self.history = {}              # vehicle ID -> recent tracking history positions (frame, cx, cy)  

        # High-level traffic measurement variables  
        self.in_view = 0  
        self.avg_speed = 0.0  
        self.queue = 0  
        self.density = 0.0  
        self.pcu = 0.0  
        self.congestion = "LOW"  
        self.rows = []                 # store logging rows data to output to CSV file later  

    def compute_iou(self, box1, box2):  
        """Calculates Spatial Overlap (Intersection over Union) between current detection bounding boxes"""  
        x1 = max(box1[0], box2[0])  
        y1 = max(box1[1], box2[1])  
        x2 = min(box1[2], box2[2])  
        y2 = min(box1[3], box2[3])  
          
        intersection = max(0, x2 - x1) * max(0, y2 - y1)  
        area1 = (box1[2] - box1[0]) * (box1[3] - box1[1])  
        area2 = (box2[2] - box2[0]) * (box2[3] - box2[1])  
        union = area1 + area2 - intersection  
          
        return intersection / union if union > 0 else 0  

    def speed_display(self):  
        if METERS_PER_PIXEL:  
            return self.avg_speed * METERS_PER_PIXEL * 3.6  
        return self.avg_speed

    def log_row(self):  
        self.rows.append({  
            "lane": self.id,  
            "time_sec": max(1, round(self.frame_no / self.fps)),  
            "vehicles_in_view": self.in_view,  
            "avg_speed": round(self.speed_display(), 1),  
            "queue_vehicles": self.queue,  
            "density_percent": round(self.density, 1),  
            "unique_seen_total": len(self.seen_ids),  
            "pcu": round(self.pcu, 1),  
            "congestion": self.congestion,  
        })

# ==============================================================================
# MULTI-LANE MANAGEMENT OBJECT CLASS (PART 2)
# ==============================================================================
    def process(self, current_global_id, model):  
        ok, frame = self.cap.read()  
        if not ok:  
            if self.frame_no > 0 and (not self.rows or self.rows[-1]["time_sec"] != round(self.frame_no / self.fps)):  
                self.log_row()  
            self.finished = True  
            return current_global_id, None  
        self.frame_no += 1  

        h, w = frame.shape[:2]  
        target_h = int(h * WIDTH / w)  
        frame = cv2.resize(frame, (WIDTH, target_h))  
        frame_area = WIDTH * target_h  

        results = model(frame, classes=VEHICLE_CLASSES, verbose=False)  
          
        current_detections = []  
        boxes_container = results[0].boxes if (results and len(results) > 0) else []  
          
        if len(boxes_container) > 0:  
            for box in boxes_container:  
                x1, y1, x2, y2 = map(int, box.xyxy[0].tolist())  
                conf = float(box.conf[0])  
                cls_id = int(box.cls[0])  
                current_detections.append({"box": [x1, y1, x2, y2], "cls_id": cls_id, "conf": conf, "id": None})  

        updated_vehicles = []  
        speeds = []  
        box_area_sum = 0  
        pcu_sum = 0.0  

        for cur in current_detections:  
            best_iou = 0  
            best_match_id = None  
              
            for prev in self.prev_vehicles:  
                iou = self.compute_iou(cur["box"], prev["box"])  
                if iou > best_iou and cur["cls_id"] == prev["cls_id"]:  
                    best_iou = iou  
                    best_match_id = prev["id"]  
            
            if best_iou > 0.35:  
                cur["id"] = best_match_id  
            else:  
                cur["id"] = current_global_id  
                current_global_id += 1  
                  
            self.seen_ids.add(cur["id"])  
            updated_vehicles.append(cur)  
              
            x1, y1, x2, y2 = cur["box"]  
            vid = cur["id"]  
            conf = cur["conf"]  
            cls_id = cur["cls_id"]  
              
            box_area_sum += (x2 - x1) * (y2 - y1)  
            cx, cy = (x1 + x2) / 2, (y1 + y2) / 2  

            hist = self.history.setdefault(vid, deque(maxlen=10))  
            hist.append((self.frame_no, cx, cy))  
            if len(hist) >= 5:  
                f0, x0, y0 = hist[0]  
                f1, x1_, y1_ = hist[-1]  
                seconds = (f1 - f0) / self.fps  
                if seconds > 0:  
                    dist = ((x1_ - x0) ** 2 + (y1_ - y0) ** 2) ** 0.5  
                    speeds.append(dist / seconds)  

            width = x2 - x1  
            height = y2 - y1  
            aspect_ratio = width / height if height > 0 else 0  
            box_area = width * height  

            v_type = CLASS_NAMES[cls_id]  
            if cls_id == 7 and (0.45 <= aspect_ratio <= 0.82):  
                v_type = "auto-rickshaw"  
                color = (0, 165, 255)  
            elif cls_id == 5 and box_area < 38000:  
                v_type = "ambulance"  
                color = (0, 0, 255)  
            elif cls_id == 3:  
                v_type = "motorcycle"  
                color = (0, 255, 0)  
            else:  
                color = (255, 0, 0)  

            pcu_sum += PCU.get(v_type, 1.0)  

            label = f"id:{vid} {v_type} {conf:.2f}"  
            cv2.rectangle(frame, (x1, y1), (x2, y2), color, 2)  
            cv2.putText(frame, label, (x1, y1 - 10), cv2.FONT_HERSHEY_SIMPLEX, 0.5, color, 2)  

        self.prev_vehicles = updated_vehicles  
        self.in_view = len(updated_vehicles)  
        self.avg_speed = sum(speeds) / len(speeds) if speeds else 0.0  
        self.queue = sum(1 for s in speeds if s < STOPPED_PX_PER_SEC)  
        self.density = min(100.0, 100.0 * box_area_sum / frame_area)  

        self.pcu = pcu_sum  
        self.congestion = congestion_level(self.pcu)  

        if self.frame_no % int(self.fps) == 0:  
            self.log_row()  

        # FIXED VISIBILITY: Expanded dimensions background layout panel
        cv2.rectangle(frame, (5, 5), (460, 95), (0, 0, 0), -1)  

        # Text overlay strings layout panels  
        unit = "km/h" if METERS_PER_PIXEL else "px/s"  
        cv2.putText(frame, f"{self.id} | In view: {self.in_view} | Congestion: {self.congestion}",   
                    (15, 30), cv2.FONT_HERSHEY_SIMPLEX, 0.65, (255, 255, 255), 2)  
                  
        cv2.putText(frame, f"Speed: {self.speed_display():.0f} {unit} | Density: {self.density:.0f}%",   
                    (15, 60), cv2.FONT_HERSHEY_SIMPLEX, 0.55, (0, 255, 0), 2)  
                  
        # FIXED ALIGNMENT: Shifted position horizontal trace parameter to 15 to align with standard lines
        cv2.putText(frame, f"PCU: {self.pcu:.1f} | Congestion: {self.congestion}",
                    (15, 84), cv2.FONT_HERSHEY_SIMPLEX, 0.65, (0, 255, 255), 2)  
                  
        return current_global_id, frame  

# ==============================================================================
# MAIN SYSTEM GRID VIEWPORT RUNTIME LOOP
# ==============================================================================
global_model = YOLO("yolov8n.pt")
lanes = [Lane(i) for i in range(1, NUM_LANES + 1)]
global_id_tracker = 1

GRID_W, GRID_H = 640, 480
blank_placeholder = np.zeros((GRID_H, GRID_W, 3), dtype=np.uint8)

while True:
    processed_quadrants = {}
    active_threads = 0

    for lane in lanes:  
        if lane.finished:  
            processed_quadrants[lane.id] = blank_placeholder  
            continue  
              
        global_id_tracker, frame = lane.process(global_id_tracker, global_model)  
        if frame is not None:  
            active_threads += 1  
            processed_quadrants[lane.id] = cv2.resize(frame, (GRID_W, GRID_H))  
        else:  
            processed_quadrants[lane.id] = blank_placeholder  

    if active_threads == 0:  
        break  

    top_row = np.hstack((processed_quadrants["Lane 1"], processed_quadrants["Lane 2"]))  
    bottom_row = np.hstack((processed_quadrants["Lane 3"], processed_quadrants["Lane 4"]))  
    single_window_grid = np.vstack((top_row, bottom_row))  
      
    cv2.imshow("Smart Traffic Management Dashboard", single_window_grid)  

    if cv2.waitKey(1) & 0xFF == ord("q"):  
        for lane in lanes:
            if not lane.finished and lane.frame_no > 0:
                lane.log_row()
        break

cv2.destroyAllWindows()

# ==============================================================================
# DATASET GENERATION LOGIC (traffic_metrics.csv Exporter)
# ==============================================================================
all_metrics_rows = []
for lane in lanes:
    all_metrics_rows.extend(lane.rows)

if all_metrics_rows:
    csv_file_path = "traffic_metrics.csv"
    headers = ["lane", "time_sec", "vehicles_in_view", "avg_speed", "queue_vehicles", "density_percent", "unique_seen_total", "pcu", "congestion"]
    
    with open(csv_file_path, mode="w", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=headers)
        writer.writeheader()
        writer.writerows(all_metrics_rows)
        
    print(f"\n[SUCCESS] Unified dataset file successfully saved to '{csv_file_path}'!")        