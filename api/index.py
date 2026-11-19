"""
San Jose Uber Demand - Flask app for Vercel
"""
from flask import Flask, Response
import json
import time
import urllib.request
from datetime import datetime

app = Flask(__name__)

SJ_LAT = 37.3382
SJ_LON = -121.8863

ZONES = [
    {"name": "SJC Airport", "reason": "Flight arrivals create consistent demand"},
    {"name": "Downtown San Jose", "reason": "Events, nightlife, restaurants"},
    {"name": "SAP Center area", "reason": "Sharks games & concerts → post-event surge"},
    {"name": "Santana Row / Valley Fair", "reason": "Shopping & dining evenings"},
    {"name": "North San Jose / tech campuses", "reason": "Commute & business travel"},
]

def fetch_json(url, timeout=8):
    try:
        req = urllib.request.Request(url, headers={"User-Agent": "SJ-Uber-Demand/1.0"})
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            return json.loads(resp.read().decode())
    except Exception as e:
        return {"error": str(e)}

def get_weather():
    url = (
        f"https://api.open-meteo.com/v1/forecast"
        f"?latitude={SJ_LAT}&longitude={SJ_LON}"
        f"&current=temperature_2m,precipitation,weather_code"
        f"&hourly=precipitation_probability"
        f"&forecast_days=1&timezone=America/Los_Angeles"
    )
    data = fetch_json(url)
    if "error" in data:
        return {"error": data["error"], "rain_risk": False, "temp_c": None}
    current = data.get("current", {})
    hourly = data.get("hourly", {})
    probs = hourly.get("precipitation_probability", [])
    now_idx = 0
    try:
        times = hourly.get("time", [])
        current_time = current.get("time", "")
        for i, t in enumerate(times):
            if t.startswith(current_time[:13]):
                now_idx = i
                break
    except:
        pass
    next_probs = probs[now_idx:now_idx+3] if probs else []
    max_prob = max(next_probs) if next_probs else 0
    rain_risk = max_prob >= 30 or current.get("precipitation", 0) > 0
    return {
        "temp_c": current.get("temperature_2m"),
        "next_3h_rain_prob": max_prob,
        "rain_risk": rain_risk,
    }

def get_opensky_arrivals():
    end = int(time.time())
    begin = end - 3600
    url = f"https://opensky-network.org/api/flights/arrival?airport=KSJC&begin={begin}&end={end}"
    data = fetch_json(url, timeout=10)
    if isinstance(data, list):
        return {"arrivals_last_hour": len(data), "error": None}
    return {"arrivals_last_hour": 0, "error": "unavailable"}

def score_demand(weather, arrivals):
    score = 40
    reasons = []
    hour = datetime.now().hour
    if 7 <= hour <= 9 or 16 <= hour <= 19:
        score += 15
        reasons.append("Peak commute window")
    if 21 <= hour or hour <= 2:
        score += 10
        reasons.append("Evening / late night")
    if weather.get("rain_risk"):
        score += 25
        reasons.append(f"Rain risk ({weather.get('next_3h_rain_prob', 0)}% next 3h)")
    else:
        reasons.append("Dry conditions")
    arr = arrivals.get("arrivals_last_hour", 0)
    if arr >= 5:
        score += 20
        reasons.append(f"Strong airport activity (~{arr} arrivals last hour)")
    elif arr >= 1:
        score += 10
        reasons.append(f"Some airport activity ({arr} arrivals)")
    else:
        reasons.append("Low recent airport arrivals (or data unavailable)")
    score = max(0, min(100, score))
    if score >= 70:
        level, advice = "HIGH", "Good time to be online. Prioritize airport and event areas."
    elif score >= 50:
        level, advice = "MODERATE", "Decent demand. Mix of airport and downtown should work."
    else:
        level, advice = "LOW", "Slower period. Stay near high-activity zones or wait for weather/events."
    return {"score": score, "level": level, "advice": advice, "reasons": reasons}

@app.route("/")
def index():
    weather = get_weather()
    arrivals = get_opensky_arrivals()
    demand = score_demand(weather, arrivals)
    zones_html = "".join(
        f'<div class="zone"><strong>{z["name"]}</strong><br><small>{z["reason"]}</small></div>'
        for z in ZONES
    )
    html = f"""<!DOCTYPE html>
<html lang=\"en\">
<head>
<meta charset=\"utf-8\">
<meta name=\"viewport\" content=\"width=device-width, initial-scale=1\">
<title>SJ Uber Demand</title>
<style>
body {{ font-family: -apple-system, BlinkMacSystemFont, sans-serif; margin: 0; padding: 16px; background: #0f172a; color: #e2e8f0; }}
.card {{ background: #1e293b; border-radius: 12px; padding: 16px; margin-bottom: 16px; }}
.score {{ font-size: 3rem; font-weight: bold; }}
.HIGH {{ color: #22c55e; }}
.MODERATE {{ color: #eab308; }}
.LOW {{ color: #ef4444; }}
.zone {{ padding: 10px 0; border-bottom: 1px solid #334155; }}
.zone:last-child {{ border: none; }}
small {{ color: #94a3b8; }}
</style>
</head>
<body>
<div class=\"card\">
  <h2>San Jose Uber Demand</h2>
  <div class=\"score {demand['level']}\">{demand['score']}</div>
  <div><strong>{demand['level']}</strong> — {demand['advice']}</div>
  <ul>{''.join(f'<li>{r}</li>' for r in demand['reasons'])}</ul>
</div>
<div class=\"card\">
  <h3>Weather</h3>
  <p>Temp: {weather.get('temp_c', '—')}°C | Rain risk: {'YES' if weather.get('rain_risk') else 'NO'}</p>
  <small>Next 3h precip probability peak: {weather.get('next_3h_rain_prob', 0)}%</small>
</div>
<div class=\"card\">
  <h3>Airport (SJC)</h3>
  <p>Arrivals last hour: {arrivals.get('arrivals_last_hour', 0)}</p>
  <small>{arrivals.get('error') or 'OpenSky data'}</small>
</div>
<div class=\"card\">
  <h3>Suggested zones</h3>
  {zones_html}
</div>
<small>Data: Open-Meteo + OpenSky (best effort). Not real-time Uber supply. Refresh for update.</small>
</body>
</html>"""
    return Response(html, mimetype="text/html")

application = app
