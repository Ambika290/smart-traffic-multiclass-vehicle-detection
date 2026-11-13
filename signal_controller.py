import psycopg2
import time
# THE CRITICAL IMPORT FIX: Removed ".py" extension so Python loads the module cleanly
from traffic_notifier import send_traffic_alert

DB_CONFIG = {
    "host": "127.0.0.1",
    "port": "5432",
    "database": "smart_traffic_db",
    "user": "postgres",
    "password": "Traffic@1234"
}

def get_latest_lane_counts():
    """Fetches the absolute latest real-time vehicle counts for each lane by checking the highest IDs first."""
    try:
        connection = psycopg2.connect(**DB_CONFIG)
        connection.set_session(autocommit=True)
        cursor = connection.cursor()
        
        # FIXED QUERY ENGINE: Subquery pulls the absolute latest ID frames first, completely breaking the index cache lock
        query = """
            SELECT lane_id, current_vehicle_count 
            FROM traffic_metrics 
            WHERE id IN (
                SELECT MAX(id) 
                FROM traffic_metrics 
                GROUP BY lane_id
            );
        """
        cursor.execute(query)
        results = cursor.fetchall()
        
        cursor.close()
        connection.close()
        
        # Initialize lanes
        lane_counts = {"Lane 1": 0, "Lane 2": 0, "Lane 3": 0, "Lane 4": 0}
        for row in results:
            lane_name = str(row[0])  
            vehicle_count = int(row[1]) 
            lane_counts[lane_name] = vehicle_count
            
        return lane_counts
    except Exception as e:
        print(f"❌ Error fetching real-time signals: {e}")
        return {}

def calculate_dynamic_signals():
    print("Resilient Adaptive Signal Optimization Engine Initialized...")
    last_green_lane = None
    
    while True:
        lane_data = get_latest_lane_counts()
        
        if lane_data:
            print("\n--- Live Data Feed Density Status ---")
            for lane, count in lane_data.items():
                print(f"📍 {lane}: {count} vehicles waiting")
                
                # --- INTEGRATED REAL-TIME EXTREME CONGESTION AUTOMATED ALERT WATCHER ---
                # Placed inside the lane loop to evaluate each highway sensor feed dynamically
                if count >= 25:
                    print(f"⚠️ THRESHOLD CRITICAL: Congestion warning triggered on {lane}!")
                    send_traffic_alert(incident_type="EXTREME CONGESTION", lane_id=lane, metric_value=f"{count} Vehicles Queued")
            
            # --- ROUND-ROBIN FAIRNESS FILTER ---
            available_lanes = lane_data.copy()
            if last_green_lane in available_lanes and len(available_lanes) > 1:
                available_lanes[last_green_lane] = -1  
                
            busiest_lane = max(available_lanes, key=available_lanes.get)
            highest_count = lane_data[busiest_lane]
            
            last_green_lane = busiest_lane
            print(f"⚡ Target Selection: {busiest_lane} selected.")
            
            # --- TRUE ADAPTIVE TIMING ENGAGED ---
            # Strict layout scaling: Base 5s + only 1.5 seconds per actual waiting car
            if highest_count <= 2:
                allocated_green_time = 6  # Quick clearance for empty roads
            elif highest_count <= 6:
                allocated_green_time = 12 # Light congestion response
            else:
                allocated_green_time = 5 + (highest_count * 1.5)
            
            # Formulate ultimate boundary parameters (Minimum 6s, Maximum 45s)
            allocated_green_time = int(max(6, min(allocated_green_time, 45)))
            
            print(f"🟢 Adaptive Action: Giving GREEN to {busiest_lane} for {allocated_green_time} seconds.")
            
            # --- SECOND-BY-SECOND DYNAMIC COUNTDOWN LOOP ---
            for remaining_seconds in range(allocated_green_time, -1, -1):
                try:
                    connection = psycopg2.connect(**DB_CONFIG)
                    connection.set_session(autocommit=True)
                    cursor = connection.cursor()
                    
                    # Force update states instantly to database
                    cursor.execute(
                        "UPDATE live_signals SET signal_state = 'RED', "
                        "green_time_allocated = 0 WHERE lane_id != %s;",
                        (busiest_lane,),
                    )

                    cursor.execute(
                        """
                        INSERT INTO live_signals (lane_id, signal_state, green_time_allocated, last_updated)
                        VALUES (%s, 'GREEN', %s, CURRENT_TIMESTAMP)
                        ON CONFLICT (lane_id)
                        DO UPDATE SET signal_state = 'GREEN', green_time_allocated = EXCLUDED.green_time_allocated, last_updated = CURRENT_TIMESTAMP;
                        """,
                        (busiest_lane, remaining_seconds),
                    )
                    
                    cursor.close()
                    connection.close()
                except Exception as db_err:
                    print(f"Failed to save signal status: {db_err}")
                
                print(f"⏳ {busiest_lane} Active Countdown: {remaining_seconds}s remaining...", end="\r")
                time.sleep(1)
            
            # --- AUTOMATIC CLEARANCE LOG FLUSH ---
            try:
                connection = psycopg2.connect(**DB_CONFIG)
                connection.set_session(autocommit=True)
                cursor = connection.cursor()
                cursor.execute("""
                    INSERT INTO traffic_metrics (lane_id, current_vehicle_count, congestion_level, timestamp)
                    VALUES (%s, 0, 'Low', CURRENT_TIMESTAMP);
                """, (busiest_lane,))
                cursor.close()
                connection.close()
                print(f"\n✨ System cleared density queue history markers for {busiest_lane}.")
            except Exception as flush_err:
                print(f"\nFailed to clear lane logs: {flush_err}")
                
        else:
            print("⌛ Waiting for active tracking metrics from track.py loop...")
            time.sleep(5)

if __name__ == "__main__":
    calculate_dynamic_signals()