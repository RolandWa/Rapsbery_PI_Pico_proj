# wifi_manager.py
import network
import time
import machine # Required for Pin, even if not directly used here
from config_manager import config

# Global WLAN object for consistency
wlan = None 

def connect_wifi(ssid, password):
    global wlan
    
    # In Pico W, boot.py typically handles the initial connection.
    # This function is primarily for getting status or re-connecting if needed.
    
    wlan = network.WLAN(network.STA_IF)
    
    if not wlan.active():
        wlan.active(True)

    if not wlan.isconnected():
        print("[WiFi Manager] Attempting to (re)connect to WiFi...")
        try:
            wlan.connect(ssid, password)
            # Give it some time, but assume boot.py did the heavy lifting
            # This is more for a quick check or if credentials changed in-session
            max_wait = 10
            while max_wait > 0:
                if wlan.isconnected():
                    break
                max_wait -= 1
                time.sleep(1)

            if wlan.isconnected():
                print(f"[WiFi Manager] Connected as: {wlan.ifconfig()[0]}")
                return True
            else:
                print("[WiFi Manager] Could not connect to WiFi.")
                return False
        except Exception as e:
            print(f"[WiFi Manager] Error connecting to WiFi: {e}")
            return False
    else:
        return True # Already connected

def get_wifi_status():
    global wlan
    if wlan is None:
        wlan = network.WLAN(network.STA_IF) # Initialize if not already
    
    if wlan.isconnected():
        return "Connected", wlan.ifconfig()[0]
    else:
        return "Disconnected", "N/A"