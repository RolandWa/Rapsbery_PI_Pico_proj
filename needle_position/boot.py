# boot.py
# This file is executed on every boot (including wake-boot from deepsleep)

import gc
import network
import time
from config_manager import config, load_config

# Load config early to get WiFi credentials
load_config()

print("[BOOT] Starting WiFi connection...")

wlan = network.WLAN(network.STA_IF)
wlan.active(True)

ssid = config.get('wifi_ssid')
password = config.get('wifi_password')

if ssid and ssid != "SSID_Default": # Check if credentials are set
    wlan.connect(ssid, password)

    max_retries = 30
    retry_count = 0
    while not wlan.isconnected() and retry_count < max_retries:
        print(f"[BOOT] Waiting for WiFi connection... ({retry_count+1}/{max_retries})")
        time.sleep(1)
        retry_count += 1

    if wlan.isconnected():
        print("[BOOT] WiFi connected!")
        print(f"[BOOT] IP address: {wlan.ifconfig()[0]}")
    else:
        print("[BOOT] WiFi connection failed after multiple retries.")
        print("[BOOT] Ensure correct SSID/Password in config.json and strong signal.")
else:
    print("[BOOT] WiFi credentials not set in config.json. Skipping auto-connect.")

gc.collect()