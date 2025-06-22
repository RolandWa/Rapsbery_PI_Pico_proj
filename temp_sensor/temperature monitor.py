# main.py for Raspberry Pi Pico W

# This script measures temperature from multiple DS18B20 OneWire sensors,
# serves the data on a simple webpage, and sends the data via MQTT to Domoticz.

# --- Imports ---
import machine
import onewire
import ds18x20
import network
import time
import ubinascii
import json
import os # Import for file system operations
from umqtt.simple import MQTTClient
import _thread # For handling web requests in a separate thread (basic)

# --- Configuration ---
# WiFi credentials
WIFI_SSID = 'YOUR_WIFI_SSID'
WIFI_PASSWORD = 'YOUR_WIFI_PASSWORD'

# MQTT Broker settings
MQTT_BROKER = 'YOUR_MQTT_BROKER_IP' # e.g., '192.168.1.100'
MQTT_PORT = 1883
MQTT_USERNAME = 'YOUR_MQTT_USERNAME' # Leave empty string if no username
MQTT_PASSWORD = 'YOUR_MQTT_PASSWORD' # Leave empty string if no password
MQTT_CLIENT_ID = ubinascii.hexlify(machine.unique_id()).decode('ascii') # Unique ID for MQTT client

# Domoticz settings
# The base topic for Domoticz incoming messages
DOMOTICZ_MQTT_TOPIC = b'domoticz/in'
# Mapping of DS18B20 sensor ROM (address) to Domoticz device IDX
# You will need to find the ROM addresses of your sensors and assign unique IDX values
# in Domoticz for each virtual temperature sensor.
# Example: {'28ffc5a704000003': 123, '28ff12b604000005': 124, ...}
# The ROMs below are placeholders. Replace them with your actual sensor ROMs.
SENSOR_IDX_MAP = {
    # Replace these with your actual 64-bit ROM addresses (e.g., '28FFABCDEF012345')
    # and their corresponding Domoticz IDX values.
    # To find sensor ROMs, run the script and check the console output.
    '28a011a00200007e': 80,  # Example: Sensor 1
    '28b022b00200007e': 81,  # Example: Sensor 2
    '28c033c00200007e': 82,  # Example: Sensor 3
    '28d044d00200007e': 83,  # Example: Sensor 4
    '28e055e00200007e': 84   # Example: Sensor 5
}

# Alarm Configuration
ALARM_TEMPERATURE_LEVEL = 25.0 # Default alarm temperature level in Celsius
ALARM_TRIGGER_DURATION_SECONDS = 60 # Duration in seconds temperature must be above level to trigger alarm
ALARM_VIRTUAL_SWITCH_IDX = 85 # Domoticz IDX for a virtual switch to indicate alarm state (create this in Domoticz)

# File for storing known sensor ROMs and configuration
SENSOR_FILE = 'sensors.json'

# OneWire bus pin (GPIO pin where DS18B20 data line is connected)
ONEWIRE_PIN = 22 # Example: GP22

# Update interval (seconds) for readings and MQTT publishing
UPDATE_INTERVAL_SECONDS = 30


# --- Global Variables ---
sta_if = None
mqtt_client = None
ds_sensors = [] # List to store discovered DS18B20 sensor objects
current_temperatures = {} # Dictionary to store latest temperature readings {rom: temp}

# Alarm state tracking for each sensor
# Key: rom_hex, Value: {'high_start_time': None or time.time(), 'is_triggered': False}
sensor_alarm_states = {}

# --- Functions ---

def save_config():
    """Saves the current configuration (known sensors and alarm level) to sensors.json."""
    global ALARM_TEMPERATURE_LEVEL
    config_data = {
        "known_roms": [s['rom_hex'] for s in ds_sensors], # Save only currently discovered ROMs
        "alarm_level": ALARM_TEMPERATURE_LEVEL
    }
    try:
        with open(SENSOR_FILE, 'w') as f:
            json.dump(config_data, f)
            print(f"Saved configuration to {SENSOR_FILE}.")
    except Exception as e:
        print(f"Error saving configuration to {SENSOR_FILE}: {e}")


def connect_wifi(ssid, password):
    """Connects to the specified Wi-Fi network and sets the hostname."""
    global sta_if
    sta_if = network.WLAN(network.STA_IF)
    if not sta_if.isconnected():
        print('Connecting to WiFi...')
        sta_if.active(True)
        # Set the hostname for mDNS resolution
        sta_if.config(dhcp_hostname='temp_pico')
        print("Setting device hostname to 'temp_pico'")
        
        sta_if.connect(ssid, password)
        # Wait for connection, with timeout
        max_attempts = 10
        attempts = 0
        while not sta_if.isconnected() and attempts < max_attempts:
            print('.', end='')
            time.sleep(1)
            attempts += 1
        if sta_if.isconnected():
            print('\nWiFi connected!')
            print('IP address:', sta_if.ifconfig()[0])
            print("You can try accessing the web page at http://temp_pico/ (if mDNS supported on your network)")
        else:
            print('\nFailed to connect to WiFi after multiple attempts.')
    else:
        print('Already connected to WiFi.')
        print('IP address:', sta_if.ifconfig()[0])
        print("You can try accessing the web page at http://temp_pico/ (if mDNS supported on your network)")


def connect_mqtt():
    """Attempts to connect to the MQTT broker. Returns True on success, False on failure."""
    global mqtt_client
    try:
        if mqtt_client:
            # Attempt to disconnect existing client gracefully before new connection
            try:
                mqtt_client.disconnect()
                print("Disconnected from previous MQTT broker.")
            except Exception as e:
                print(f"Error disconnecting existing MQTT client: {e}")
        
        mqtt_client = MQTTClient(
            client_id=MQTT_CLIENT_ID,
            server=MQTT_BROKER,
            port=MQTT_PORT,
            user=MQTT_USERNAME,
            password=MQTT_PASSWORD
        )
        mqtt_client.connect()
        print(f'Successfully connected to MQTT broker: {MQTT_BROKER}')
        return True
    except OSError as e:
        # Catch network-related errors during connection (e.g., DNS resolution, connection refused)
        print(f'MQTT connection failed (OSError): {e}. Retrying on next cycle.')
        mqtt_client = None # Reset client on failure
        return False
    except Exception as e:
        # Catch any other unexpected errors during connection
        print(f'MQTT connection failed (General Error): {e}. Retrying on next cycle.')
        mqtt_client = None # Reset client on failure
        return False

def discover_ds18b20_sensors(pin):
    """
    Discovers DS18B20 sensors on the OneWire bus and manages their presence in a JSON file.
    It identifies newly found sensors and those that are no longer reachable.
    """
    global ds_sensors, current_temperatures, sensor_alarm_states, ALARM_TEMPERATURE_LEVEL

    ds_pin = machine.Pin(pin)
    ow = onewire.OneWire(ds_pin)
    ds = ds18x20.DS18X20(ow)

    # 1. Load previously known sensors and alarm level from file
    known_rom_hexes = []
    loaded_alarm_level = ALARM_TEMPERATURE_LEVEL # Default to current global value
    try:
        with open(SENSOR_FILE, 'r') as f:
            config_data = json.load(f)
            if "known_roms" in config_data:
                known_rom_hexes = config_data["known_roms"]
                print(f"Loaded {len(known_rom_hexes)} previously known sensors from {SENSOR_FILE}.")
            if "alarm_level" in config_data:
                loaded_alarm_level = config_data["alarm_level"]
                print(f"Loaded alarm level: {loaded_alarm_level}°C from {SENSOR_FILE}.")
                ALARM_TEMPERATURE_LEVEL = loaded_alarm_level # Update global alarm level
    except OSError:
        print(f"No existing sensor file '{SENSOR_FILE}' found. Will create one if sensors are found.")
    except ValueError: # JSON decoding error
        print(f"Error decoding JSON from '{SENSOR_FILE}'. File might be corrupt. Starting fresh.")
    except Exception as e:
        print(f"Unexpected error loading config from '{SENSOR_FILE}': {e}. Starting fresh.")
    
    # Convert known_rom_hexes to a set for efficient lookup
    known_rom_hexes_set = set(known_rom_hexes)

    # 2. Scan for currently connected sensors
    current_scan_roms = ds.scan()
    current_scan_rom_hexes_set = set(ubinascii.hexlify(rom).decode('ascii') for rom in current_scan_roms)

    # Prepare for the new ds_sensors list and update current_temperatures/sensor_alarm_states
    new_ds_sensors = []
    updated_current_temperatures = {}
    updated_sensor_alarm_states = {}
    
    # Combine all known and newly scanned ROMs to track
    all_active_rom_hexes = sorted(list(known_rom_hexes_set.union(current_scan_rom_hexes_set)))

    print('\n--- Sensor Discovery Report ---')

    if not all_active_rom_hexes:
        print("No DS18B20 devices found on OneWire bus and no previous sensors known.")
        # If no sensors ever known or found, ensure lists are empty and file is cleaned
        ds_sensors = []
        current_temperatures = {}
        sensor_alarm_states = {}
        # Try to delete the file if no sensors are present, as it might be empty or hold old data
        try:
            if SENSOR_FILE in os.listdir():
                os.remove(SENSOR_FILE)
                print(f"Removed empty sensor file: {SENSOR_FILE}")
        except OSError as e:
            print(f"Could not remove sensor file {SENSOR_FILE}: {e}")
        return

    for rom_hex in all_active_rom_hexes:
        if rom_hex in current_scan_rom_hexes_set:
            # Sensor is currently connected
            print(f"  - FOUND: {rom_hex}")
            rom_bytes = ubinascii.unhexlify(rom_hex) # Convert back to bytes for ds18x20 object
            new_ds_sensors.append({'ds_object': ds, 'rom': rom_bytes, 'rom_hex': rom_hex})
            # Initialize with 'Pending' or keep existing good value if available, will be updated by read_temperatures
            updated_current_temperatures[rom_hex] = current_temperatures.get(rom_hex, 'Pending')
            updated_sensor_alarm_states[rom_hex] = sensor_alarm_states.get(rom_hex, {'high_start_time': None, 'is_triggered': False})
        else:
            # Sensor was known but is not currently connected (connection error)
            print(f"  - ERROR: Sensor {rom_hex} (previously known) is now unreachable.")
            updated_current_temperatures[rom_hex] = 'Error' # Mark as error
            # If it was an alarm, clear it as it's unreachable
            updated_sensor_alarm_states[rom_hex] = {'high_start_time': None, 'is_triggered': False}

    ds_sensors = new_ds_sensors
    current_temperatures = updated_current_temperatures
    sensor_alarm_states = updated_sensor_alarm_states

    # 3. Save the *currently found* (and therefore known good) ROMs and current alarm level back to the file
    save_config()

    return ds_sensors

def read_temperatures():
    """
    Reads temperature from all currently connected DS18B20 sensors and updates
    the global current_temperatures dictionary. Sensors not currently connected
    will retain their 'Error' status set during discovery.
    """
    global current_temperatures
    
    # Create a copy to update, preserving states of disconnected sensors
    temp_readings_new = current_temperatures.copy() 

    if not ds_sensors:
        print("No DS18B20 sensors are currently connected to read from.")
        # All sensors in temp_readings_new should already be 'Error' if ds_sensors is empty
        return

    # Trigger temperature conversion for all *currently connected* sensors
    try:
        # ds_sensors[0]['ds_object'] should be valid here if ds_sensors is not empty
        ds_sensors[0]['ds_object'].convert_temp()
        time.sleep_ms(750) # Wait for conversion to complete (max 750ms for 12-bit resolution)
    except IndexError: # Should theoretically not happen here if ds_sensors is checked above
        print("Logic Error: ds_sensors list became empty unexpectedly during read_temperatures.")
        return
    except Exception as e:
        print(f"Error during temperature conversion trigger: {e}. Marking connected sensors as error for this cycle.")
        for sensor in ds_sensors:
            temp_readings_new[sensor['rom_hex']] = 'Error' # Mark current connected sensors as error
        current_temperatures = temp_readings_new
        return

    for sensor in ds_sensors:
        rom_hex = sensor['rom_hex']
        try:
            temp = sensor['ds_object'].read_temp(sensor['rom'])
            temp_readings_new[rom_hex] = round(temp, 2)
        except onewire.OneWireError as e:
            print(f"Error reading sensor {rom_hex}: {e}. Marking as error.")
            temp_readings_new[rom_hex] = 'Error' # Mark as error
        except Exception as e:
            print(f"Unexpected error reading sensor {rom_hex}: {e}. Marking as error.")
            temp_readings_new[rom_hex] = 'Error'

    current_temperatures = temp_readings_new
    print("Current Temperatures:", current_temperatures)

def publish_temperatures_mqtt():
    """Publishes current temperatures to Domoticz via MQTT."""
    global mqtt_client
    if not mqtt_client or not mqtt_client.is_connected():
        print("MQTT client not connected. Attempting to reconnect before publishing temperatures...")
        if not connect_mqtt():
            print("Failed to reconnect to MQTT. Skipping temperature publishing for this cycle.")
            return # Cannot publish if connection fails

    for rom_hex, temp in current_temperatures.items():
        if rom_hex in SENSOR_IDX_MAP: # Check if IDX is mapped, regardless of temp value
            idx = SENSOR_IDX_MAP[rom_hex]
            payload = {}
            if temp == 'Error':
                # Send 255 for connection error to Domoticz
                payload = {
                    "idx": idx,
                    "nvalue": 0,
                    "svalue": "255" # Value 255 indicates error/unreachable in Domoticz (for temp sensors)
                }
                print(f"Published MQTT: Sensor {rom_hex} (IDX: {idx}) Error (255)")
            else:
                # Send actual temperature
                payload = {
                    "idx": idx,
                    "nvalue": 0,
                    "svalue": str(temp)
                }
                # print(f"Published MQTT: Sensor {rom_hex} (IDX: {idx}) Temp: {temp}°C") # Uncomment for verbose output
            
            try:
                mqtt_client.publish(DOMOTICZ_MQTT_TOPIC, json.dumps(payload).encode('utf-8'))
            except Exception as e:
                print(f"Failed to publish MQTT for sensor {rom_hex} (IDX: {idx}, Value: {temp if temp != 'Error' else 'Error'}): {e}")
        else:
            print(f"Warning: Sensor ROM {rom_hex} not found in SENSOR_IDX_MAP. Not publishing.")


def get_web_page():
    """Generates the HTML content for the web page."""
    global ALARM_TEMPERATURE_LEVEL
    # Corrected meta charset to ensure proper character display for degree symbol
    html = f"""<!DOCTYPE html>
<html>
<head>
    <title>Pico W Temperature Monitor</title>
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <meta charset="UTF-8"> <!-- Added or corrected charset -->
    <style>
        body {{ font-family: 'Inter', sans-serif; background-color: #f0f4f8; margin: 0; padding: 20px; display: flex; flex-direction: column; align-items: center; justify-content: center; min-height: 100vh; color: #334155; }}
        .container {{ background-color: #ffffff; border-radius: 12px; box-shadow: 0 4px 8px rgba(0,0,0,0.1); padding: 30px; text-align: center; width: 90%; max-width: 500px; }}
        h1 {{ color: #1e293b; margin-bottom: 25px; font-size: 1.8em; }}
        h2 {{ color: #1e293b; margin-top: 25px; margin-bottom: 15px; font-size: 1.4em; }}
        .sensor-card {{ background-color: #e2e8f0; border-radius: 8px; padding: 15px; margin-bottom: 15px; display: flex; justify-content: space-between; align-items: center; }}
        .sensor-label {{ font-weight: bold; color: #475569; }}
        .temperature-value {{ font-size: 1.5em; color: #0f766e; font-weight: bold; }}
        .error-text {{ color: #dc2626; font-size: 1.2em; font-weight: bold; }} /* New style for error messages */
        .footer {{ margin-top: 30px; font-size: 0.8em; color: #64748b; }}
        .last-update {{ font-size: 0.9em; margin-top: 15px; color: #475569; }}
        .alarm-config {{ background-color: #e0f2f7; border-radius: 8px; padding: 20px; margin-top: 20px; border: 1px solid #a7d9ee; }}
        .alarm-config p {{ margin: 5px 0; }}
        .alarm-config form {{ display: flex; flex-direction: column; gap: 10px; align-items: center; }}
        .alarm-config label {{ font-weight: bold; color: #086e8e; }}
        /* Corrected input value format to use dot for decimal */
        .alarm-config input[type="number"] {{ padding: 8px; border: 1px solid #a7d9ee; border-radius: 5px; width: 100px; text-align: center; font-size: 1em; }}
        .alarm-config button {{ background-color: #2e8b57; color: white; padding: 10px 20px; border: none; border-radius: 8px; cursor: pointer; font-size: 1em; transition: background-color 0.3s ease; box-shadow: 0 2px 4px rgba(0,0,0,0.2); }}
        .alarm-config button:hover {{ background-color: #3cb371; }}
        .alarm-indicator {{ margin-top: 10px; font-weight: bold; color: #dc2626; animation: blink 1s infinite; }}
        @keyframes blink {{ 0% {{ opacity: 1; }} 50% {{ opacity: 0; }} 100% {{ opacity: 1; }} }}
        @media (max-width: 600px) {{
            .container {{ padding: 20px; }}
            h1 {{ font-size: 1.5em; }}
            .sensor-card {{ flex-direction: column; align-items: flex-start; gap: 5px; }}
            .temperature-value {{ font-size: 1.3em; }}
            .alarm-config input[type="number"] {{ width: 80px; }}
        }}
    </style>
</head>
<body>
    <div class="container">
        <h1>🏡 Temperature Readings</h1>
"""
    # Add sensor data
    if current_temperatures:
        for rom_hex, temp in current_temperatures.items():
            # Get a more readable sensor label from the map if available, otherwise use ROM
            display_label = f"Sensor {SENSOR_IDX_MAP.get(rom_hex, 'Unknown')}" if rom_hex in SENSOR_IDX_MAP else f"Sensor {rom_hex[-4:]}" # Use last 4 digits of ROM
            
            temp_display_class = "temperature-value"
            display_value = f"{temp}°C"
            if temp == 'Error':
                display_value = "Connection Error"
                temp_display_class = "error-text" # Apply the new error style

            html += f"""
        <div class="sensor-card">
            <span class="sensor-label">{display_label}:</span>
            <span class="{temp_display_class}">{display_value}</span>
        </div>
"""
    else:
        html += """
        <p>No temperature data available yet.</p>
"""
    
    # Add Alarm Configuration section
    # Value is formatted to use a dot as decimal separator
    html += f"""
        <div class="alarm-config">
            <h2>🚨 Alarm Settings</h2>
            <p>Current Alarm Level: <span id="currentAlarmLevel">{ALARM_TEMPERATURE_LEVEL:.1f}</span>°C</p>
            <form action="/set_alarm_level" method="post">
                <label for="new_alarm_level">Set New Alarm Level (°C):</label>
                <input type="number" id="new_alarm_level" name="new_alarm_level" step="0.1" value="{ALARM_TEMPERATURE_LEVEL:.1f}">
                <button type="submit">Update Alarm Level</button>
            </form>
            <p class="last-update">Alarm duration before trigger: {ALARM_TRIGGER_DURATION_SECONDS} seconds</p>
        </div>
"""
    
    # Check if any alarm is currently triggered to display an indicator
    any_alarm_triggered = False
    for rom_hex, state in sensor_alarm_states.items():
        if state['is_triggered']:
            any_alarm_triggered = True
            break
            
    if any_alarm_triggered:
        html += """
        <p class="alarm-indicator">ALARM! High Temperature Detected!</p>
        """

    html += f"""
        <p class="last-update">Last Updated: {time.localtime()[3]:02}:{time.localtime()[4]:02}:{time.localtime()[5]:02}</p>
        <div class="footer">
            <p>Powered by Raspberry Pi Pico W</p>
        </div>
    </div>
</body>
</html>
"""
    return html


def web_server_thread():
    """Handles incoming web server connections in a separate thread."""
    global ALARM_TEMPERATURE_LEVEL
    s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    s.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1) # Allow reuse of address
    s.bind(('', 80)) # Listen on port 80 (HTTP)
    s.listen(5) # Max 5 pending connections
    print("Web server listening on port 80")

    while True:
        try:
            conn, addr = s.accept()
            print('Got a connection from %s:%s' % (addr[0], addr[1]))
            request_bytes = conn.recv(1024)
            # Decode with 'utf-8' now that meta charset is set
            request = request_bytes.decode('utf-8', 'ignore') 
            
            # Handle POST request to set alarm level
            if request.find('POST /set_alarm_level HTTP/1.1') != -1:
                try:
                    # Find the body of the POST request
                    # Split the request by double CRLF to separate headers from body
                    parts = request.split('\r\n\r\n', 1)
                    if len(parts) > 1:
                        post_data_str = parts[1]
                        
                        # Very basic parsing for 'new_alarm_level=XX.X'
                        if 'new_alarm_level=' in post_data_str:
                            value_str = post_data_str.split('new_alarm_level=')[1].split('&')[0]
                            new_level = float(value_str) # float() expects dot as decimal separator
                            ALARM_TEMPERATURE_LEVEL = new_level
                            print(f"Alarm level updated to: {ALARM_TEMPERATURE_LEVEL}°C via web.")
                            save_config() # Save the updated alarm level to file
                            response_text = f"Alarm level updated to {ALARM_TEMPERATURE_LEVEL:.1f}°C."
                        else:
                            response_text = "Invalid alarm level provided."
                            print("Invalid alarm level provided in POST request.")
                    else:
                        response_text = "No POST data found."
                        print("No POST data found in request.")

                    # Send a redirect response back to the home page
                    conn.send(b'HTTP/1.1 303 See Other\r\n') # 303 for POST redirects
                    conn.send(b'Location: /\r\n')
                    conn.send(b'Content-Type: text/plain\r\n')
                    conn.send(b'Content-Length: %d\r\n\r\n' % len(response_text))
                    conn.send(response_text.encode('utf-8'))
                    conn.close()

                except ValueError:
                    print("Error: Could not convert new_alarm_level to float. Ensure dot is used for decimals.")
                    conn.send(b'HTTP/1.1 400 Bad Request\r\n\r\n')
                    conn.send(b'Invalid number format for alarm level. Please use a dot for decimals.\r\n')
                    conn.close()
                except Exception as e:
                    print(f"Error parsing alarm level POST: {e}")
                    conn.send(b'HTTP/1.1 400 Bad Request\r\n\r\n')
                    conn.send(b'Error processing request.\r\n')
                    conn.close()

            # Handle GET request for the main page
            elif request.find('GET / HTTP/1.1') != -1:
                response = get_web_page()
                conn.send(b'HTTP/1.1 200 OK\r\n')
                conn.send(b'Content-Type: text/html\r\n')
                conn.send(b'Connection: close\r\n\r\n')
                # Explicitly encode the HTML response to UTF-8
                conn.sendall(response.encode('utf-8')) 
                conn.close()
            else:
                # Handle other requests or 404
                conn.send(b'HTTP/1.1 404 Not Found\r\n\r\n')
                conn.send(b'404 Not Found\r\n')
                conn.close()

        except OSError as e:
            print(f'Web server connection error: {e}')
            # conn.close() might be needed here if 'e' is a client disconnection
        except Exception as e:
            print(f'Unexpected web server error: {e}')
            if 'conn' in locals() and conn:
                conn.close() # Ensure connection is closed on error
        time.sleep(0.1) # Small delay to yield to other operations


# --- Main Application Logic ---
def main():
    global ds_sensors, current_temperatures, sensor_alarm_states

    print("Starting Pico W Temperature Monitor...")

    # 1. Connect to WiFi
    connect_wifi(WIFI_SSID, WIFI_PASSWORD)
    if not sta_if.isconnected():
        print("Exiting: Could not connect to WiFi. Please check credentials and try again.")
        return

    # 2. Discover DS18B20 sensors
    # This function now handles loading/saving sensor data to/from SENSOR_FILE
    discover_ds18b20_sensors(ONEWIRE_PIN)
    
    # 3. Connect to MQTT initially
    # This will be retried in the main loop if connection is lost
    connect_mqtt()

    # 4. Start web server in a separate thread
    try:
        _thread.start_new_thread(web_server_thread, ())
    except Exception as e:
        print(f"Failed to start web server thread: {e}")
        print("Web server functionality might be unavailable.")

    # 5. Main loop for sensor reading, MQTT publishing, and alarm monitoring
    last_update_time = time.time() - UPDATE_INTERVAL_SECONDS # Force immediate update on start
    while True:
        try:
            current_time = time.time()
            if current_time - last_update_time >= UPDATE_INTERVAL_SECONDS:
                print("\n--- Performing periodic update ---")
                
                # Read temperatures for currently connected sensors
                read_temperatures()

                # Publish temperatures via MQTT (including errors as 255)
                publish_temperatures_mqtt()
                
                last_update_time = current_time

            # --- Alarm Monitoring Logic ---
            # Check for high temperature alarms
            for rom_hex, temp in current_temperatures.items():
                # Ensure sensor_alarm_states is initialized for this sensor
                sensor_alarm_states.setdefault(rom_hex, {'high_start_time': None, 'is_triggered': False})

                if temp == 'Error':
                    # If reading error, clear any active alarm state for this sensor
                    if sensor_alarm_states[rom_hex]['high_start_time'] is not None:
                        print(f"Sensor {rom_hex} temp read error. Resetting alarm timer.")
                        sensor_alarm_states[rom_hex]['high_start_time'] = None
                    if sensor_alarm_states[rom_hex]['is_triggered']:
                        print(f"Alarm for sensor {rom_hex} cleared due to read error.")
                        sensor_alarm_states[rom_hex]['is_triggered'] = False
                    continue # Skip alarm processing for erroneous readings (as 255 is not a valid alarm temp)

                if temp > ALARM_TEMPERATURE_LEVEL:
                    # Temperature is above alarm level
                    if sensor_alarm_states[rom_hex]['high_start_time'] is None:
                        # First time temp goes high, start timer
                        sensor_alarm_states[rom_hex]['high_start_time'] = current_time
                        print(f"Sensor {rom_hex} temp {temp}°C > {ALARM_TEMPERATURE_LEVEL}°C. Starting alarm timer.")
                    
                    # Check if duration passed and alarm not yet triggered for this sensor
                    if not sensor_alarm_states[rom_hex]['is_triggered'] and \
                       (current_time - sensor_alarm_states[rom_hex]['high_start_time']) >= ALARM_TRIGGER_DURATION_SECONDS:
                        
                        sensor_alarm_states[rom_hex]['is_triggered'] = True
                        print(f"ALARM TRIGGERED for sensor {rom_hex}! Temp: {temp}°C")
                        
                        # Check if any alarm is now active (overall system alarm)
                        any_alarm_active_now = False
                        for state in sensor_alarm_states.values():
                            if state['is_triggered']:
                                any_alarm_active_now = True
                                break
                        
                        # Turn on the general alarm switch in Domoticz if it's not already on
                        if any_alarm_active_now:
                            alarm_payload = {
                                "idx": ALARM_VIRTUAL_SWITCH_IDX,
                                "nvalue": 1, # 1 for On
                                "svalue": "1"
                            }
                            # Ensure MQTT client is connected before publishing alarm
                            if not mqtt_client or not mqtt_client.is_connected():
                                print("MQTT client not connected. Attempting to reconnect for alarm publishing...")
                                if not connect_mqtt():
                                    print("Failed to reconnect to MQTT. Skipping alarm ON publish.")
                                    # Still set alarm_triggered but can't notify Domoticz
                                else:
                                    try:
                                        mqtt_client.publish(DOMOTICZ_MQTT_TOPIC, json.dumps(alarm_payload).encode('utf-8'))
                                        print(f"Published MQTT: General Alarm ON (IDX: {ALARM_VIRTUAL_SWITCH_IDX})")
                                    except Exception as e:
                                        print(f"Failed to publish general alarm ON MQTT: {e}")
                            else:
                                try:
                                    mqtt_client.publish(DOMOTICZ_MQTT_TOPIC, json.dumps(alarm_payload).encode('utf-8'))
                                    print(f"Published MQTT: General Alarm ON (IDX: {ALARM_VIRTUAL_SWITCH_IDX})")
                                except Exception as e:
                                    print(f"Failed to publish general alarm ON MQTT: {e}")

                else: # Temperature is NOT above alarm level
                    # If temperature dropped below threshold, reset timer
                    if sensor_alarm_states[rom_hex]['high_start_time'] is not None:
                        print(f"Sensor {rom_hex} temp {temp}°C <= {ALARM_TEMPERATURE_LEVEL}°C. Resetting alarm timer.")
                        sensor_alarm_states[rom_hex]['high_start_time'] = None
                        
                    # If temperature dropped and alarm was previously triggered for this sensor, clear it
                    if sensor_alarm_states[rom_hex]['is_triggered']:
                        sensor_alarm_states[rom_hex]['is_triggered'] = False
                        print(f"Alarm for sensor {rom_hex} CLEARED.")
                        
                        # Check if ALL other alarms are now cleared. If so, turn off general alarm.
                        all_alarms_cleared = True
                        for state in sensor_alarm_states.values():
                            if state['is_triggered']:
                                all_alarms_cleared = False
                                break
                        
                        if all_alarms_cleared:
                            alarm_payload = {
                                "idx": ALARM_VIRTUAL_SWITCH_IDX,
                                "nvalue": 0, # 0 for Off
                                "svalue": "0"
                            }
                            # Ensure MQTT client is connected before publishing alarm clear
                            if not mqtt_client or not mqtt_client.is_connected():
                                print("MQTT client not connected. Attempting to reconnect for alarm clear publishing...")
                                if not connect_mqtt():
                                    print("Failed to reconnect to MQTT. Skipping alarm OFF publish.")
                                else:
                                    try:
                                        mqtt_client.publish(DOMOTICZ_MQTT_TOPIC, json.dumps(alarm_payload).encode('utf-8'))
                                        print(f"Published MQTT: General Alarm OFF (IDX: {ALARM_VIRTUAL_SWITCH_IDX})")
                                    except Exception as e:
                                        print(f"Failed to publish general alarm OFF MQTT: {e}")
                            else:
                                try:
                                    mqtt_client.publish(DOMOTICZ_MQTT_TOPIC, json.dumps(alarm_payload).encode('utf-8'))
                                    print(f"Published MQTT: General Alarm OFF (IDX: {ALARM_VIRTUAL_SWITCH_IDX})")
                                except Exception as e:
                                    print(f"Failed to publish general alarm OFF MQTT: {e}")
            
            # Small delay to keep the loop from spinning too fast
            time.sleep(1) 

        except KeyboardInterrupt:
            print("KeyboardInterrupt: Exiting.")
            break
        except Exception as e:
            print(f"Main loop error: {e}")
            time.sleep(5) # Wait before retrying after an error


# --- Entry Point ---
if __name__ == '__main__':
    # Ensure network module is imported for socket
    import socket
    main()
    