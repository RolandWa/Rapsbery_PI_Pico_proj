// static/script.js
async function fetchStatus() {
    try {
        const response = await fetch('/status');
        const data = await response.json();

        document.getElementById('pedal_adc').textContent = data.pedal_adc;
        document.getElementById('current_rpm').textContent = data.current_rpm;
        document.getElementById('motor_power_percent').textContent = data.motor_power_percent;
        document.getElementById('needle_up_active').textContent = data.needle_up_active ? 'ACTIVE' : 'INACTIVE';
        document.getElementById('needle_down_active').textContent = data.needle_down_active ? 'ACTIVE' : 'INACTIVE';
        document.getElementById('pid_enabled').textContent = data.pid_enabled ? 'True' : 'False';
        document.getElementById('max_rpm_setting').textContent = data.max_rpm_setting;
        document.getElementById('max_motor_rpm_calibrated').textContent = data.max_motor_rpm_calibrated;
        document.getElementById('autotune_active').textContent = data.autotune_active ? 'True' : 'False';
        document.getElementById('autotune_stage').textContent = data.autotune_stage;
        document.getElementById('autotune_kp').textContent = data.autotune_kp;
        document.getElementById('autotune_ki').textContent = data.autotune_ki;
        document.getElementById('autotune_kd').textContent = data.autotune_kd;
        document.getElementById('calibration_active').textContent = data.calibration_active ? 'True' : 'False';


        // Also populate input fields with current config values
        document.getElementById('max_rpm_setting_input').value = data.max_rpm_setting;
        document.getElementById('pid_enabled_input').value = data.pid_enabled ? 'true' : 'false';
        document.getElementById('kp_input').value = data.autotune_kp;
        document.getElementById('ki_input').value = data.autotune_ki;
        document.getElementById('kd_input').value = data.autotune_kd;
        
        // Populate other fields if they exist in the status data
        // For brevity, assuming they map directly
        if (data.soft_start_time_step_ms !== undefined) document.getElementById('soft_start_time_step_ms_input').value = data.soft_start_time_step_ms;
        if (data.soft_start_ramp_steps !== undefined) document.getElementById('soft_start_ramp_steps_input').value = data.soft_start_ramp_steps;
        if (data.stop_position_default !== undefined) document.getElementById('stop_position_default_input').value = data.stop_position_default;
        if (data.calibrated_motor_power_free_running_percent !== undefined) document.getElementById('calibrated_motor_power_free_running_percent_input').value = data.calibrated_motor_power_free_running_percent;
        if (data.calibrated_motor_power_load_offset_percent !== undefined) document.getElementById('calibrated_motor_power_load_offset_percent_input').value = data.calibrated_motor_power_load_offset_percent;
        if (data.autotune_target_rpm !== undefined) document.getElementById('autotune_target_rpm_input').value = data.autotune_target_rpm;
        if (data.autotune_power_high !== undefined) document.getElementById('autotune_power_high_input').value = data.autotune_power_high;
        if (data.autotune_power_low !== undefined) document.getElementById('autotune_power_low_input').value = data.autotune_power_low;
        if (data.wifi_ssid !== undefined) document.getElementById('wifi_ssid_input').value = data.wifi_ssid; // Be cautious with password field
        // Note: Password field will not be re-populated for security reasons
        
    } catch (error) {
        console.error('Error fetching status:', error);
        showMessage('Error fetching status: ' + error.message, 'error');
    }
}

async function sendCommand(url, method = 'POST', data = null) {
    const options = { method: method };
    if (data) {
        options.headers = { 'Content-Type': 'application/json' };
        options.body = JSON.stringify(data);
    }
    try {
        const response = await fetch(url, options);
        const result = await response.json();
        if (result.status === 'success') {
            showMessage(result.message, 'success');
        } else {
            showMessage(result.message, 'error');
        }
    } catch (error) {
        console.error('Error sending command:', error);
        showMessage('Network or server error: ' + error.message, 'error');
    } finally {
        updateStatus(); // Always update status after a command
    }
}

function setParam(param, value) {
    sendCommand('/set_param', 'POST', { param: param, value: value });
}

function calibrateMaxRpm() {
    sendCommand('/calibrate_max_rpm');
}

function autotunePid() {
    sendCommand('/autotune_pid');
}

function stopOperations() {
    sendCommand('/stop_operations');
}

function rebootPico() {
    if (confirm('Are you sure you want to reboot the Pico?')) {
        sendCommand('/reboot');
    }
}

function showMessage(message, type) {
    const msgBox = document.getElementById('message-box');
    msgBox.textContent = message;
    msgBox.className = `message ${type}`;
    msgBox.style.display = 'block';
    setTimeout(() => {
        msgBox.style.display = 'none';
    }, 5000); // Hide message after 5 seconds
}

// Global function to update status
function updateStatus() {
    fetchStatus();
}

// Initial fetch and set interval for periodic updates
document.addEventListener('DOMContentLoaded', () => {
    updateStatus(); // Initial call
    setInterval(updateStatus, 500); // Update every 500ms
});