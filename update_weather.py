from pathlib import Path
from datetime import datetime, timezone, timedelta
import json
import urllib.request

JST = timezone(timedelta(hours=9))

# Open-Meteo: Tokyo
URL = (
    "https://api.open-meteo.com/v1/forecast"
    "?latitude=35.6895&longitude=139.6917"
    "&current=temperature_2m,relative_humidity_2m,surface_pressure"
    "&hourly=surface_pressure"
    "&past_days=1&forecast_days=1"
    "&timezone=Asia%2FTokyo"
)

def fetch():
    req = urllib.request.Request(URL, headers={"User-Agent": "kindle-weather/1.0"})
    with urllib.request.urlopen(req, timeout=30) as r:
        return json.load(r)

def fmt_delta(x):
    if x is None:
        return "24時間変化 －"
    arrow = "↑" if x > 0.4 else "↓" if x < -0.4 else "→"
    sign = "+" if x > 0 else ""
    return f"24時間変化 {arrow} {sign}{x:.1f} hPa"

data = fetch()
cur = data["current"]

pressure = float(cur["surface_pressure"])
temp = float(cur["temperature_2m"])
humidity = int(round(float(cur["relative_humidity_2m"])))

times = data["hourly"]["time"]
pressures = data["hourly"]["surface_pressure"]
current_time = cur["time"]

delta = None
try:
    idx = times.index(current_time)
    if idx >= 24 and pressures[idx-24] is not None:
        delta = pressure - float(pressures[idx-24])
except Exception:
    pass

template = Path("template.html").read_text(encoding="utf-8")
now = datetime.now(JST).strftime("%Y年%m月%d日 %H:%M 更新")
html = (template
        .replace("{{UPDATED}}", now)
        .replace("{{PRESSURE}}", f"{pressure:.1f}")
        .replace("{{PRESSURE_DELTA}}", fmt_delta(delta))
        .replace("{{TEMP}}", f"{temp:.1f}")
        .replace("{{HUMIDITY}}", str(humidity)))

Path("index.html").write_text(html, encoding="utf-8")
