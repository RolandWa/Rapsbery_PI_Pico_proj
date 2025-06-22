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


Deployment Steps:

Save all files: Create the folder structure mentioned above on your computer.
Connect Pico W: Plug your Raspberry Pi Pico W into your computer via USB.
Open Thonny: Launch Thonny IDE.
Connect to Pico: In Thonny, go to Run -> Select interpreter... and choose "MicroPython (Raspberry Pi Pico)".
Upload Files:
Using Thonny's "Files" pane, navigate to your project directory on "This computer".
Select all .py files (boot.py, config_manager.py, motor_control.py, sensor_manager.py, wifi_manager.py, web_server.py, main.py).
Right-click and select "Upload to /" (to upload to the root of the Pico).
Create the templates folder on your Pico (right-click on "Raspberry Pi Pico" in files pane, "New folder").
Upload index.html into the templates folder.
Create the static folder on your Pico.
Upload style.css and script.js into the static folder.
Verify WiFi Configuration: Ensure your config.json file (which boot.py reads) has the correct wifi_ssid and wifi_password for your network. You can also set these through the web interface once it's up.
Soft Reboot: Reset your Pico (Ctrl+D in Thonny Shell, or unplug/replug).
Find IP Address: Look in Thonny's Shell for the IP address printed by boot.py (e.g., [BOOT] IP address: 192.168.1.100).
Access Web UI: Open a web browser on a device connected to the same WiFi network as your Pico W, and navigate to the Pico's IP address (e.g., http://192.168.1.100).