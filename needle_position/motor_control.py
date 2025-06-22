# motor_control.py
from machine import Pin, ADC
import utime
import uasyncio as asyncio # Ensure uasyncio is imported as asyncio

# --- Pin Definitions for Raspberry Pi Pico W (for AC Motor with TRIAC) ---
# You MUST connect your hardware to these specific GPIOs
# Make sure to use opto-isolators for both zero-cross detection and TRIAC gate control for safety!
ZERO_CROSS_PIN = 5     # GP5 for Zero Crossing Detector input (e.g., from an AC-optocoupler like PC817, or dedicated ZC module)
TRIAC_GATE_PIN = 6     # GP6 for TRIAC Gate control output (e.g., to an opto-TRIAC driver like MOC3021)
FOOT_PEDAL_ADC_PIN = 26 # GP26 (ADC0) for the foot pedal potentiometer

# --- Motor Control Globals ---
zero_cross_sensor = None
triac_gate_pin = None
foot_pedal_adc = None

motor_power_percent = 0 # Global variable to hold current motor power percentage (0-100)
adc_max_value = 65535 # 16-bit ADC on Pico

# --- Zero-Crossing Timing Globals ---
# This will be updated by the zero-cross interrupt
last_zero_cross_time_us = 0
ac_half_cycle_time_us = 10000 # For 50Hz AC, half-cycle is 10ms = 10000us. For 60Hz, it's 8333us.
                             # Given the location (Poland), 50Hz (10000us) is appropriate.
                             # Adjust if your mains frequency is different!

# Global variable to hold the calculated target delay for the TRIAC
# This is set by `set_motor_power` and read by the `triac_firing_task`
_target_triac_delay_us = ac_half_cycle_time_us # Initialize to max delay (motor off)


# --- PID Controller Class ---
class PID:
    def __init__(self, kp, ki, kd):
        self.kp = kp
        self.ki = ki
        self.kd = kd
        self._prev_error = 0
        self._integral = 0
        self._last_time = utime.ticks_ms()
        self._soft_start_current_setpoint = 0 # Used for PID soft start

    def update(self, setpoint, current_value):
        current_time = utime.ticks_ms()
        dt = utime.ticks_diff(current_time, self._last_time) / 1000.0 # Convert ms to seconds
        
        if dt == 0: # Avoid division by zero
            return self._prev_error # Or return last output, depends on desired behavior

        error = setpoint - current_value

        # Proportional term
        p_term = self.kp * error

        # Integral term
        self._integral += error * dt
        # Optional: Add integral wind-up protection (clamping)
        # self._integral = max(-100, min(100, self._integral)) # Example clamp

        i_term = self.ki * self._integral

        # Derivative term
        d_term = self.kd * (error - self._prev_error) / dt

        output = p_term + i_term + d_term

        self._prev_error = error
        self._last_time = current_time

        # Map output to power percentage (0-100%) and clamp
        output_percent = max(0, min(100, output))
        return output_percent

    def reset(self):
        self._prev_error = 0
        self._integral = 0
        self._last_time = utime.ticks_ms()
        self._soft_start_current_setpoint = 0
        print("[PID] Controller state reset.")

# --- Interrupt Service Routine (ISR) for Zero Crossing ---
def zero_cross_isr(pin):
    global last_zero_cross_time_us
    last_zero_cross_time_us = utime.ticks_us()
    # print("ZC detected") # For debugging, uncomment if needed

# --- Motor Control Functions ---

def init_motor_control():
    global zero_cross_sensor, triac_gate_pin, foot_pedal_adc
    
    # Initialize Zero Crossing pin as input with a pull-up
    # Assuming the opto-isolator pulls the line low at zero crossing
    zero_cross_sensor = Pin(ZERO_CROSS_PIN, Pin.IN, Pin.PULL_UP)
    # Trigger ISR on the RISING edge of the opto-isolated signal 
    # (meaning the opto-isolator output goes HIGH after sensing a zero cross LOW pulse)
    zero_cross_sensor.irq(trigger=Pin.IRQ_RISING, handler=zero_cross_isr)
    print(f"[Motor] Zero Cross sensor initialized on GP{ZERO_CROSS_PIN}. Ensure it's opto-isolated!")

    # Initialize TRIAC Gate pin as output (starts low)
    triac_gate_pin = Pin(TRIAC_GATE_PIN, Pin.OUT)
    triac_gate_pin.value(0) # Ensure TRIAC is off
    print(f"[Motor] TRIAC Gate control initialized on GP{TRIAC_GATE_PIN}. Ensure it's opto-isolated!")

    # Initialize ADC for foot pedal input
    foot_pedal_adc = ADC(FOOT_PEDAL_ADC_PIN)
    
    print(f"[Motor] Motor control initialized. ADC on GP{FOOT_PEDAL_ADC_PIN}.")
    print("WARNING: Using AC motor control. Ensure ALL safety measures for mains voltage are in place!")

def fire_triac(delay_us):
    """
    Fires the TRIAC by sending a short pulse to its gate after a delay.
    Delay is from the last detected zero crossing.
    """
    
    # Send a short pulse to the TRIAC gate (typically 10-50 us)
    if triac_gate_pin: # Ensure pin is initialized
        triac_gate_pin.value(1)
        utime.sleep_us(50) # Pulse width for TRIAC driver (adjust as needed, usually 10-50us)
        triac_gate_pin.value(0)

def set_motor_power(percent):
    """
    Controls AC motor power by calculating the TRIAC firing angle (delay).
    0% means maximum delay (off), 100% means minimum delay (full power).
    The actual firing is handled by `triac_firing_task`.
    """
    global motor_power_percent, _target_triac_delay_us
    
    # Clamp percentage between 0 and 100
    percent = max(0, min(100, percent))
    motor_power_percent = percent
    
    if percent <= 5: # Small dead zone at low percentage to ensure motor truly off
        _target_triac_delay_us = ac_half_cycle_time_us + 100 # Set delay beyond half cycle
        if triac_gate_pin:
            triac_gate_pin.value(0) # Ensure TRIAC is off
        return

    # Calculate delay based on percentage
    # A small `min_fire_delay_us` ensures the TRIAC has time to react after zero cross.
    # The `max_effective_delay_us` is just before the next zero crossing.
    min_fire_delay_us = 500 # Minimum delay after ZC for TRIAC to fire at full power (adjust for your hardware)
    # The actual maximum delay we can use is just before the next zero crossing.
    # We subtract a buffer (e.g., 200us) to ensure we fire *before* the next ZC event from the ISR.
    max_effective_delay_us = ac_half_cycle_time_us - 200 
    
    # Invert the percentage for delay calculation:
    # 0% power -> max_effective_delay_us (high delay, low power)
    # 100% power -> min_fire_delay_us (low delay, high power)
    
    # Linear mapping:
    # delay = max_fire_delay - (percentage/100) * (max_fire_delay - min_fire_delay)
    
    # (100 - percent) / 100.0 maps from 1.0 (at 0%) to 0.0 (at 100%)
    delay_range = max_effective_delay_us - min_fire_delay_us
    
    calculated_delay = min_fire_delay_us + delay_range * ((100 - percent) / 100.0)
    
    _target_triac_delay_us = int(calculated_delay)
    
def read_foot_pedal():
    if foot_pedal_adc:
        return foot_pedal_adc.read_u16() # Read 16-bit ADC value
    return 0

def get_target_rpm_from_pedal(pedal_value, max_rpm_setting, max_motor_rpm):
    # Scale pedal_value (0-adc_max_value) to target RPM (0-max_rpm_setting)
    # Ensure a small dead zone or threshold if needed, for start/stop stability
    if pedal_value < 1000: # Example dead zone, adjust as per your pedal
        return 0
    
    # Map raw ADC pedal value to a target RPM relative to max_rpm_setting
    # First normalize pedal_value to 0-1 range based on its max observed value
    normalized_pedal = (pedal_value - 1000) / (adc_max_value - 1000) # Adjust for dead zone offset
    normalized_pedal = max(0, min(1, normalized_pedal)) # Clamp 0-1
    
    # Scale this normalized value to the user-set max_rpm_setting
    target_rpm = int(normalized_pedal * max_rpm_setting)
    
    # Ensure target_rpm doesn't exceed the theoretical max_motor_rpm if it was set
    target_rpm = min(target_rpm, max_motor_rpm)
    
    return target_rpm

# --- TRIAC Firing Task ---
async def triac_firing_task():
    global last_zero_cross_time_us, _target_triac_delay_us
    
    print("[Motor] TRIAC Firing Task started.")
    current_cycle_zc_time = 0 # To track ZC for current half-cycle
    
    while True:
        # Check if a new zero crossing has occurred since the last check
        # This is a critical timing loop.
        
        # If the last zero cross time has updated AND it's a new cycle for this task
        if utime.ticks_diff(last_zero_cross_time_us, current_cycle_zc_time) > 0:
            current_cycle_zc_time = last_zero_cross_time_us # Update our reference ZC time
            
            # Calculate the time to fire the TRIAC
            fire_at_us = current_cycle_zc_time + _target_triac_delay_us
            
            # Ensure we are not attempting to fire too late into the cycle
            if _target_triac_delay_us > 0 and _target_triac_delay_us < ac_half_cycle_time_us:
                
                # Spin-wait until the calculated fire time
                while utime.ticks_diff(fire_at_us, utime.ticks_us()) > 0:
                    pass # Keep CPU busy for precise timing
                
                # Fire the TRIAC
                fire_triac(0) # Delay is already factored into `fire_at_us`
            else:
                # If target delay is invalid (e.g., motor off), ensure TRIAC is off
                if triac_gate_pin:
                    triac_gate_pin.value(0)
        else:
            # If no new zero cross yet, ensure TRIAC is off and yield control
            if triac_gate_pin:
                triac_gate_pin.value(0)
        
        # Give control back to asyncio. A very short sleep to keep it reactive.
        # CORRECTED LINE BELOW: Changed sleep_us to sleep_ms
        await asyncio.sleep_ms(1) # Use sleep_ms(1) for the smallest yield in uasyncio