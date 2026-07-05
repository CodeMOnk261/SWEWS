import time
import requests
import logging

logger = logging.getLogger("SWEWS_Bot")

# Track state of alerts to avoid spamming and react dynamically to changes
LAST_SENT_PROBABILITY = 0
LAST_ALERT_TIME = 0

def check_and_send_alert(probability, telemetry_data):
    global LAST_SENT_PROBABILITY, LAST_ALERT_TIME
    
    THRESHOLD = 20
    
    # Check if we should notify based on probability changes
    if probability >= THRESHOLD:
        # Case 1: Initial alert (crossed threshold)
        if LAST_SENT_PROBABILITY == 0:
            title = "🚨 SWEWS Warning: Elevated Risk Detected"
            color = 15158332  # Orange Hex
            content = f"🚨 **SPACE WEATHER ALERT: {probability}% STORM PROBABILITY** 🚨"
            bypass_cooldown = True
        # Case 2: Risk increased
        elif probability > LAST_SENT_PROBABILITY:
            title = "📈 SWEWS Escalation: Storm Risk Increased"
            color = 13632027  # Red Hex
            content = f"📈 **SPACE WEATHER UPDATE: RISK INCREASED TO {probability}%** (previously {LAST_SENT_PROBABILITY}%) 📈"
            bypass_cooldown = False
        # Case 3: Risk decreased or remained same
        else:
            return  # Exit silently - do not spam if probability didn't increase
            
        LAST_SENT_PROBABILITY = probability
    else:
        # Case 4: Clear alert (dropped below threshold)
        if LAST_SENT_PROBABILITY > 0:
            title = "✅ SWEWS Normalization: Risk Cleared"
            color = 3066993  # Green Hex
            content = f"✅ **SPACE WEATHER CLEAR: Risk normalized to {probability}%** (below warning threshold) ✅"
            bypass_cooldown = True
            LAST_SENT_PROBABILITY = 0
        else:
            return  # Exit silently - risk remains nominal

    # Cooldown check (only apply to Escalation updates, allow Warning & Clear alerts instantly!)
    current_time = time.time()
    if not bypass_cooldown and (current_time - LAST_ALERT_TIME < 1800):
        logger.info("Alert triggered, but suppressed by active 30-minute cooldown.")
        return

    # Target your server's incoming integration port
    WEBHOOK_URL = "https://discord.com/api/webhooks/1523014660989911218/AMoWs4Y3Xc618ERltfJMY0dj8Or_ruMlTxSjN8aft45JbOsY_bm6JD1mPTpF9VmO7wV4"
    
    payload = {
        "content": content,
        "embeds": [{
            "title": title,
            "color": color,
            "fields": [
                {"name": "Solar Wind Speed", "value": f"{telemetry_data['speed']:.1f} km/s", "inline": True},
                {"name": "IMF Bz", "value": f"{telemetry_data['bz']:.1f} nT", "inline": True},
                {"name": "Kp Index", "value": f"{telemetry_data['kp']}", "inline": True}
            ],
            "footer": {"text": "Space Weather Early Warning System"}
        }]
    }
    
    # Attempt transmission to Discord
    try:
        response = requests.post(WEBHOOK_URL, json=payload, timeout=5)
        if response.status_code in (200, 204):
            logger.info("Alert successfully sent to Discord!")
            LAST_ALERT_TIME = current_time  # Reset the cooldown timer lock
        else:
            logger.error(f"Discord responded with an error status: {response.status_code}")
    except requests.exceptions.RequestException as e:
        logger.error(f"Network transport error failing alert delivery: {e}")
