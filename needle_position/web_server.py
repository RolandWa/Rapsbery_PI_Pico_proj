# web_server.py
from microdot import Microdot, send_file, Response
import uasyncio as asyncio
import gc
import json

# Global application instance
app = Microdot()

# Import the main application's shared state and functions
# This is crucial for controlling the main loop and getting its status
import main as main_app
import config_manager
import motor_control # For pedal reading
import sensor_manager # For sensor status


# --- Web Routes ---

@app.route('/')
async def index(request):
    gc.collect() # Periodically collect garbage
    return send_file('templates/index.html')

@app.route('/static/<path:path>')
def static(request, path):
    return send_file('static/' + path, max_age=86400) # Cache static files for a day

@app.route('/status')
async def status(request):
    # This route provides JSON data for AJAX requests to update the UI
    gc.collect()

    status_data = {
        'pedal_adc': motor_control.read_foot_pedal(), # Read directly from motor_control
        'current_rpm': sensor_manager.current_rpm,    # Read directly from sensor_manager
        'motor_power_percent': motor_control.motor_power_percent,
        'needle_up_active': sensor_manager.get_needle_up_status(),
        'needle_down_active': sensor_manager.get_needle_down_status(),
        'pid_enabled': config_manager.config.get('pid_enabled', False),
        'max_rpm_setting': config_manager.config.get('max_rpm_setting', 0),
        'max_motor_rpm_calibrated': config_manager.config.get('max_motor_rpm', 0),
        'autotune_active': main_app.autotune_active,
        'autotune_stage': main_app.autotune_stage,
        'autotune_kp': config_manager.config.get('kp', 0.0),
        'autotune_ki': config_manager.config.get('ki', 0.0),
        'autotune_kd': config_manager.config.get('kd', 0.0),
        'calibration_active': main_app.max_rpm_calibration_active, 
        'current_debug_mode': 'None' # Can add more debug modes here
    }
    return Response(json.dumps(status_data), headers={'Content-Type': 'application/json'})

@app.route('/set_param', methods=['POST'])
async def set_param(request):
    gc.collect()
    try:
        data = request.json
        param = data.get('param')
        value = data.get('value')

        if param and value is not None:
            if param in config_manager.config:
                # Attempt type conversion based on default config
                default_value = config_manager.config[param]
                if isinstance(default_value, int):
                    config_manager.config[param] = int(value)
                elif isinstance(default_value, float):
                    config_manager.config[param] = float(value)
                elif isinstance(default_value, bool):
                    config_manager.config[param] = str(value).lower() in ('true', '1', 'yes')
                else: # Assume string for others like WiFi creds, stop_position_default
                    config_manager.config[param] = str(value) # Ensure string conversion
                
                config_manager.save_config()
                
                # Signal main_app to re-initialize PID if gains changed
                if param in ['kp', 'ki', 'kd', 'pid_enabled']:
                    main_app.last_pid_kp = None # This will trigger re-initialization in main_loop

                return Response(json.dumps({'status': 'success', 'message': f'Parameter {param} set and saved.'}),
                                headers={'Content-Type': 'application/json'})
            else:
                return Response(json.dumps({'status': 'error', 'message': 'Unknown parameter.'}),
                                status=400, headers={'Content-Type': 'application/json'})
        else:
            return Response(json.dumps({'status': 'error', 'message': 'Missing parameter or value.'}),
                            status=400, headers={'Content-Type': 'application/json'})
    except Exception as e:
        return Response(json.dumps({'status': 'error', 'message': f'Error setting parameter: {e}'}),
                        status=500, headers={'Content-Type': 'application/json'})

@app.route('/calibrate_max_rpm', methods=['POST'])
async def calibrate_max_rpm_web(request):
    gc.collect()
    if not main_app.max_rpm_calibration_active and not main_app.autotune_active:
        main_app.max_rpm_calibration_active = True
        # Launch the calibration task if it's not already running as a persistent task
        # In this setup, run_max_rpm_calibration() is a persistent task in main.py,
        # so we just set the flag.
        return Response(json.dumps({'status': 'success', 'message': 'Max RPM calibration started. Check status for progress.'}),
                        headers={'Content-Type': 'application/json'})
    else:
        return Response(json.dumps({'status': 'error', 'message': 'Calibration or Autotune already active. Stop first.'}),
                        status=409, headers={'Content-Type': 'application/json'})

@app.route('/autotune_pid', methods=['POST'])
async def autotune_pid_web(request):
    gc.collect()
    if not main_app.autotune_active and not main_app.max_rpm_calibration_active:
        main_app.autotune_active = True
        main_app.autotune_stage = 1 # Indicate starting stage
        # Launch the autotune task if it's not already running as a persistent task
        # Similar to calibration, autotune_pid() is a persistent task in main.py.
        return Response(json.dumps({'status': 'success', 'message': 'PID Autotune started. Monitor status and serial for progress.'}),
                        headers={'Content-Type': 'application/json'})
    else:
        return Response(json.dumps({'status': 'error', 'message': 'Autotune or Calibration already active. Stop first.'}),
                        status=409, headers={'Content-Type': 'application/json'})

@app.route('/stop_operations', methods=['POST'])
async def stop_operations_web(request):
    gc.collect()
    main_app.autotune_active = False
    main_app.max_rpm_calibration_active = False
    main_app.set_motor_power(0) # Ensure motor stops
    return Response(json.dumps({'status': 'success', 'message': 'All operations stopped.'}),
                    headers={'Content-Type': 'application/json'})

@app.route('/reboot', methods=['POST'])
async def reboot_device(request):
    gc.collect()
    import machine
    print("Web request: Rebooting Pico...")
    await asyncio.sleep_ms(100) # Give time for response to send
    machine.reset() # Perform a soft reset

# --- Start Server Function ---
async def start_web_server():
    try:
        print("[Web Server] Starting Microdot server...")
        await app.start_server(debug=True, port=80)
    except Exception as e:
        print(f"[Web Server] Failed to start server: {e}")
    finally:
        app.shutdown() # Ensure clean shutdown if fails
        print("[Web Server] Web server stopped.")