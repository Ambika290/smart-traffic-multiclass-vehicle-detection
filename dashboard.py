import streamlit as st
import pandas as pd
import sqlite3
import os
import time
import psycopg2
from datetime import datetime

# Set up clean web browser layout configuration
st.set_page_config(page_title="Smart Traffic Management Dashboard", layout="wide")

# DATABASE CONFIGURATIONS
SQLITE_DB_NAME = "traffic_violations.db"
POSTGRES_CONFIG = {
    "host": "127.0.0.1",
    "port": "5432",
    "database": "smart_traffic_db",
    "user": "postgres",
    "password": "Traffic@1234"
}

def get_postgres_data(query):
    """Safely queries active telemetry streams from the live PostgreSQL instance."""
    try:
        with psycopg2.connect(**POSTGRES_CONFIG) as connection:
            df = pd.read_sql_query(query, connection)
            df.columns = df.columns.str.lower()
            return df
    except Exception:
        return pd.DataFrame()

def execute_postgres_command(query):
    """Safely runs delete/truncation commands on the PostgreSQL relational server maps."""
    try:
        with psycopg2.connect(**POSTGRES_CONFIG) as connection:
            connection.set_session(autocommit=True)
            with connection.cursor() as cursor:
                cursor.execute(query)
                return True
    except Exception as e:
        st.sidebar.error(f"PostgreSQL Command Error: {e}")
        return False


def get_sqlite_data(query):
    """Read violation records from the correct SQLite database."""
    db_path = os.path.abspath(SQLITE_DB_NAME)

    if not os.path.exists(db_path):
        st.sidebar.error(f"SQLite database not found: {db_path}")
        return pd.DataFrame()

    try:
        with sqlite3.connect(db_path) as connection:
            df = pd.read_sql_query(query, connection)
            df.columns = df.columns.str.lower()
            return df

    except Exception as e:
        st.sidebar.error(f"SQLite database error: {e}")
        return pd.DataFrame()


def execute_sqlite_command(query):
    """Safely executes write/delete statements against the local SQLite database context."""
    try:
        with sqlite3.connect(SQLITE_DB_NAME) as connection:
            cursor = connection.cursor()
            cursor.execute(query)
            connection.commit()
            return True
    except Exception as e:
        st.sidebar.error(f"SQLite Command Error: {e}")
        return False

# --- SIDEBAR NAVIGATION & TELEMETRY BANNER ---
st.sidebar.title("Navigation Panel")
page_selection = st.sidebar.radio(
    "Go to page:",
    ["📊 Real-Time Detection & Analytics", "🚨 Traffic Violations Log Panel", "⚙️ Database Operations Control"],
    key="page_selection"
)

st.sidebar.markdown("---")
st.sidebar.subheader("🚨 Live Enforcement Status")

# Query high-risk metrics dynamically from the active PostgreSQL database tables
df_sidebar_alerts = get_postgres_data("SELECT count(*) as heavy_count FROM traffic_metrics WHERE current_vehicle_count >= 15")
sidebar_flags = 0
if not df_sidebar_alerts.empty and 'heavy_count' in df_sidebar_alerts.columns:
    try:
        sidebar_flags = int(df_sidebar_alerts.iloc[0]['heavy_count'])
    except Exception:
        pass

if sidebar_flags > 0:
    st.sidebar.error(f"⚠️ SYSTEM HAZARDS: {sidebar_flags} Active Flags")
    st.sidebar.caption("High density queue thresholds breached. Adaptive override engaged.")
else:
    st.sidebar.success("✅ SYSTEM STATUS: Clear")
    st.sidebar.caption("All intersections moving smoothly within normal parameters.")
# =========================================================================
# PAGE 1: REAL-TIME DETECTION & ANALYTICS
# =========================================================================
if page_selection == "📊 Real-Time Detection & Analytics":
    st.title("🚦 Smart Traffic Management System")
    st.markdown("Real-time multi-lane monitoring, automated vehicle tracking, and metrics telemetry panel.")
    st.divider()

    # --- LIVE SIGNAL CONTROLLER VISUAL HUD ---
    st.subheader("🚦 Real-Time Lane Signal Indicators")
    df_signals = get_postgres_data("SELECT * FROM live_signals;")

    with st.container():
        sig_cols = st.columns(4)
        lanes_list = ["Lane 1", "Lane 2", "Lane 3", "Lane 4"]
        
        signal_dict = {}
        if not df_signals.empty and 'lane_id' in df_signals.columns:
            try:
                for _, s_row in df_signals.iterrows():
                    # Standardizing string formatting to safely capture all lane formats
                    raw_id = str(s_row['lane_id']).strip().lower()
                    l_key = raw_id if "lane" in raw_id else f"lane {raw_id}"
                    
                    signal_dict[l_key] = {
                        'signal_state': str(s_row.get('signal_state', 'RED')).strip().upper(),
                        'green_time_allocated': int(s_row.get('green_time_allocated', 0))
                    }
            except Exception as e:
                st.write(f"HUD Error: {e}")

        for idx, lane_name in enumerate(lanes_list):
            state = "RED"
            seconds = 0
            
            # Map standard presentation name to normalized lookup format
            norm_lookup_key = lane_name.lower()
            if norm_lookup_key in signal_dict:
                state = signal_dict[norm_lookup_key].get('signal_state', 'RED')
                seconds = signal_dict[norm_lookup_key].get('green_time_allocated', 0)
                
            with sig_cols[idx]:
                if str(state).upper() == 'GREEN':
                    st.success(f"### 🟢 {lane_name}")
                    st.metric(label="Active Timing Window", value=f"{seconds}s remaining")
                elif str(state).upper() == 'YELLOW':
                    st.warning(f"### 🟡 {lane_name}")
                    st.metric(label="Caution Phase", value=f"{seconds}s remaining")
                else:
                    st.error(f"### 🔴 {lane_name}")
                    st.markdown(f"🔒 **Status:** Stopped ({seconds}s)")
                
    st.divider()
# --- GEOSPATIAL INTERSECTION TRACKER MAP ---
    st.subheader("🗺️ Live Geospatial Intersection Monitoring Node Map")
    st.markdown("Interactive routing canvas indicating live node congestion thresholds across the metro grid mapping layers.")

    try:
        import folium
        from streamlit_folium import st_folium

       # FIXED GEOSPATIAL INTERSECTION TELEMETRY ANCHORS
        # Lane 1 has been re-anchored to Sirguppa Road, and Lane 4 is set to the SN Pet Flyover Underpass
        LANE_GPS_LOCATIONS = {
            "1": {"display": "Lane 1", "lat": 15.1582, "lng": 76.9341, "road": "Sirguppa Road, Ballari"},
            "2": {"display": "Lane 2", "lat": 15.1432, "lng": 76.9197, "road": "Hosapete Rd / Royal Circle, Ballari"},
            "3": {"display": "Lane 3", "lat": 15.1332, "lng": 76.9248, "road": "Kappagal Rd / Double Road, Ballari"},
            "4": {"display": "Lane 4", "lat": 15.1402, "lng": 76.9189, "road": "SN Pet Flyover Underpass, Ballari"}
        }

        df_latest_counts = get_postgres_data("""
            SELECT lane_id, current_vehicle_count, congestion_level 
            FROM traffic_metrics 
            WHERE id IN (SELECT MAX(id) FROM traffic_metrics GROUP BY lane_id);
        """)
        
        live_counts = {"1": 0, "2": 0, "3": 0, "4": 0}
        live_levels = {"1": "Low", "2": "Low", "3": "Low", "4": "Low"}
        
        if not df_latest_counts.empty and 'lane_id' in df_latest_counts.columns:
            for _, row in df_latest_counts.iterrows():
                # Extract and strip raw lane value, converting strings like 'Lane 1' or 'lane_1' down to simple digits '1'
                raw_lane = str(row['lane_id']).strip().lower().replace("lane", "").replace("_", "").strip()
                
                if raw_lane in live_counts:
                    live_counts[raw_lane] = int(row.get('current_vehicle_count', 0))
                    live_levels[raw_lane] = str(row.get('congestion_level', 'Low')).strip()

        # FIXED DEFAULT LOCATION: Instantly defaults center over central Ballari so it never renders blank
        traffic_map = folium.Map(location=[15.1395, 76.9245], zoom_start=14, tiles="OpenStreetMap")
        marker_points = []

        for internal_key, coords in LANE_GPS_LOCATIONS.items():
            v_queued = live_counts.get(internal_key, 0)
            c_status = live_levels.get(internal_key, "Low")
            display_name = coords["display"]
            lat_val = float(coords['lat'])
            lng_val = float(coords['lng'])
            
            marker_points.append([lat_val, lng_val])
            
            if v_queued >= 15 or str(c_status).lower() in ["heavy", "high"]:
                marker_color = "red"
                badge_icon = "exclamation-sign"
            elif v_queued >= 5 or str(c_status).lower() in ["medium", "moderate"]:
                marker_color = "orange"
                badge_icon = "info-sign"
            else:
                marker_color = "green"
                badge_icon = "ok-sign"

            popup_html = f"""
            <div style="font-family: Arial, sans-serif; width: 180px; font-size: 13px; color: #333333;">
                <h4 style="margin: 0 0 5px 0; color:#007bff;">{display_name} Status</h4>
                <b>📍 Location:</b> {coords['road']}<br>
                <b>🚗 Queued Vehicles:</b> {v_queued} units<br>
                <b>⚠️ Traffic Index:</b> <span style="color:{'red' if marker_color=='red' else ('orange' if marker_color=='orange' else 'green')}; font-weight:bold;">{c_status}</span>
            </div>
            """
            
            folium.Marker(
                location=[lat_val, lng_val],
                popup=folium.Popup(popup_html, max_width=250),
                tooltip=f"{display_name} Telemetry Node Monitor",
                icon=folium.Icon(color=marker_color, icon=badge_icon)
            ).add_to(traffic_map)

        # Only execute boundary adjustments if valid coordinate items were stored
        if marker_points:
            try:
                traffic_map.fit_bounds(marker_points, padding=(40, 40))
            except Exception:
                pass

        @st.fragment
        def render_isolated_hud_map(f_map):
            st_folium(
                f_map, 
                width="100%", 
                height=500, 
                returned_objects=[], 
                key="main_hud_map",
                use_container_width=True
            )
            
        render_isolated_hud_map(traffic_map)
        
    except Exception as map_err:
        st.error(f"Map rendering error: {map_err}")

    st.divider()

    # --- TOP HIGHLIGHT METRIC ROW ---
    st.subheader("📊 System Telemetry Metrics")

    df_metrics = get_postgres_data("""
        SELECT * FROM (
            SELECT * FROM traffic_metrics ORDER BY id DESC LIMIT 100
        ) sub ORDER BY id ASC;
    """)
    
    total_vehicles = get_postgres_data("SELECT count(distinct vehicle_id) as total FROM vehicle_detections")
    
    val = 0
    if not total_vehicles.empty and 'total' in total_vehicles.columns:
        try:
            # FIXED ILOC: Clean index parsing selection prevents data collection structure compile drops
            val = int(total_vehicles.iloc[0, 0])
        except Exception:
            pass

    # Safety fallbacks validation layer to ensure missing scoped metrics variables don't crash layout compilation
    logged_alerts = sidebar_flags if 'sidebar_flags' in locals() or 'sidebar_flags' in globals() else 0

    st.markdown(
        f"""
        <div style="display: flex; gap: 15px; flex-wrap: wrap; margin-bottom: 20px;">
            <div style="flex: 1; min-width: 220px; background-color: #0c2340; color: #ffffff; padding: 15px; border-radius: 8px; border-left: 5px solid #007bff;">
                <div style="font-size: 12px; color: #a0aec0; font-weight: bold; text-transform: uppercase;">🎥 Monitored Streams</div>
                <div style="font-size: 20px; font-weight: bold; margin-top: 5px; white-space: nowrap;">4 Active Lanes</div>
            </div>
            <div style="flex: 1; min-width: 220px; background-color: #0c2340; color: #ffffff; padding: 15px; border-radius: 8px; border-left: 5px solid #28a745;">
                <div style="font-size: 12px; color: #a0aec0; font-weight: bold; text-transform: uppercase;">🚗 Total Vehicles Tracked</div>
                <div style="font-size: 20px; font-weight: bold; margin-top: 5px; white-space: nowrap;">{val} Units</div>
            </div>
            <div style="flex: 1; min-width: 220px; background-color: #0c2340; color: #ffffff; padding: 15px; border-radius: 8px; border-left: 5px solid #dc3545;">
                <div style="font-size: 12px; color: #a0aec0; font-weight: bold; text-transform: uppercase;">⚠️ Congestion Alerts Logged</div>
                <div style="font-size: 20px; font-weight: bold; margin-top: 5px; white-space: nowrap;">{logged_alerts} Flags</div>
            </div>
            <div style="flex: 1; min-width: 220px; background-color: #0c2340; color: #ffffff; padding: 15px; border-radius: 8px; border-left: 5px solid #ffc107;">
                <div style="font-size: 12px; color: #a0aec0; font-weight: bold; text-transform: uppercase;">🕒 System Status</div>
                <div style="font-size: 20px; font-weight: bold; margin-top: 5px; white-space: nowrap;">Online / Live</div>
            </div>
        </div>
        """,
        unsafe_allow_html=True
    )

    st.divider()
    st.subheader("📈 Live Traffic Density & Logs")
    st.markdown("**Multi-Lane Traffic Influx Analytics**")
    
    if not df_metrics.empty and 'lane_id' in df_metrics.columns and 'current_vehicle_count' in df_metrics.columns:
        try:
            time_axis = 'id'
            chart_data = df_metrics.pivot_table(
                index=time_axis, 
                columns='lane_id', 
                values='current_vehicle_count',
                aggfunc='first'
            ).fillna(0)
            
            chart_data = chart_data.sort_index()
            st.bar_chart(chart_data)
                
        except Exception as chart_err:
            st.caption(f"Awaiting chart axis update: {chart_err}")
    else:
        st.info("⌛ Awaiting incoming history feed streams from track.py loop...")
# =========================================================================
# PAGE 2: TRAFFIC VIOLATIONS LOG PANEL (AUTOMATED REAL-TIME STORAGE UI)
# =========================================================================
if page_selection == "🚨 Traffic Violations Log Panel":
    st.title("🚨 Automated Traffic Violations Logging Center")
    st.markdown("Real-time pipeline monitoring vehicle infractions, stop-line breaches, and red-light violations.")
    st.divider()

    # --- ADVANCED MANUAL CONTROL PANEL OVERRIDE (COLLAPSED BY DEFAULT) ---
    with st.expander("🛠️ Manual Enforcement Administration Controls Override Panel"):
        st.markdown("Use this administrative console form override section only if you need to submit records manually.")
        
        with st.form("manual_violation_form", clear_on_submit=True):
            col1, col2 = st.columns(2)
            with col1:
                m_lane = st.selectbox("Select Target Lane Intersection Node", ["Lane 1", "Lane 2", "Lane 3", "Lane 4"])
                m_vtype = st.selectbox("Observed Target Vehicle Classification Type", ["Car", "Auto-rickshaw", "Two-wheeler", "Truck", "Bus", "Ambulance"])
            with col2:
                m_v_id = st.text_input("Vehicle Tracking ID Reference Code (Optional)", placeholder="e.g., 542")
                m_violation = st.selectbox("Enforcement Infraction Violation Category Type", ["Red-light violation", "Wrong-way entry", "Illegal parking node blockage"])
            
            m_details = st.text_area("Details / Incident Evidence Logging Notes (Optional)")
            submit_btn = st.form_submit_button("Save Confirmed Manual Record Entry Log")
            
            if submit_btn:
                try:
                    from traffic_db import save_traffic_violation
                    # Direct integration with the production database table pipeline
                    save_traffic_violation(
                        lane_id=m_lane, 
                        vehicle_id=int(m_v_id) if m_v_id.isdigit() else None, 
                        vehicle_type=m_vtype, 
                        violation_type=m_violation, 
                        details=f"Manual Admin Entry Override: {m_details}"
                    )
                    st.success("Successfully injected administrative enforcement entry log parameters inside database.")
                    st.rerun()
                except Exception as err:
                    st.error(f"Failed to append administrative field data: {err}")

    st.divider()

    # --- LIVE DATA LOGGER FEED STREAM COMPONENT GRID ---
    st.subheader("📋 Active Real-Time Systems Violation Logs Feed Streams")
    
    try:
        # Load data directly from PostgreSQL using simple lowercase columns to prevent mapping mismatches
        df_logs = get_postgres_data("""
            SELECT id, 
                   timestamp, 
                   lane_id, 
                   vehicle_id, 
                   vehicle_type, 
                   violation_type, 
                   details 
            FROM traffic_violations 
            ORDER BY id DESC;
        """)

        # Sync active global telemetry indicator cards counters safely
        if df_logs is not None and not df_logs.empty:
            sidebar_flags = len(df_logs)
        else:
            sidebar_flags = 0

        if df_logs is not None and not df_logs.empty and 'lane_id' in df_logs.columns:
            # Format UI presentation columns cleanly inside a temporary layout frame variable
            df_display = df_logs.copy()
            df_display.columns = [
                "Log ID", "Timestamp", "Lane ID", "Vehicle Tracking ID", 
                "Vehicle Type", "Violation Type", "Incident Capture Details"
            ]

            # Telemetry Metrics Summary Panels Bar
            metric_col1, metric_col2 = st.columns(2)
            with metric_col1:
                st.metric(label="Total Automated Infractions Captured", value=len(df_display))
            with metric_col2:
                st.metric(label="Active Monitoring Nodes with Records", value=df_display["Lane ID"].nunique())
            
            st.markdown("#### Live Monitoring Logging Matrix Feed")
            
            # Interactive Filter Tools Layer Component
            filter_col1, filter_col2 = st.columns(2)
            with filter_col1:
                selected_lane_filter = st.selectbox("Filter Matrix By Target Intersection", ["All Lanes"] + list(df_display["Lane ID"].unique()))
            with filter_col2:
                selected_type_filter = st.selectbox("Filter Matrix By Violation Type", ["All Types"] + list(df_display["Violation Type"].unique()))
            
            # Apply dynamic filtering steps to the presentation data view
            if selected_lane_filter != "All Lanes":
                df_display = df_display[df_display["Lane ID"] == selected_lane_filter]
            if selected_type_filter != "All Types":
                df_display = df_display[df_display["Violation Type"] == selected_type_filter]

            # Render data matrix window
            st.dataframe(df_display, use_container_width=True, hide_index=True)
            
            # Export Options
            csv_data = df_display.to_csv(index=False).encode('utf-8')
            st.download_button(
                label="📥 Export Infraction History Log Output Matrix (CSV)",
                data=csv_data,
                file_name="automated_traffic_violations_report.csv",
                mime="text/csv"
            )
        else:
            st.info("⌛ Awaiting real-time capture stream telemetry records entries from the automated CV processing tracking node loop...")
            
    except Exception as read_err:
        st.error(f"Failed to read automated infraction history tracking table updates: {read_err}")
# =========================================================================
# PAGE 3: DATABASE OPERATIONS CONTROL
# =========================================================================
elif page_selection == "⚙️ Database Operations Control":
    st.title("⚙️ Database Operations Control Panel")
    st.markdown("System administrator utilities to optimize indexing performance and wipe historical cache logs.")
    st.divider()
    
    st.warning("⚠️ Critical Actions: Executing these buttons changes the raw records inside production maps permanently.")
    
    col_maintenance1, col_maintenance2 = st.columns(2)
    
    with col_maintenance1:
        st.subheader("🧹 Clear Logs Data Storage")
        st.markdown("Clears out all historical telemetry updates inside PostgreSQL `traffic_metrics` and resets alert indexes.")
        if st.button("Purge Congestion Logs History", type="primary", use_container_width=True, key="purge_metrics_btn"):
            if execute_postgres_command("TRUNCATE TABLE traffic_metrics RESTART IDENTITY CASCADE;"):
                timestamp_str = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
                with open("maintenance_audit.log", "a", encoding="utf-8") as log_file:
                    log_file.write(f"🧹 [{timestamp_str}] SUCCESS: Purged historical rows from traffic_metrics.\n")
                st.success("✨ Congestion telemetry metrics cleared successfully! UI charts reset.")
                time.sleep(1)
                st.rerun()

    with col_maintenance2:
        st.subheader("🔄 Reset Total Vehicles Tracking Counters")
        st.markdown("Truncates continuous tracking counters matching active vehicle detection layers to zero.")
        if st.button("Reset Tracked Vehicle Counts", use_container_width=True, key="reset_counters_btn"):
            postgres_clear = execute_postgres_command("TRUNCATE TABLE vehicle_detections RESTART IDENTITY CASCADE;")
            sqlite_clear = execute_sqlite_command("DELETE FROM violations;")
            
            if postgres_clear or sqlite_clear:
                if sqlite_clear:
                    execute_sqlite_command("DELETE FROM sqlite_sequence WHERE name='violations';")
                    execute_sqlite_command("VACUUM;")
                timestamp_str = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
                with open("maintenance_audit.log", "a", encoding="utf-8") as log_file:
                    log_file.write(f"🔄 [{timestamp_str}] SUCCESS: Truncated vehicle tracking counters and reset distinct ID indexes.\n")
                st.success("✨ Vehicle tracking logs cleared out! Base frame stats set back to zero.")
                time.sleep(1)
                st.rerun()

    st.divider()
    st.subheader("📋 Administrative Maintenance Action History Log")
    
    try:
        with open("maintenance_audit.log", "r", encoding="utf-8") as log_file:
            log_lines = log_file.readlines()
            
        if log_lines:
            for entry_log in reversed(log_lines):
                st.code(entry_log.strip(), language="text")
        else:
            st.info("⌛ No maintenance operations run on this system environment yet.")
    except FileNotFoundError:
        st.info("⌛ No maintenance operations run on this system environment yet.")

# --- GLOBAL REFRESH ENGINE CONTROLLER ---
time.sleep(2)
st.rerun()        