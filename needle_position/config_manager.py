# config_manager.py
import json
import os # os module is available on Pico

CONFIG_FILE = "config.json"

# Default configuration values
DEFAULT_CONFIG = {
    "wifi_ssid": "SSID_Default",
    "wifi_password": "WI_Fi_Password",
    "max_rpm_setting": 500,  # User-set Max RPM limit for normal operation
    "soft_start_time_step_ms": 20, # How often to update power during soft start (ms)
    "soft_start_ramp_steps": 50, # Number of power increments for soft start
    "stop_position_default": "DOWN", # Default stop position: "UP" or "DOWN"
    "calibrated_motor_power_free_running_percent": 80, # Default Power% needed for max_rpm_setting free-running
    "calibrated_motor_power_load_offset_percent": 10, # Default additional Power% for load (e.g., 80 + 10 = 90%)
    "max_motor_rpm": 2000, # Calibrated absolute maximum RPM of the motor at 100% power
    "pid_enabled": False, # Whether PID control is active by default
    "kp": 0.5, # PID Proportional gain
    "ki": 0.01, # PID Integral gain
    "kd": 0.05,  # PID Derivative gain
    "autotune_target_rpm": 300, # Default RPM to use during PID tuning
    "autotune_power_high": 70, # Default high power for autotune (percent)
    "autotune_power_low": 30  # Default low power for autotune (percent)
}

# Global variable to hold the current configuration
config = {}

# --- Configuration Management Functions ---

def load_config():
    """
    Loads configuration from config.json. If the file doesn't exist or is invalid,
    it creates it with default values.
    """
    global config
    print("[Config] Attempting to load configuration...")
    try:
        with open(CONFIG_FILE, 'r') as f:
            config_loaded = json.load(f)
        
        # Merge with defaults: Important for new settings
        for key, default_value in DEFAULT_CONFIG.items():
            if key not in config_loaded:
                config_loaded[key] = default_value
                print(f"[Config] Added new default setting: {key} = {default_value}")
        
        config = config_loaded # Update global config after merging
        print("[Config] Configuration loaded successfully.")

    except (OSError, ValueError) as e:
        print(f"[Config] Error loading config file ({e.__class__.__name__}: {e}). Creating with default settings.")
        config = DEFAULT_CONFIG.copy() # Use .copy() to ensure we don't modify the default directly
        save_config() # Save the newly created default config
    
    # Debug print the loaded/created config
    print("\n--- Current Configuration ---")
    for key, value in config.items():
        print(f"[Config] {key}: {value}")
    print("-----------------------------\n")

def save_config():
    """
    Saves the current configuration to config.json.
    """
    print("[Config] Saving configuration...")
    try:
        with open(CONFIG_FILE, 'w') as f:
            json.dump(config, f)
        print("Configuration saved successfully.")
    except OSError as e:
        print(f"[Config] Error saving config file: {e}")

# Initialize config on module import
load_config()