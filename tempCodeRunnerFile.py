    # --- SAVE UPDATE LOGS TO POSTGRESQL ---
            try:
                connection = psycopg2.connect(**DB_CONFIG)
                cursor = connection.cursor()
                
                # Step A: Turn all lanes RED first
                cursor.execute("UPDATE live_signals SET signal_state = 'RED', green_time_allocated = 0;")
                
                # Step B: Insert or Update the chosen lane to GREEN
                cursor.execute("""
                    INSERT INTO live_signals (lane_id, signal_state, green_time_allocated, last_updated)
                    VALUES (%s, 'GREEN', %s, CURRENT_TIMESTAMP)
                    ON CONFLICT (lane_id) 
                    DO UPDATE SET signal_state = 'GREEN', green_time_allocated = %s, last_updated = CURRENT_TIMESTAMP;
                """, (busiest_lane, allocated_green_time, allocated_green_time))
                
                connection.commit()
                cursor.close()
                connection.close()
            except Exception as db_err:
                print(f"Failed to save signal status: {db_err}")