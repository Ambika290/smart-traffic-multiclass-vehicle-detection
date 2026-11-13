import psycopg2

DB_CONFIG = {
    "host": "127.0.0.1",
    "port": "5432",
    "database": "smart_traffic_db",
    "user": "postgres",
    "password": "Traffic@1234"
}

def setup_lane_rows():
    try:
        connection = psycopg2.connect(**DB_CONFIG)
        cursor = connection.cursor()
        
        # Insert baseline placeholder rows for all 4 lanes
        for lane in ["Lane 1", "Lane 2", "Lane 3", "Lane 4"]:
            cursor.execute("""
                INSERT INTO live_signals (lane_id, signal_state, green_time_allocated)
                VALUES (%s, 'RED', 0)
                ON CONFLICT (lane_id) DO NOTHING;
            """, (lane,))
            
        connection.commit()
        cursor.close()
        connection.close()
        print("🎉 Dashboard rows linked successfully!")
    except Exception as e:
        print(f"Error: {e}")

if __name__ == "__main__":
    setup_lane_rows()