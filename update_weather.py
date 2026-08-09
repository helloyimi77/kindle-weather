from pathlib import Path
from datetime import datetime, timezone, timedelta
from collections import Counter
import json
import urllib.request

JST = timezone(timedelta(hours=9))
LAT = 35.5494
LON = 139.7798

URL = (
    "https://api.open-meteo.com/v1/forecast"
    f"?latitude={LAT}&longitude={LON}"
    "&current=temperature_2m,relative_humidity_2m,surface_pressure,wind_speed_10m,wind_direction_10m"
    "&hourly=temperature_2m,surface_pressure,precipitation_probability,weather_code"
    "&daily=sunrise,sunset,precipitation_probability_max"
    "&past_days=1&forecast_days=2"
    "&timezone=Asia%2FTokyo"
    "&wind_speed_unit=ms"
)

def fetch():
    req = urllib.request.Request(URL, headers={"User-Agent": "kindle-weather/3.0"})
    with urllib.request.urlopen(req, timeout=30) as r:
        return json.load(r)

def parse_local(s):
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

def pressure_trend_text(delta3h):
    if delta3h <= -2.0:
        return "大きく下降"
    if delta3h <= -0.7:
        return "下降傾向"
    if delta3h >= 2.0:
        return "大きく上昇"
    if delta3h >= 0.7:
        return "上昇傾向"
    return "ほぼ横ばい"

def weather_label(code):
    # WMO weather interpretation codesをKindle向けに大分類
    if code == 0:
        return "晴れ"
    if code in (1, 2):
        return "晴れ時々くもり"
    if code == 3:
        return "くもり"
    if code in (45, 48):
        return "霧"
    if code in (51, 53, 55, 56, 57):
        return "小雨"
    if code in (61, 63, 65, 66, 67, 80, 81, 82):
        return "雨"
    if code in (71, 73, 75, 77, 85, 86):
        return "雪"
    if code in (95, 96, 99):
        return "雷雨"
    return "変わりやすい天気"

def dominant_weather(hour_times, weather_codes, target_date, start_hour, end_hour):
    labels = []
    for t, code in zip(hour_times, weather_codes):
        dt = parse_local(t)
        if dt.date() == target_date and start_hour <= dt.hour <= end_hour and code is not None:
            labels.append(weather_label(int(code)))
    if not labels:
        return "予報なし"
    return Counter(labels).most_common(1)[0][0]

def hour_value(hour_times, values, target_date, hour):
    for t, v in zip(hour_times, values):
        dt = parse_local(t)
        if dt.date() == target_date and dt.hour == hour:
            return v
    return None

data = fetch()
cur = data["current"]
hourly = data["hourly"]
daily = data["daily"]

now_local = parse_local(cur["time"])
today = now_local.date()
tomorrow = today + timedelta(days=1)

pressure = float(cur["surface_pressure"])
temp = float(cur["temperature_2m"])
humidity = int(round(float(cur["relative_humidity_2m"])))
wind_speed = float(cur["wind_speed_10m"])
wind_direction = wind_dir_jp(float(cur["wind_direction_10m"]))

hour_times = hourly["time"]
hour_pressures = hourly["surface_pressure"]
hour_temps = hourly["temperature_2m"]
hour_pops = hourly["precipitation_probability"]
hour_codes = hourly["weather_code"]

# 24時間差
idx_24h = nearest_index(hour_times, now_local - timedelta(hours=24))
pressure_24h = float(hour_pressures[idx_24h])
delta24 = pressure - pressure_24h

# 3時間差（「今日の傾向」の気圧コメント用）
idx_3h = nearest_index(hour_times, now_local - timedelta(hours=3))
pressure_3h = float(hour_pressures[idx_3h])
delta3 = pressure - pressure_3h

# 今日最高・明朝最低
today_points = []
tomorrow_morning_points = []

for t, v in zip(hour_times, hour_temps):
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

daily_dates = [datetime.fromisoformat(x).date() for x in daily["time"]]
try:
    di = daily_dates.index(today)
except ValueError:
    di = 0

pop = daily["precipitation_probability_max"][di]
pop = "--" if pop is None else str(int(round(float(pop))))

sunrise_dt = parse_local(daily["sunrise"][di])
sunset_dt = parse_local(daily["sunset"][di])

morning_weather = dominant_weather(hour_times, hour_codes, today, 6, 11)
afternoon_weather = dominant_weather(hour_times, hour_codes, today, 12, 17)

def fmt_temp(v):
    return "--" if v is None else str(int(round(float(v))))

def fmt_pop(v):
    return "--" if v is None else str(int(round(float(v))))

hours = [6, 9, 12, 15, 18, 21]
hour_repl = {}
for h in hours:
    hour_repl[f"{{{{H{h:02d}_TEMP}}}}"] = fmt_temp(hour_value(hour_times, hour_temps, today, h))
    hour_repl[f"{{{{H{h:02d}_POP}}}}"] = fmt_pop(hour_value(hour_times, hour_pops, today, h))

template = Path("template.html").read_text(encoding="utf-8")
updated = datetime.now(JST).strftime("%Y年%m月%d日 %H:%M 更新")

replacements = {
    "{{UPDATED}}": updated,
    "{{PRESSURE}}": f"{pressure:.1f}",
    "{{PRESSURE_ARROW}}": pressure_arrow(delta24),
    "{{PRESSURE_DELTA}}": fmt_signed(delta24),
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
    "{{MORNING_WEATHER}}": morning_weather,
    "{{AFTERNOON_WEATHER}}": afternoon_weather,
    "{{PRESSURE_TREND}}": pressure_trend_text(delta3),
}
replacements.update(hour_repl)

html = template
for k, v in replacements.items():
    html = html.replace(k, v)

Path("index.html").write_text(html, encoding="utf-8")
