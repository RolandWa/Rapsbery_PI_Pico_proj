# Rapsbery_PI_Pico_proj

## Raspberry Pi Pico Needle position

Assumed Pin Assignments for Raspberry Pi Pico W:
Here's a summary of the pin assignments used in your Raspberry Pi Pico W project, presented in Markdown:
---

### Raspberry Pi Pico W Pin Assignments

| Pin Name (Code)        | GPIO Number | Purpose                                       | Module Where Defined | Notes                                                    |
| :--------------------- | :---------- | :-------------------------------------------- | :------------------- | :------------------------------------------------------- |
| `RPM_SENSOR_PIN`       | GP2         | RPM Sensor Input (e.g., Hall Effect)          | `sensor_manager.py`  | Connect your RPM sensor output here.                     |
| `NEEDLE_UP_SENSOR_PIN` | GP3         | Needle UP Position Sensor Input               | `sensor_manager.py`  | Used for detecting the needle's top position.            |
| `NEEDLE_DOWN_SENSOR_PIN`| GP4        | Needle DOWN Position Sensor Input             | `sensor_manager.py`  | Used for detecting the needle's bottom position and stopping. |
| `ZERO_CROSS_PIN`       | GP5         | AC Zero Crossing Detector Input               | `motor_control.py`   | **CRITICAL SAFETY:** Must be opto-isolated from mains AC! |
| `TRIAC_GATE_PIN`       | GP6         | TRIAC Gate Control Output                     | `motor_control.py`   | **CRITICAL SAFETY:** Controls the motor; must use an opto-TRIAC driver (e.g., MOC3021) for isolation! |
| `FOOT_PEDAL_ADC_PIN`   | GP26 (ADC0) | Foot Pedal Potentiometer Input                | `motor_control.py`   | Analog input for reading pedal position.                 |

---

**Important Safety Notes:**

* **Mains Voltage:** The `ZERO_CROSS_PIN` and `TRIAC_GATE_PIN` interact with mains AC voltage. **It is absolutely crucial to use proper opto-isolators (like a PC817 for zero-cross detection and a MOC3021 for the TRIAC gate driver) to provide galvanic isolation between the low-voltage Pico and the high-voltage AC circuit.** Failure to do so can result in serious injury or death, and damage to your equipment.
* **Wiring:** Double-check all wiring according to the datasheets of your sensors, opto-isolators, and TRIACs before applying power.
* **Pull-Up Resistors:** Digital input pins (`RPM_SENSOR_PIN`, `NEEDLE_UP_SENSOR_PIN`, `NEEDLE_DOWN_SENSOR_PIN`, `ZERO_CROSS_PIN`) are typically initialized with internal pull-up resistors in the code (`Pin.PULL_UP`). Ensure your sensors are designed to pull the pin low when active.