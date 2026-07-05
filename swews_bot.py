import time
import requests
import logging
import json
import os
import asyncio

# Configure logger
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s"
)
logger = logging.getLogger("SWEWS_Bot_Smart")


WEBHOOK_URL = "https://discord.com/api/webhooks/1523014660989911218/AMoWs4Y3Xc618ERltfJMY0dj8Or_ruMlTxSjN8aft45JbOsY_bm6JD1mPTpF9VmO7wV4"
STATE_FILE = "swews_bot_state.json"
LAST_ALERT_TIME = 0

# Try to load optional bot token from environment
BOT_TOKEN = os.environ.get("DISCORD_BOT_TOKEN")

def load_state():
    if os.path.exists(STATE_FILE):
        try:
            with open(STATE_FILE, "r") as f:
                return json.load(f)
        except Exception:
            pass
    return {"last_sent_probability": 0}

def save_state(state):
    try:
        with open(STATE_FILE, "w") as f:
            json.dump(state, f)
    except Exception as e:
        logger.error(f"Error saving state: {e}")

def fetch_latest_data_from_api(api_url="http://127.0.0.1:8000"):
    """
    Fetches live solar wind telemetry and goes data from the API server
    and computes the storm probability.
    """
    try:
        intensity_res = requests.get(f"{api_url}/api/regression-intensity", timeout=5)
        goes_res = requests.get(f"{api_url}/api/live/goes", timeout=5)
        
        if intensity_res.status_code != 200 or goes_res.status_code != 200:
            logger.warning("Could not fetch latest live data from API.")
            return None, None
            
        intensity_data = intensity_res.json()
        goes_data = goes_res.json()
        
        electrons = goes_data.get("electrons", [])
        latest_electron = 0.0
        if electrons:
            last_el = electrons[-1].get("electron_flux_2mev", 0.0)
            if last_el is not None:
                latest_electron = float(last_el)
                
        wind_speed = float(intensity_data.get("wind_speed", 450.0))
        bz = float(intensity_data.get("bz", -1.5))
        dyn_pressure = float(intensity_data.get("dynamic_pressure", 2.0))
        intensity = float(intensity_data.get("intensity", 0.15))
        
        # Compute physical parameters & storm probability matching frontend metrics
        kp = max(0.0, min(9.0, 1.4 + intensity * 7.2))
        
        electron_score = min(20.0, (latest_electron / 10000.0) * 20.0)
        bz_score = min(30.0, max(0.0, -bz * 2.3))
        speed_score = min(25.0, max(0.0, wind_speed - 400.0) / 14.0)
        pressure_score = min(15.0, dyn_pressure * 1.15)
        
        probability = round(
            min(99.0, max(5.0, intensity * 18.0 + electron_score + bz_score + speed_score + pressure_score))
        )
        
        telemetry_data = {
            "speed": wind_speed,
            "bz": bz,
            "kp": round(kp, 1)
        }
        return probability, telemetry_data
    except Exception as e:
        logger.error(f"Error communicating with FastAPI server: {e}")
        return None, None

def check_and_send_alert(probability, telemetry_data):
    """
    Evaluates probability changes and posts stateful warnings/clears to Discord Webhook.
    """
    global LAST_ALERT_TIME
    state = load_state()
    last_prob = state.get("last_sent_probability", 0)
    THRESHOLD = 20
    
    # Evaluate warning states
    if probability >= THRESHOLD:
        # Case 1: Initial alert (probability crosses threshold)
        if last_prob == 0:
            title = "🚨 SWEWS Warning: Elevated Risk Detected"
            color = 15158332  # Orange warning
            content = f"🚨 **SPACE WEATHER ALERT: {probability}% STORM PROBABILITY** 🚨"
            bypass_cooldown = True
        # Case 2: Risk increased since last sent probability
        elif probability > last_prob:
            title = "📈 SWEWS Escalation: Storm Risk Increased"
            color = 13632027  # Red escalation
            content = f"📈 **SPACE WEATHER UPDATE: RISK INCREASED TO {probability}%** (previously {last_prob}%) 📈"
            bypass_cooldown = False
        # Case 3: Risk decreased or didn't increase
        else:
            return  # Exit silently - do not spam if probability didn't increase
            
        state["last_sent_probability"] = probability
    else:
        # Case 4: Clear alert (dropped below threshold)
        if last_prob > 0:
            title = "✅ SWEWS Normalization: Risk Cleared"
            color = 3066993  # Green clear
            content = f"✅ **SPACE WEATHER CLEAR: Risk normalized to {probability}%** (below warning threshold) ✅"
            bypass_cooldown = True
            state["last_sent_probability"] = 0
        else:
            return  # Exit silently - risk remains nominal

    # Cooldown check (only apply to Escalation updates, Warning and Clear alerts bypass cooldown)
    current_time = time.time()
    if not bypass_cooldown and (current_time - LAST_ALERT_TIME < 1800):
        logger.info("Alert triggered, but suppressed by active 30-minute cooldown.")
        return

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

    try:
        response = requests.post(WEBHOOK_URL, json=payload, timeout=5)
        if response.status_code in (200, 204):
            logger.info(f"Alert successfully sent to Discord Webhook! (Prob: {probability}%)")
            LAST_ALERT_TIME = current_time
            save_state(state)
        else:
            logger.error(f"Discord Webhook responded with error status: {response.status_code}")
    except requests.exceptions.RequestException as e:
        logger.error(f"Network transport error failing alert delivery: {e}")

async def run_webhook_poller():
    """
    Standard webhook-only polling fallback loop.
    """
    logger.info("Running in Webhook Polling Mode...")
    while True:
        prob, telemetry = fetch_latest_data_from_api()
        if prob is not None:
            check_and_send_alert(prob, telemetry)
        else:
            logger.warning("Failed to retrieve telemetry data. Skipping this check.")
        await asyncio.sleep(10)

# If BOT_TOKEN is configured, run interactive Discord Bot using discord.py
if BOT_TOKEN:
    import discord
    from discord.ext import commands, tasks

    intents = discord.Intents.default()
    intents.message_content = True
    bot = commands.Bot(command_prefix="!", intents=intents)

    @bot.event
    async def on_ready():
        logger.info(f"Discord Bot successfully authenticated and logged in as: {bot.user}")
        # Start background alerts dispatcher task
        check_weather_alerts.start()

    @bot.event
    async def on_message(message):
        if message.author == bot.user:
            return

        msg_content = message.content.strip().lower()
        # Respond to user requests for updates
        if msg_content in ["update", "send me current update", "current update", "!update"]:
            logger.info(f"Interactive update request received from {message.author}: '{message.content}'")
            prob, telemetry = fetch_latest_data_from_api()
            
            if prob is not None:
                color_hex = 0x00e676 if prob < 20 else (0xff9100 if prob < 65 else 0xff1744)
                embed = discord.Embed(
                    title="🛰️ SWEWS Real-Time Status Report",
                    description=f"Current solar wind storm probability is **{prob}%**.",
                    color=color_hex
                )
                embed.add_field(name="Solar Wind Speed", value=f"{telemetry['speed']:.1f} km/s", inline=True)
                embed.add_field(name="IMF Bz", value=f"{telemetry['bz']:.1f} nT", inline=True)
                embed.add_field(name="Kp Index", value=f"{telemetry['kp']}", inline=True)
                embed.set_footer(text="Space Weather Early Warning System")
                
                await message.reply(embed=embed)
            else:
                await message.reply("⚠️ Unable to fetch live telemetry. Ensure FastAPI server is running.")

        await bot.process_commands(message)

    @tasks.loop(seconds=10)
    async def check_weather_alerts():
        """
        Background task running alongside the bot to dispatch alerts on increases.
        """
        prob, telemetry = fetch_latest_data_from_api()
        if prob is not None:
            check_and_send_alert(prob, telemetry)

    def main():
        bot.run(BOT_TOKEN)

else:
    def main():
        # Fallback to pure webhook polling
        asyncio.run(run_webhook_poller())

if __name__ == "__main__":
    main()
