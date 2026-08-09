from pathlib import Path
from datetime import datetime, timezone, timedelta
import json
import math
import urllib.request

JST = timezone(timedelta(hours=9))

# 東京（都心付近）
LAT = 35.6895
LON = 139.6917

URL = (
    "https://api.open-meteo.com/v1/forecast"
    f"?latitude={LAT}&longitude={LON}"
    "&current=temperature_2m,relative_humidity_2m,surface_pressure,wind_speed_10m,wind_direction_10m"
    "&hourly=temperature_2m,surface_pressure,precipitation_probability"
    "&daily=sunrise,sunset,precipitation_probability_max"
    "&past_days=1&forecast_days=2"
    "&timezone=Asia%2FTokyo"
    "&wind_speed_unit=ms"
)

def fetch():
    req = urllib.request.Request(URL, headers={"User-Agent": "kindle-weather/2.0"})
    with urllib.request.urlopen(req, timeout=30) as r:
        return json.load(r)

def parse_local(s):
    # Open-Meteo timezone=Asia/Tokyo returns local ISO strings without offset
    return datetime.fromisoformat(s)

def nearest_index(times, target):
    dts = [parse_local(t) for t in times]
    return min(range(len(dts)), key=lambda i: abs((dts[i] - target).total_seconds()))

def wind_dir_jp(deg):
    names = ["北", "北東", "東", "南東", "南", "南西", "西", "北西"]
    return names[int((deg + 22.5) // 45) % 8]

def fmt_signed(x):
    if x > 0:
        return f"+{x:.1f}"
    if x < 0:
        return f"{x:.1f}"
    return "±0.0"

def pressure_arrow(x):
    if x >= 0.5:
        return "↗"
    if x <= -0.5:
        return "↘"
    return "→"

data = fetch()
cur = data["current"]
hourly = data["hourly"]
daily = data["daily"]

now_local = parse_local(cur["time"])
today = now_local.date()
tomorrow = today + timedelta(days=1)

# 現在値
pressure = float(cur["surface_pressure"])
temp = float(cur["temperature_2m"])
humidity = int(round(float(cur["relative_humidity_2m"])))
wind_speed = float(cur["wind_speed_10m"])
wind_direction = wind_dir_jp(float(cur["wind_direction_10m"]))

# 24時間前の気圧
hour_times = hourly["time"]
hour_pressures = hourly["surface_pressure"]
target_24h = now_local - timedelta(hours=24)
idx_24h = nearest_index(hour_times, target_24h)
pressure_24h = float(hour_pressures[idx_24h])
delta = pressure - pressure_24h

# 今日の最高気温と時刻（今日0:00〜23:59の時間予報）
temps = hourly["temperature_2m"]
today_points = []
tomorrow_morning_points = []

for t, v in zip(hour_times, temps):
    if v is None:
        continue
    dt = parse_local(t)
    if dt.date() == today:
        today_points.append((dt, float(v)))
    if dt.date() == tomorrow and 0 <= dt.hour <= 9:
        tomorrow_morning_points.append((dt, float(v)))

if today_points:
    high_dt, today_high = max(today_points, key=lambda x: x[1])
else:
    high_dt, today_high = now_local, temp

if tomorrow_morning_points:
    low_dt, tomorrow_low = min(tomorrow_morning_points, key=lambda x: x[1])
else:
    low_dt, tomorrow_low = now_local + timedelta(days=1), temp

# 今日の降水確率最大・日の出・日の入
daily_dates = [datetime.fromisoformat(x).date() for x in daily["time"]]
try:
    di = daily_dates.index(today)
except ValueError:
    di = 0

pop = daily["precipitation_probability_max"][di]
pop = "--" if pop is None else str(int(round(float(pop))))

sunrise_dt = parse_local(daily["sunrise"][di])
sunset_dt = parse_local(daily["sunset"][di])

template = Path("template.html").read_text(encoding="utf-8")
updated = datetime.now(JST).strftime("%Y年%m月%d日 %H:%M 更新")

replacements = {
    "{{UPDATED}}": updated,
    "{{PRESSURE}}": f"{pressure:.1f}",
    "{{PRESSURE_ARROW}}": pressure_arrow(delta),
    "{{PRESSURE_DELTA}}": fmt_signed(delta),
    "{{PRESSURE_24H_AGO}}": f"{pressure_24h:.1f}",
    "{{TEMP}}": f"{temp:.1f}",
    "{{HUMIDITY}}": str(humidity),
    "{{TODAY_HIGH}}": f"{today_high:.0f}",
    "{{TODAY_HIGH_TIME}}": high_dt.strftime("%H時"),
    "{{TOMORROW_LOW}}": f"{tomorrow_low:.0f}",
    "{{TOMORROW_LOW_TIME}}": low_dt.strftime("%H時"),
    "{{POP}}": pop,
    "{{SUNRISE}}": sunrise_dt.strftime("%H:%M"),
    "{{SUNSET}}": sunset_dt.strftime("%H:%M"),
    "{{WIND_DIR}}": wind_direction,
    "{{WIND_SPEED}}": f"{wind_speed:.1f}",
}

html = template
for k, v in replacements.items():
    html = html.replace(k, v)

Path("index.html").write_text(html, encoding="utf-8")
