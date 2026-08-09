from pathlib import Path
from datetime import datetime, timezone, timedelta
from collections import Counter
import json
import math
import os
import urllib.request
import urllib.parse


JST = timezone(timedelta(hours=9))

# -------------------------
# 羽田空港
# -------------------------

LAT = 35.5494
LON = 139.7798
ICAO = "RJTT"

OPENWEATHER_API_KEY = os.environ["OPENWEATHER_API_KEY"]


# =========================================================
# HTTP
# =========================================================

def fetch_json(url, user_agent="kindle-weather/5.0"):

    req = urllib.request.Request(
        url,
        headers={
            "User-Agent": user_agent,
            "Accept": "application/json"
        }
    )

    with urllib.request.urlopen(
        req,
        timeout=30
    ) as r:

        return json.load(r)


# =========================================================
# OpenWeather
# =========================================================

def fetch_openweather():

    params = urllib.parse.urlencode({
        "lat": LAT,
        "lon": LON,
        "appid": OPENWEATHER_API_KEY,
        "units": "metric",
        "lang": "ja",
        "exclude": "minutely,alerts"
    })

    url = (
        "https://api.openweathermap.org/"
        "data/3.0/onecall?"
        + params
    )

    return fetch_json(
        url,
        "kindle-weather-openweather/5.0"
    )


# =========================================================
# METAR
# =========================================================

def fetch_metar(hours=25):

    params = urllib.parse.urlencode({
        "ids": ICAO,
        "format": "json",
        "hours": hours
    })

    url = (
        "https://aviationweather.gov/"
        "api/data/metar?"
        + params
    )

    return fetch_json(
        url,
        "kindle-weather-metar/5.0"
    )


# =========================================================
# 共通
# =========================================================

def wind_dir_jp(deg):

    if deg is None:
        return "静穏"

    names = [
        "北",
        "北東",
        "東",
        "南東",
        "南",
        "南西",
        "西",
        "北西"
    ]

    return names[
        int((float(deg) + 22.5) // 45) % 8
    ]


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


def relative_humidity(temp_c, dew_c):
    """
    気温・露点から相対湿度を計算
    Magnus式
    """

    if temp_c is None or dew_c is None:
        return None

    a = 17.625
    b = 243.04

    e = math.exp(
        (a * dew_c) /
        (b + dew_c)
    )

    es = math.exp(
        (a * temp_c) /
        (b + temp_c)
    )

    rh = 100.0 * e / es

    return max(
        0,
        min(100, round(rh))
    )


# =========================================================
# METAR解析
# =========================================================

def metar_timestamp(record):

    # 新旧APIのフィールド名差を吸収
    for key in (
        "obsTime",
        "reportTime",
        "receiptTime"
    ):

        value = record.get(key)

        if value is None:
            continue

        # Unix timestamp
        if isinstance(value, (int, float)):
            return datetime.fromtimestamp(
                value,
                tz=timezone.utc
            )

        # ISO文字列
        try:

            s = str(value).replace(
                "Z",
                "+00:00"
            )

            return datetime.fromisoformat(s)

        except Exception:
            pass

    return None


def metar_pressure(record):

    value = record.get("altim")

    if value is None:
        value = record.get("altimeter")

    if value is None:
        return None

    value = float(value)

    # APIによってinHg表現の場合に対応
    if value < 100:
        value *= 33.8638866667

    return value


def metar_temperature(record):

    for key in (
        "temp",
        "tempC",
        "temperature"
    ):

        if record.get(key) is not None:

            return float(
                record[key]
            )

    return None


def metar_dewpoint(record):

    for key in (
        "dewp",
        "dewpC",
        "dewpoint"
    ):

        if record.get(key) is not None:

            return float(
                record[key]
            )

    return None


def metar_wind(record):

    wdir = record.get("wdir")
    wspd = record.get("wspd")

    if wdir in (
        "VRB",
        "VAR",
        None
    ):
        direction = None

    else:

        try:
            direction = float(wdir)
        except Exception:
            direction = None

    try:
        speed_knots = float(wspd)
    except Exception:
        speed_knots = 0.0

    # knot → m/s
    speed_ms = (
        speed_knots *
        0.514444
    )

    return (
        direction,
        speed_ms
    )


def metar_cloud(record):
    """
    METAR雲層から

    雲量 → 最大雲量を8分量化
    雲底 → 最も低い雲層

    FEW 2/8
    SCT 4/8
    BKN 7/8
    OVC 8/8
    """

    clouds = record.get("clouds", [])

    coverage_map = {
        "SKC": 0,
        "CLR": 0,
        "NSC": 0,
        "NCD": 0,
        "FEW": 2,
        "SCT": 4,
        "BKN": 7,
        "OVC": 8,
        "VV": 8
    }

    max_okta = 0
    lowest_base_ft = None

    if isinstance(clouds, list):

        for cloud in clouds:

            if not isinstance(
                cloud,
                dict
            ):
                continue

            cover = (
                cloud.get("cover")
                or cloud.get("amount")
            )

            base = (
                cloud.get("base")
                or cloud.get("baseFtAGL")
            )

            if cover:

                okta = coverage_map.get(
                    str(cover).upper(),
                    0
                )

                max_okta = max(
                    max_okta,
                    okta
                )

            if base is not None:

                try:

                    base = float(base)

                    if (
                        lowest_base_ft is None
                        or base < lowest_base_ft
                    ):

                        lowest_base_ft = base

                except Exception:
                    pass

    # cloudsが取れない場合raw METARを解析
    if not clouds:

        raw = (
            record.get("rawOb")
            or record.get("raw")
            or ""
        )

        tokens = raw.split()

        for token in tokens:

            for code, okta in (
                ("FEW", 2),
                ("SCT", 4),
                ("BKN", 7),
                ("OVC", 8),
                ("VV", 8)
            ):

                if token.startswith(code):

                    max_okta = max(
                        max_okta,
                        okta
                    )

                    digits = token[
                        len(code):
                        len(code) + 3
                    ]

                    if digits.isdigit():

                        base_ft = (
                            int(digits)
                            * 100
                        )

                        if (
                            lowest_base_ft is None
                            or
                            base_ft <
                            lowest_base_ft
                        ):

                            lowest_base_ft = (
                                base_ft
                            )

    if lowest_base_ft is None:

        base_km = None

    else:

        base_km = (
            lowest_base_ft *
            0.3048 /
            1000
        )

    return (
        max_okta,
        base_km
    )


# =========================================================
# METAR実況取得
# =========================================================

metars = fetch_metar(25)

if not metars:
    raise RuntimeError(
        "RJTT METARを取得できませんでした"
    )


# 時刻順に並べる
metars = sorted(
    metars,
    key=lambda r:
        metar_timestamp(r)
        or datetime.min.replace(
            tzinfo=timezone.utc
        )
)


latest_metar = metars[-1]

latest_time = metar_timestamp(
    latest_metar
)

if latest_time is None:

    latest_time = datetime.now(
        timezone.utc
    )


temp = metar_temperature(
    latest_metar
)

dewpoint = metar_dewpoint(
    latest_metar
)

pressure = metar_pressure(
    latest_metar
)

if (
    temp is None
    or dewpoint is None
    or pressure is None
):
    raise RuntimeError(
        "METARの気温・露点・気圧を解析できませんでした"
    )


humidity = relative_humidity(
    temp,
    dewpoint
)


wind_deg, wind_speed = metar_wind(
    latest_metar
)

wind_direction = wind_dir_jp(
    wind_deg
)


cloud_cover_okta, cloud_base_km = (
    metar_cloud(
        latest_metar
    )
)


# =========================================================
# METAR 24時間・3時間気圧差
# =========================================================

def nearest_metar_pressure(
    records,
    target
):

    candidates = []

    for r in records:

        dt = metar_timestamp(r)
        p = metar_pressure(r)

        if (
            dt is None
            or p is None
        ):
            continue

        diff = abs(
            (
                dt -
                target
            ).total_seconds()
        )

        candidates.append(
            (
                diff,
                p
            )
        )

    if not candidates:
        return None

    candidates.sort(
        key=lambda x: x[0]
    )

    return candidates[0][1]


pressure_24h = nearest_metar_pressure(
    metars,
    latest_time -
    timedelta(hours=24)
)

pressure_3h = nearest_metar_pressure(
    metars,
    latest_time -
    timedelta(hours=3)
)


if pressure_24h is None:

    pressure_24h = pressure

if pressure_3h is None:

    pressure_3h = pressure


delta24 = (
    pressure -
    pressure_24h
)

delta3 = (
    pressure -
    pressure_3h
)


# =========================================================
# OpenWeather予報
# =========================================================

ow = fetch_openweather()

timezone_offset = int(
    ow.get(
        "timezone_offset",
        9 * 3600
    )
)


def ow_local_datetime(timestamp):

    return datetime.fromtimestamp(
        timestamp,
        timezone.utc
    ) + timedelta(
        seconds=timezone_offset
    )


now_local = (
    datetime.now(
        timezone.utc
    )
    + timedelta(
        seconds=timezone_offset
    )
)

today = now_local.date()

tomorrow = (
    today +
    timedelta(days=1)
)


hourly = ow.get(
    "hourly",
    []
)

daily = ow.get(
    "daily",
    []
)


# =========================================================
# 今日最高
# =========================================================

today_points = []

for h in hourly:

    dt = ow_local_datetime(
        h["dt"]
    )

    if dt.date() == today:

        today_points.append(
            (
                dt,
                float(
                    h["temp"]
                )
            )
        )


if today_points:

    high_dt, today_high = max(
        today_points,
        key=lambda x: x[1]
    )

else:

    today_high = float(
        daily[0]["temp"]["max"]
    )

    high_dt = now_local


# =========================================================
# 明朝最低 0〜9時
# =========================================================

tomorrow_morning = []

for h in hourly:

    dt = ow_local_datetime(
        h["dt"]
    )

    if (
        dt.date() == tomorrow
        and
        0 <= dt.hour <= 9
    ):

        tomorrow_morning.append(
            (
                dt,
                float(
                    h["temp"]
                )
            )
        )


if tomorrow_morning:

    low_dt, tomorrow_low = min(
        tomorrow_morning,
        key=lambda x: x[1]
    )

else:

    tomorrow_low = float(
        daily[1]["temp"]["min"]
    )

    low_dt = (
        now_local +
        timedelta(days=1)
    )


# =========================================================
# 降水確率
# =========================================================

if daily:

    today_pop = daily[0].get(
        "pop",
        0
    )

    pop = str(
        int(
            round(
                float(today_pop)
                * 100
            )
        )
    )

else:

    pop = "--"


# =========================================================
# OpenWeather天気分類
# =========================================================

def weather_label(
    weather
):

    if not weather:
        return "予報なし"

    wid = int(
        weather[0].get(
            "id",
            800
        )
    )

    if wid == 800:
        return "晴れ"

    if wid in (
        801,
        802
    ):
        return "晴れ時々くもり"

    if wid in (
        803,
        804
    ):
        return "くもり"

    if 200 <= wid < 300:
        return "雷雨"

    if 300 <= wid < 400:
        return "小雨"

    if 500 <= wid < 600:
        return "雨"

    if 600 <= wid < 700:
        return "雪"

    if 700 <= wid < 800:
        return "霧"

    return "変わりやすい天気"


def dominant_weather(
    start_hour,
    end_hour
):

    labels = []

    for h in hourly:

        dt = ow_local_datetime(
            h["dt"]
        )

        if (
            dt.date() == today
            and
            start_hour
            <= dt.hour
            <= end_hour
        ):

            labels.append(
                weather_label(
                    h.get(
                        "weather",
                        []
                    )
                )
            )

    if not labels:

        return "予報なし"

    return Counter(
        labels
    ).most_common(1)[0][0]


morning_weather = (
    dominant_weather(
        6,
        11
    )
)

afternoon_weather = (
    dominant_weather(
        12,
        17
    )
)


# =========================================================
# 時間別予報
# =========================================================

def hourly_value(
    target_hour
):

    candidates = []

    for h in hourly:

        dt = ow_local_datetime(
            h["dt"]
        )

        if (
            dt.date() == today
            and
            dt.hour == target_hour
        ):

            return (
                float(
                    h["temp"]
                ),
                int(
                    round(
                        float(
                            h.get(
                                "pop",
                                0
                            )
                        )
                        * 100
                    )
                )
            )

    return (
        None,
        None
    )


hours = [
    6,
    9,
    12,
    15,
    18,
    21
]


hour_repl = {}


for h in hours:

    h_temp, h_pop = (
        hourly_value(h)
    )

    if h_temp is None:

        temp_text = "--"

    else:

        temp_text = str(
            int(
                round(
                    h_temp
                )
            )
        )


    if h_pop is None:

        pop_text = "--"

    else:

        pop_text = str(
            h_pop
        )


    hour_repl[
        f"{{{{H{h:02d}_TEMP}}}}"
    ] = temp_text


    hour_repl[
        f"{{{{H{h:02d}_POP}}}}"
    ] = pop_text


# =========================================================
# HTML
# =========================================================

template = Path(
    "template.html"
).read_text(
    encoding="utf-8"
)


updated = datetime.now(
    JST
).strftime(
    "%Y年%m月%d日 %H:%M 更新"
)


if cloud_base_km is None:

    cloud_base_text = "--"

else:

    cloud_base_text = (
        f"{cloud_base_km:.1f}"
    )


replacements = {

    "{{UPDATED}}":
        updated,

    "{{PRESSURE}}":
        f"{pressure:.1f}",

    "{{PRESSURE_ARROW}}":
        pressure_arrow(
            delta24
        ),

    "{{PRESSURE_DELTA}}":
        fmt_signed(
            delta24
        ),

    "{{PRESSURE_24H_AGO}}":
        f"{pressure_24h:.1f}",

    "{{TEMP}}":
        f"{temp:.1f}",

    "{{HUMIDITY}}":
        str(humidity),

    "{{TODAY_HIGH}}":
        f"{today_high:.0f}",

    "{{TODAY_HIGH_TIME}}":
        high_dt.strftime(
            "%H時"
        ),

    "{{TOMORROW_LOW}}":
        f"{tomorrow_low:.0f}",

    "{{TOMORROW_LOW_TIME}}":
        low_dt.strftime(
            "%H時"
        ),

    "{{POP}}":
        pop,

    "{{WIND_DIR}}":
        wind_direction,

    "{{WIND_SPEED}}":
        f"{wind_speed:.1f}",

    "{{MORNING_WEATHER}}":
        morning_weather,

    "{{AFTERNOON_WEATHER}}":
        afternoon_weather,

    "{{PRESSURE_TREND}}":
        pressure_trend_text(
            delta3
        ),

    "{{CLOUD_COVER}}":
        str(
            cloud_cover_okta
        ),

    "{{CLOUD_BASE}}":
        cloud_base_text,

    "{{DEWPOINT}}":
        f"{dewpoint:.1f}",
}


replacements.update(
    hour_repl
)


html = template


for key, value in (
    replacements.items()
):

    html = html.replace(
        key,
        value
    )


Path(
    "index.html"
).write_text(
    html,
    encoding="utf-8"
)
