import psycopg2
from psycopg2.extras import RealDictCursor
from contextlib import closing
from datetime import datetime

# ============================================================
# 1. DATABASE CONFIGURATION
# ============================================================

DB_CONFIG = {
    "host": "127.0.0.1",
    "port": 5432,
    "database": "smart_traffic_db",
    "user": "postgres",
    "password": "Traffic@1234"
}


# ============================================================
# 2. DATABASE CONNECTION
# ============================================================

def get_connection():
    """Create and return a PostgreSQL connection."""
    return psycopg2.connect(**DB_CONFIG)


# ============================================================
# 3. CREATE DATABASE TABLES
# ============================================================

def create_tables():
    """Create required tables if they do not already exist."""

    with closing(get_connection()) as connection:
        with connection.cursor() as cursor:

            cursor.execute("""
                CREATE TABLE IF NOT EXISTS vehicle_detections (
                    id SERIAL PRIMARY KEY,
                    lane_id VARCHAR(20) NOT NULL,
                    timestamp TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    video_time_seconds FLOAT,
                    vehicle_id INTEGER,
                    vehicle_type VARCHAR(30),
                    confidence FLOAT
                );
            """)

            cursor.execute("""
                CREATE TABLE IF NOT EXISTS traffic_metrics (
                    id SERIAL PRIMARY KEY,
                    lane_id VARCHAR(20) NOT NULL,
                    timestamp TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    video_time_seconds FLOAT,
                    car_count INTEGER DEFAULT 0,
                    motorcycle_count INTEGER DEFAULT 0,
                    bus_count INTEGER DEFAULT 0,
                    truck_count INTEGER DEFAULT 0,
                    current_vehicle_count INTEGER DEFAULT 0,
                    unique_vehicle_count INTEGER DEFAULT 0,
                    pcu FLOAT DEFAULT 0,
                    congestion_level VARCHAR(20)
                );
            """)

            cursor.execute("""
                CREATE TABLE IF NOT EXISTS live_signals (
                    lane_id VARCHAR(20) PRIMARY KEY,
                    signal_state VARCHAR(10) DEFAULT 'RED',
                    green_time_allocated INTEGER DEFAULT 0,
                    last_updated TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                );
            """)

            cursor.execute("""
                CREATE TABLE IF NOT EXISTS traffic_violations (
                    id SERIAL PRIMARY KEY,
                    lane_id VARCHAR(20) NOT NULL,
                    timestamp TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    vehicle_id INTEGER,
                    vehicle_type VARCHAR(30),
                    violation_type VARCHAR(50) NOT NULL,
                    details TEXT
                );
            """)

        connection.commit()

    print("Database tables are ready.")


# ============================================================
# 4. SAVE VEHICLE DETECTION
# ============================================================

def save_vehicle_detection(
    lane_id,
    video_time_seconds,
    vehicle_id,
    vehicle_type,
    confidence
):
    """Save one vehicle detection to PostgreSQL."""

    query = """
        INSERT INTO vehicle_detections (
            lane_id,
            video_time_seconds,
            vehicle_id,
            vehicle_type,
            confidence
        )
        VALUES (%s, %s, %s, %s, %s);
    """

    return execute_insert(
        query,
        (
            lane_id,
            video_time_seconds,
            vehicle_id,
            vehicle_type,
            confidence
        ),
        "vehicle detection"
    )


# ============================================================
# 5. SAVE TRAFFIC METRICS
# ============================================================

def save_traffic_metrics(
    lane_id,
    video_time_seconds,
    car_count,
    motorcycle_count,
    bus_count,
    truck_count,
    current_vehicle_count,
    unique_vehicle_count,
    pcu,
    congestion_level
):
    """Save traffic counts and congestion metrics."""

    query = """
        INSERT INTO traffic_metrics (
            lane_id,
            video_time_seconds,
            car_count,
            motorcycle_count,
            bus_count,
            truck_count,
            current_vehicle_count,
            unique_vehicle_count,
            pcu,
            congestion_level
        )
        VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s);
    """

    values = (
        lane_id,
        video_time_seconds,
        car_count,
        motorcycle_count,
        bus_count,
        truck_count,
        current_vehicle_count,
        unique_vehicle_count,
        pcu,
        congestion_level
    )

    return execute_insert(query, values, "traffic metrics")


# ============================================================
# 6. SAVE TRAFFIC VIOLATIONS (AUTOMATIC PIPELINE INTEGRATION)
# ============================================================

def save_traffic_violation(
    lane_id,
    vehicle_id,
    vehicle_type,
    violation_type="Red-light violation",
    details="AI Automated Pipeline Capture"
):
    """Save a confirmed traffic violation automatically."""

    query = """
        INSERT INTO traffic_violations (
            lane_id,
            vehicle_id,
            vehicle_type,
            violation_type,
            details
        )
        VALUES (%s, %s, %s, %s, %s);
    """

    values = (
        str(lane_id),
        int(vehicle_id) if vehicle_id and str(vehicle_id).lower() != 'none' else None,
        str(vehicle_type),
        str(violation_type),
        str(details)
    )

    return execute_insert(query, values, "traffic violation")


# ============================================================
# 7. FETCH LIVE SIGNAL STATE FOR AUTOMATION VALIDATION
# ============================================================

def check_live_signal_state(lane_id):
    """
    Fetch the current active signal status string from a specific lane.
    Used inside track.py to verify if the lane state phase is actively 'RED'.
    """
    query = "SELECT signal_state FROM live_signals WHERE UPPER(TRIM(lane_id)) = UPPER(TRIM(%s));"
    try:
        with closing(get_connection()) as connection:
            with connection.cursor(cursor_factory=RealDictCursor) as cursor:
                cursor.execute(query, (str(lane_id),))
                result = cursor.fetchone()
                if result:
                    return str(result['signal_state']).strip().upper()
        return "RED"  # Safe default if lane isn't registered yet
    except Exception as error:
        print(f"Error fetching live signal state: {error}")
        return "RED"


# ============================================================
# 8. COMMON DATABASE INSERT FUNCTION
# ============================================================

def execute_insert(query, values, operation_name):
    """
    Execute an INSERT query safely.
    Commit when successful and roll back when an error occurs.
    """

    try:
        with closing(get_connection()) as connection:
            with connection.cursor() as cursor:
                cursor.execute(query, values)

            connection.commit()

        return True

    except (psycopg2.Error, TypeError, ValueError) as error:
        print(f"Error saving {operation_name}: {error}")
        return False


# ============================================================
# 9. RUN THIS FILE DIRECTLY TO CREATE TABLES
# ============================================================

if __name__ == "__main__":
    try:
        create_tables()
        print("PostgreSQL database functions are ready!")

    except psycopg2.Error as error:
        print(f"Database error: {error}")