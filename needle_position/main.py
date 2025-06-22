# main.py
import uasyncio as asyncio
import utime
from machine import Pin 
import network 

from config_manager import config, load_config, save_config
from wifi_manager import get_wifi_status 
from motor_control import init_motor_control, set_motor_power, read_foot_pedal, \
                          get_target_rpm_from_pedal, motor_power_percent, PID, \
                          triac_firing_task, ac_half_cycle_time_us, adc_max_value # ADDED adc_max_value HERE!
from sensor_manager import init_sensors, get_needle_up_status, get_needle_down_status, calculate_rpm

# Import web server functions (Microdot app instance will be started here)
import web_server

# --- Global State Variables (Accessed by Web Server) ---
is_pedal_pressed = False
soft_start_active = False
current_soft_start_power = 0 
target_rpm_setpoint = 0 
last_rpm = 0 # Updated by calculate_rpm() in sensor_manager, read by main_loop and web_server

pid_controller = None 
last_pid_kp = None 
last_pid_ki = None
last_pid_kd = None

# --- Calibration and Autotune Flags ---
max_rpm_calibration_active = False
autotune_active = False
autotune_stage = 0 # 0: idle, 1: oscillation, 2: complete/error

# --- Calibration and Autotune Helper Functions ---

async def run_max_rpm_calibration():
    global max_rpm_calibration_active
    print("\n--- Max RPM Calibration Initiated ---")
    print("Running motor at 100% power for 5 seconds to find max RPM...")
    
    max_observed_rpm = 0
    set_motor_power(100) # Full power
    
    start_time = utime.ticks_ms()
    calibration_duration_ms = 5000 # Run for 5 seconds

    while utime.ticks_diff(utime.ticks_ms(), start_time) < 0 and max_rpm_calibration_active:
        current_rpm = calculate_rpm()
        if current_rpm > max_observed_rpm:
            max_observed_rpm = current_rpm
        
        print(f"Max RPM Calibration: Current RPM = {current_rpm}, Max Observed = {max_observed_rpm}")
        await asyncio.sleep_ms(100) # Sample every 100ms
    
    set_motor_power(0) # Stop motor
    
    if max_rpm_calibration_active: # Check if not stopped by user
        config['max_motor_rpm'] = max_observed_rpm
        save_config()
        print(f"--- Max RPM Calibration Complete: Max Motor RPM set to {max_observed_rpm} ---")
    else:
        print("Max RPM Calibration stopped by user.")
    
    max_rpm_calibration_active = False # Reset flag

async def autotune_pid():
    global autotune_active, autotune_stage, autotune_start_time, \
           autotune_max_power_pulse, autotune_min_power_pulse, \
           autotune_rpm_peak, autotune_rpm_valley
    
    autotune_target_rpm = config.get('autotune_target_rpm', 300)
    autotune_power_high = config.get('autotune_power_high', 70)
    autotune_power_low = config.get('autotune_power_low', 30)

    print("\n--- PID Autotune Initiated (Ziegler-Nichols-like Oscillation Method) ---")
    print(f"Target RPM for tuning: {autotune_target_rpm}")
    print(f"Power range: {autotune_power_low}% to {autotune_power_high}%")
    
    autotune_active = True
    autotune_stage = 1 # Indicate active stage
    pid_controller.reset() # Reset PID before tuning
    
    # Stage 1: Induce oscillation
    print("Stage 1: Inducing oscillations...")
    set_motor_power(autotune_power_high) # Start with high power
    await asyncio.sleep(2) # Give motor time to speed up
    
    peak_count = 0
    valley_count = 0
    
    # Variables for oscillation period (Pu)
    last_peak_time = 0
    oscillation_periods = []
    
    # Variables for ultimate gain (Ku)
    max_rpm_in_oscillation = 0
    min_rpm_in_oscillation = 9999
    
    autotune_start_time = utime.ticks_ms()
    tuning_timeout = utime.ticks_ms() + 45000 # Max 45 seconds for autotune

    last_rpm_sample_time = utime.ticks_ms()

    while autotune_active and utime.ticks_diff(utime.ticks_ms(), tuning_timeout) < 0:
        current_rpm = calculate_rpm() # Get live RPM

        # Only proceed if we have valid RPM data and motor is running
        if current_rpm > 10 and utime.ticks_diff(utime.ticks_ms(), last_rpm_sample_time) >= 100: # Sample every 100ms
            last_rpm_sample_time = utime.ticks_ms()

            # Apply alternating power pulses based on deviation from target
            if current_rpm < autotune_target_rpm * 0.9: # If RPM too low, boost power
                set_motor_power(autotune_power_high)
            elif current_rpm > autotune_target_rpm * 1.1: # If RPM too high, reduce power
                set_motor_power(autotune_power_low)
            # else: hold current power

            # Detect peaks and valleys
            if current_rpm > max_rpm_in_oscillation:
                max_rpm_in_oscillation = current_rpm
            if current_rpm < min_rpm_in_oscillation:
                min_rpm_in_oscillation = current_rpm

            # Basic peak/valley detection (could be more robust with hysteresis)
            if last_rpm < current_rpm and last_rpm_sample_time > autotune_start_time + 1000: # Ensure some initial run
                # RPM is increasing
                pass
            elif last_rpm > current_rpm and last_rpm_sample_time > autotune_start_time + 1000:
                # RPM is decreasing
                pass

            # A more robust oscillation detection would involve looking for several consecutive
            # increases/decreases followed by a turn-around. For now, we'll keep it simple:
            # Look for a significant change in trend that marks a peak/valley.

            # Simple (but often noisy) trend analysis:
            # If we were going up and now going down (peak)
            # If we were going down and now going up (valley)
            
            # This part requires a state machine or more sophisticated logic for robust Z-N.
            # For this example, we'll just track max/min RPM during the period and estimates period.
            # We assume the fixed power toggling *will* induce an oscillation.

            # We'll collect RPM samples and derive peaks/valleys from that
            # This simplified version just uses the overall max/min in the window and estimates period.
            
            # To measure period, we need to detect at least 2 consecutive peaks or valleys.
            # This is a common weakness of simplified ZN.
            # A more reliable method is often "relay auto-tuning" or a more complex algorithm.

            # For now, let's simplify and just run for a fixed time to collect RPM range
            # and estimate period as the time it takes for RPM to swing from low to high.
            
            # After a minimum run time, we can try to estimate Pu and Ku
            if utime.ticks_diff(utime.ticks_ms(), autotune_start_time) > 10000: # After 10 seconds of oscillation attempt
                if (max_rpm_in_oscillation - min_rpm_in_oscillation) > autotune_target_rpm * 0.1: # Check for significant oscillation (10% of target RPM)
                    # We have an oscillation!
                    # Estimate Pu (period) roughly as time between significant peaks/valleys.
                    # Or, as a simple approximation, if we just toggled, the period is about 2 * (time to go from low to high)
                    
                    # For a basic approach: If we induced an oscillation with `autotune_power_high` and `autotune_power_low`,
                    # and the system is roughly oscillating around `autotune_target_rpm`, we can estimate `Pu`.
                    # A very simple Pu estimation could be the time it takes from min to max RPM in the cycle.
                    # This is not robust for ZN.

                    # Let's assume after 15 seconds, we have enough data for a rough Pu and Ku
                    # This is a placeholder for a more robust peak/valley detection and period calculation.
                    
                    # Estimate Pu (a very rough method if we don't have good peak detection)
                    # Assuming an oscillation, a typical industrial system might oscillate at 0.5-2 Hz (Pu = 0.5-2s)
                    Pu = 2.0 # Placeholder: Assume a 2-second oscillation period for now (needs refinement or actual measurement)
                    
                    # Estimate Ku: Ratio of power change to RPM change.
                    delta_power = autotune_power_high - autotune_power_low
                    delta_rpm_oscillation = max_rpm_in_oscillation - min_rpm_in_oscillation
                    
                    if delta_rpm_oscillation > 0:
                        Ku = delta_power / delta_rpm_oscillation
                    else:
                        Ku = 0.5 # Default if no RPM swing detected
                    
                    # Ziegler-Nichols (Continuous Cycling Method) Formulas:
                    kp_zn = 0.6 * Ku
                    ti_zn = Pu / 2.0
                    td_zn = Pu / 8.0
                    
                    ki_zn = kp_zn / ti_zn if ti_zn > 0 else 0
                    kd_zn = kp_zn * td_zn
                    
                    print("\n--- Autotune Results ---")
                    print(f"Approximate Ultimate Gain (Ku): {Ku:.2f}")
                    print(f"Estimated Oscillation Period (Pu): {Pu:.2f} seconds")
                    print(f"Recommended PID Gains (Ziegler-Nichols):")
                    print(f"  Kp: {kp_zn:.3f}")
                    print(f"  Ki: {ki_zn:.3f}")
                    print(f"  Kd: {kd_zn:.3f}")

                    # Update config with new PID values
                    config['kp'] = round(kp_zn, 3)
                    config['ki'] = round(ki_zn, 3)
                    config['kd'] = round(kd_zn, 3)
                    config['pid_enabled'] = True # Enable PID after tuning
                    save_config()
                    print("PID gains saved to config.json. PID control is now ENABLED.")
                    
                    autotune_stage = 2 # Indicate complete
                    autotune_active = False # End autotune
                    set_motor_power(0) # Stop motor
                    break # Exit loop
                else:
                    print("Autotune: Insufficient RPM oscillation. Continue trying...")
        
        await asyncio.sleep_ms(50) # Sample RPM and adjust power

    if autotune_active: # If timeout occurred
        print("Autotune timed out. Could not find stable oscillations.")
        autotune_stage = 0 # Back to idle
    
    autotune_active = False
    set_motor_power(0) # Ensure motor stops
    print("Autotune finished.")

# --- Main control loop ---
async def main_loop():
    global is_pedal_pressed, soft_start_active, current_soft_start_power, target_rpm_setpoint, last_rpm, pid_controller
    global last_pid_kp, last_pid_ki, last_pid_kd 

    # Initial motor control setup
    init_motor_control() # This now initializes ZC and TRIAC pins
    init_sensors()

    print("[Main] Entering main application loop...")
    while True:
        # Update RPM (shared global)
        last_rpm = calculate_rpm()
        
        # --- Handle Active Calibration/Autotune Modes ---
        if max_rpm_calibration_active:
            # The run_max_rpm_calibration task is self-contained.
            # We just need to wait for it to finish.
            # It's launched by web_server, so `main_loop` just yields.
            set_motor_power(0) # Ensure no conflicting motor commands
            await asyncio.sleep_ms(100) # Give control to other tasks
            continue # Skip normal motor control while calibrating

        if autotune_active:
            # The autotune_pid task is self-contained.
            # We just need to wait for it to finish.
            # It's launched by web_server, so `main_loop` just yields.
            set_motor_power(0) # Ensure no conflicting motor commands
            await asyncio.sleep_ms(100) # Give control to other tasks
            continue # Skip normal motor control while autotuning
        
        # --- PID Controller Initialization/Reset Check ---
        # Re-initialize PID if gains in config have changed (e.g., from web UI)
        if pid_controller is None or \
           config['kp'] != last_pid_kp or \
           config['ki'] != last_pid_ki or \
           config['kd'] != last_pid_kd:
            
            print(f"[Main] Re-initializing PID controller with Kp={config['kp']:.2f}, Ki={config['ki']:.3f}, Kd={config['kd']:.2f}")
            pid_controller = PID(config['kp'], config['ki'], config['kd'])
            pid_controller.reset() # Reset state when re-initialized
            
            last_pid_kp = config['kp']
            last_pid_ki = config['ki']
            last_pid_kd = config['kd']

        # --- Main Motor Control Logic (Normal Operation) ---
        pedal_value = read_foot_pedal()

        if pedal_value > 1000: # Adjust threshold based on your potentiometer's min value
            if not is_pedal_pressed:
                # Pedal just pressed - initiate soft start
                is_pedal_pressed = True
                soft_start_active = True
                current_soft_start_power = 0 
                
                if config['pid_enabled'] and pid_controller:
                    pid_controller.reset() 
                    pid_controller._soft_start_current_setpoint = 0 

                print("[Main] Pedal pressed. Initiating soft start.")
            
            target_rpm_setpoint = get_target_rpm_from_pedal(pedal_value, config['max_rpm_setting'], config['max_motor_rpm'])

            if config['pid_enabled']:
                # --- PID Control Path ---
                if soft_start_active:
                    rpm_increment_per_step = (config['max_rpm_setting'] / config['soft_start_ramp_steps'])
                    
                    pid_controller._soft_start_current_setpoint += rpm_increment_per_step

                    if pid_controller._soft_start_current_setpoint >= target_rpm_setpoint:
                        pid_controller._soft_start_current_setpoint = target_rpm_setpoint
                        soft_start_active = False
                        print(f"[Main] PID Soft start complete. Target RPM: {target_rpm_setpoint}")
                    
                    output_power = pid_controller.update(pid_controller._soft_start_current_setpoint, last_rpm)
                    set_motor_power(output_power) 
                    await asyncio.sleep_ms(config['soft_start_time_step_ms']) 
                else:
                    output_power = pid_controller.update(target_rpm_setpoint, last_rpm)
                    set_motor_power(output_power) 
                    await asyncio.sleep_ms(20) 
            else:
                # --- Open-Loop Control Path (using calibrated power percentages) ---
                base_power_needed_for_max_rpm = config['calibrated_motor_power_free_running_percent']
                additional_power_for_load = config['calibrated_motor_power_load_offset_percent']
                
                max_effective_power_setting = base_power_needed_for_max_rpm + additional_power_for_load
                
                # Use the directly imported 'adc_max_value'
                scaled_pedal = (pedal_value - 1000) / (adc_max_value - 1000)
                scaled_pedal = max(0, min(1, scaled_pedal)) 
                current_target_power_percent = scaled_pedal * max_effective_power_setting
                
                current_target_power_percent = min(current_target_power_percent, max_effective_power_setting)
                current_target_power_percent = min(current_target_power_percent, 100) 

                if soft_start_active:
                    power_increment_per_step = current_target_power_percent / config['soft_start_ramp_steps']
                    current_soft_start_power += power_increment_per_step
                    
                    if current_soft_start_power >= current_target_power_percent:
                        current_soft_start_power = current_target_power_percent
                        soft_start_active = False
                        print(f"[Main] Open-loop Soft start complete. Power: {int(current_soft_start_power)}%")
                    
                    set_motor_power(current_soft_start_power) 
                    await asyncio.sleep_ms(config['soft_start_time_step_ms'])
                else:
                    set_motor_power(current_target_power_percent)

        else: # Pedal released
            if is_pedal_pressed:
                is_pedal_pressed = False
                soft_start_active = False 
                if pid_controller:
                    pid_controller.reset() 
                
                print("[Main] Pedal released. Initiating needle stop sequence.")
                
                # --- Needle Stop Logic ---
                stop_power = 5 
                set_motor_power(stop_power) 
                
                target_sensor_func = None
                target_position_name = "UNKNOWN"
                if config['stop_position_default'] == "DOWN":
                    target_sensor_func = get_needle_down_status
                    target_position_name = "DOWN"
                else: 
                    target_sensor_func = get_needle_up_status
                    target_position_name = "UP"

                print(f"[Main] Stopping at Needle {target_position_name} position...")

                stop_timeout = utime.ticks_ms() + 5000 
                
                while not target_sensor_func() and utime.ticks_diff(utime.ticks_ms(), stop_timeout) < 0:
                    last_rpm = calculate_rpm() 
                    # print(f"[Main] Stopping... RPM: {last_rpm}, Power: {motor_power_percent}, Up: {get_needle_up_status()}, Down: {get_needle_down_status()}") # Too verbose for constant print
                    await asyncio.sleep_ms(50) 
                
                set_motor_power(0) 
                
                if target_sensor_func():
                    print(f"[Main] Needle successfully stopped at {target_position_name} position.")
                else:
                    print(f"[Main] Needle stop timed out. Did not reach {target_position_name} position precisely.")
            else:
                set_motor_power(0) # Ensure motor is off when pedal not pressed
        
        await asyncio.sleep_ms(20) 

# --- Main execution block ---
async def main():
    print("[INIT] Starting up...")
    
    load_config() # Load configuration from file

    wifi_status, wifi_ip = get_wifi_status()
    print(f"[INIT] WiFi Status: {wifi_status}, IP: {wifi_ip}")

    # Start the TRIAC firing task (must be running for motor control)
    asyncio.create_task(triac_firing_task())
    
    # Start the web server task
    asyncio.create_task(web_server.start_web_server())

    # Start tasks that are triggered by web interface but run in main_loop's context
    # These will only become active when their respective flags are set by web_server
    # Note: These tasks are meant to run continuously and yield, checking their flags.
    # If they were not created as tasks, they would block the event loop.
    asyncio.create_task(run_max_rpm_calibration()) 
    asyncio.create_task(autotune_pid()) 

    # Start the main motor control loop
    await main_loop() # This is the primary blocking task until stopped

if __name__ == '__main__':
    try:
        asyncio.run(main())
    finally:
        set_motor_power(0) 
        print("[Main] Application stopped. Motor power set to 0.")