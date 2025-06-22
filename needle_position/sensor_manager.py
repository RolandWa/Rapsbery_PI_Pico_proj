# sensor_manager.py
from machine import Pin
import utime

# --- Pin Definitions for Raspberry Pi Pico W ---
# You MUST connect your hardware to these specific GPIOs
RPM_SENSOR_PIN = 2          # GP2 for the RPM sensor (e.g., Hall effect)
NEEDLE_UP_SENSOR_PIN = 3    # GP3 for Needle UP position sensor
NEEDLE_DOWN_SENSOR_PIN = 4  # GP4 for Needle DOWN position sensor

# --- RPM Sensor Globals ---
RPM_POLES = 1  # Number of pulses per revolution from your RPM sensor
               # If using a single magnet on handwheel, this is 1.
               # If it's a slotted opto-sensor with 1 slot, it's 1.
               # If it's a motor encoder, it will be higher.

rpm_sensor = None
last_pulse_time = 0
pulse_count = 0
current_rpm = 0 # Global to hold the most recent RPM

# --- Needle Sensor Globals ---
needle_up_sensor = None
needle_down_sensor = None

# --- Internal variable for RPM calculation window ---
_last_rpm_calc_time = 0

# --- Interrupt Service Routines (ISRs) ---
def rpm_pulse_isr(pin):
    global last_pulse_time, pulse_count
    current_time = utime.ticks_us()
    if utime.ticks_diff(current_time, last_pulse_time) > 100: # Debounce for 100us
        pulse_count += 1
        last_pulse_time = current_time

def init_sensors():
    global rpm_sensor, needle_up_sensor, needle_down_sensor
    global _last_rpm_calc_time
    
    # Initialize RPM sensor pin as input with a pull-up resistor
    rpm_sensor = Pin(RPM_SENSOR_PIN, Pin.IN, Pin.PULL_UP)
    rpm_sensor.irq(trigger=Pin.IRQ_RISING, handler=rpm_pulse_isr) # Trigger on rising edge
    print(f"[Sensor] RPM sensor initialized on GP{RPM_SENSOR_PIN}.")

    # Initialize Needle UP sensor pin as input with a pull-up resistor
    needle_up_sensor = Pin(NEEDLE_UP_SENSOR_PIN, Pin.IN, Pin.PULL_UP)
    print(f"[Sensor] Needle UP sensor initialized on GP{NEEDLE_UP_SENSOR_PIN}.")

    # Initialize Needle DOWN sensor pin as input with a pull-up resistor
    needle_down_sensor = Pin(NEEDLE_DOWN_SENSOR_PIN, Pin.IN, Pin.PULL_UP)
    # CORRECTED LINE BELOW:
    print(f"[Sensor] Needle DOWN sensor initialized on GP{NEEDLE_DOWN_SENSOR_PIN}.") 
    
    _last_rpm_calc_time = utime.ticks_ms() # Set initial time

def calculate_rpm():
    global pulse_count, current_rpm, _last_rpm_calc_time
    
    current_calc_time = utime.ticks_ms()
    time_since_last_call_ms = utime.ticks_diff(current_calc_time, _last_rpm_calc_time)
    _last_rpm_calc_time = current_calc_time # Update for next call

    if time_since_last_call_ms > 0:
        # Pulses per second = (pulse_count / time_since_last_call_ms) * 1000
        # Revolutions per second = (Pulses per second) / RPM_POLES
        # RPM = RPS * 60
        
        rpm_val = (pulse_count / time_since_last_call_ms) * 1000 * (60 / RPM_POLES)
        current_rpm = int(rpm_val)
        pulse_count = 0 # Reset for next window
    else:
        current_rpm = 0 # Or maintain last if no time has passed

    return current_rpm

def get_needle_up_status():
    if needle_up_sensor:
        return not needle_up_sensor.value() # Assuming sensor pulls low when active
    return False

def get_needle_down_status():
    if needle_down_sensor:
        return not needle_down_sensor.value() # Assuming sensor pulls low when active
    return False

def check_sensor_health():
    # Placeholder for more complex health checks
    pass