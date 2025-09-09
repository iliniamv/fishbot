# -*- coding: utf-8 -*-
import json
import logging
import os
import time
import re
import traceback
import math
from datetime import datetime, timedelta

import requests
import telebot
from telebot.types import InlineKeyboardMarkup, InlineKeyboardButton, CallbackQuery

# ---------- CONFIG ----------
try:
    from config import BOT_TOKEN, CHAT_ID, OPENWEATHER_API_KEY, SPOTS as CONFIG_SPOTS, DEFAULT_SPOT
except Exception as e:
    raise RuntimeError(f"config.py is missing keys: {e}")

# ---------- MODELS ----------
from models.water_temperature_model import WaterTemperatureModel, SpotParams
from models.crucian_carp_bite_predictor import CrucianCarpBitePredictor
from models.leshch_bite_predictor import LeshchBitePredictor
from models.okun_bite_predictor import OkunBitePredictor
from models.shuka_bite_predictor import ShukaBitePredictor
from models.sudak_bite_predictor import SudakBitePredictor
from models.fishing_recommendations import FishingRecommendations

# ---------- optional astro ----------
try:
    import ephem
except Exception:
    ephem = None

# ============================
# LOGGING
# ============================
logger = logging.getLogger("fishing_bot")
logger.setLevel(logging.INFO)
_handler = logging.FileHandler("bot_debug.log", encoding="utf-8")
_handler.setFormatter(logging.Formatter("%(asctime)s [%(levelname)s] %(message)s"))
logger.addHandler(_handler)

# ============================
# STATE / FILES
# ============================
BASE_DIR = os.path.dirname(__file__)
STATE_DIR = os.path.join(BASE_DIR, "state")
os.makedirs(STATE_DIR, exist_ok=True)
USER_SPOTS_PATH = os.path.join(STATE_DIR, "user_spots.json")
LOCK_PATH = os.path.join(STATE_DIR, "instance.lock")

bot = telebot.TeleBot(BOT_TOKEN.strip(), parse_mode="HTML")

PREDICTORS = {
    "Карась": CrucianCarpBitePredictor(),
    "Судак":  SudakBitePredictor(),
    "Щука":   ShukaBitePredictor(),
    "Окунь":  OkunBitePredictor(),
    "Лещ":    LeshchBitePredictor(),
}
recs_engine = FishingRecommendations()

active_spot_name = DEFAULT_SPOT
weather_cache = {"timestamp": None, "data": None, "spot": None}
water_temp_cache = {"timestamp": None, "value": None}
CACHE_SECONDS = 900  # 15 мин
_model_cache: dict[str, WaterTemperatureModel] = {}

# ============================
# TELEGRAM: single-instance + webhook cleanup
# ============================
def tg_request(method: str, **params):
    url = f"https://api.telegram.org/bot{BOT_TOKEN}/{method}"
    try:
        r = requests.get(url, params=params, timeout=10)
        return r.ok, r.text
    except Exception as e:
        return False, str(e)

def force_clear_webhook_and_updates():
    try:
        bot.remove_webhook()
    except Exception as e:
        logger.warning(f"remove_webhook() failed: {e}")
    ok, txt = tg_request("deleteWebhook", drop_pending_updates=True)
    logger.info(f"deleteWebhook(drop_pending_updates=True): ok={ok}, resp={txt[:200]}")

def acquire_lock():
    try:
        if os.path.exists(LOCK_PATH):
            mtime = os.path.getmtime(LOCK_PATH)
            if (time.time() - mtime) > 6 * 3600:
                os.remove(LOCK_PATH)
        fd = os.open(LOCK_PATH, os.O_CREAT | os.O_EXCL | os.O_WRONLY)
        os.write(fd, str(os.getpid()).encode("utf-8"))
        os.close(fd)
        return True
    except FileExistsError:
        logger.critical("Бот уже запущен: найден lock-файл state/instance.lock")
        return False
    except Exception as e:
        logger.critical(f"Не удалось создать lock-файл: {e}")
        return False

def release_lock():
    try:
        if os.path.exists(LOCK_PATH):
            os.remove(LOCK_PATH)
    except Exception:
        pass

# ============================
# SPOTS
# ============================
def load_user_spots() -> dict:
    try:
        if os.path.exists(USER_SPOTS_PATH):
            with open(USER_SPOTS_PATH, "r", encoding="utf-8") as f:
                return json.load(f)
    except Exception as e:
        logger.error(f"load_user_spots error: {e}")
    return {}

def save_user_spots(spots: dict):
    try:
        with open(USER_SPOTS_PATH, "w", encoding="utf-8") as f:
            json.dump(spots, f, ensure_ascii=False, indent=2)
    except Exception as e:
        logger.error(f"save_user_spots error: {e}")

USER_SPOTS = load_user_spots()

def merged_spots() -> dict:
    m = dict(CONFIG_SPOTS)
    m.update(USER_SPOTS)
    return m

def current_spot() -> dict:
    m = merged_spots()
    return m.get(active_spot_name, list(m.values())[0])

def get_model_for_spot(name: str) -> WaterTemperatureModel:
    if name not in _model_cache:
        _model_cache[name] = WaterTemperatureModel(name)
    return _model_cache[name]

# ============================
# WEATHER / ASTRO UTILS
# ============================
def mmhg(hpa: float) -> float:
    try:
        return round(float(hpa) * 0.750062, 1)
    except Exception:
        return 0.0

def wind_dir_text(deg: float) -> str:
    dirs = [
        (0, 22.5, "северный"), (22.5, 67.5, "северо-восточный"),
        (67.5, 112.5, "восточный"), (112.5, 157.5, "юго-восточный"),
        (157.5, 202.5, "южный"), (202.5, 247.5, "юго-западный"),
        (247.5, 292.5, "западный"), (292.5, 337.5, "северо-западный"),
        (337.5, 360, "северный")
    ]
    for a, b, name in dirs:
        if a <= deg < b:
            return name
    return "переменный"

def get_sunrise_sunset(lat: float, lon: float, date: datetime | None = None):
    d = date or datetime.now()
    try:
        if ephem is None:
            # простой fallback
            return d.replace(hour=6, minute=0), d.replace(hour=19, minute=0)
        obs = ephem.Observer()
        obs.lat = str(lat); obs.lon = str(lon); obs.elevation = 10; obs.date = d
        sun = ephem.Sun()
        return ephem.localtime(obs.next_rising(sun)), ephem.localtime(obs.next_setting(sun))
    except Exception as e:
        logger.error(f"sunrise/sunset error: {e}")
        return d.replace(hour=6, minute=0), d.replace(hour=19, minute=0)

def hhmm(dt: datetime) -> str:
    return dt.strftime("%H:%M")

def is_daylight(now: datetime, sunrise: datetime, sunset: datetime) -> bool:
    return sunrise <= now <= sunset

# ============================
# WEATHER IO (current + 5-day 3-hourly)
# ============================
OWM_WEATHER = "https://api.openweathermap.org/data/2.5/weather"
OWM_FORECAST = "https://api.openweathermap.org/data/2.5/forecast"

def get_weather_data() -> dict:
    global weather_cache
    spot = current_spot()
    lat, lon = spot["lat"], spot["lon"]
    now = datetime.now()

    if weather_cache["timestamp"] and weather_cache["spot"] == active_spot_name \
       and (now - weather_cache["timestamp"]).total_seconds() < CACHE_SECONDS:
        return weather_cache["data"]

    params = {"lat": lat, "lon": lon, "appid": OPENWEATHER_API_KEY, "units": "metric", "lang": "ru"}

    r_cur = requests.get(OWM_WEATHER, params=params, timeout=15); r_cur.raise_for_status()
    cur = r_cur.json()
    r_fc  = requests.get(OWM_FORECAST, params=params, timeout=15); r_fc.raise_for_status()
    fc = r_fc.json()

    data = {
        "spot_name": active_spot_name,
        "coords": (lat, lon),
        "current": {
            "temp": cur["main"]["temp"],
            "pressure_mmhg": mmhg(cur["main"]["pressure"]),
            "humidity": cur["main"]["humidity"],
            "wind_speed": cur["wind"]["speed"],
            "wind_deg": cur["wind"].get("deg", 0),
            "clouds": cur["clouds"]["all"],
            "weather": cur["weather"][0]["description"].capitalize(),
        },
        "forecast": []
    }

    for item in fc["list"]:
        pop = float(item.get("pop", 0.0) or 0.0)
        rain = 0.0
        if "rain" in item and isinstance(item["rain"], dict):
            rain = float(item["rain"].get("3h", 0.0) or 0.0)
        data["forecast"].append({
            "datetime": datetime.fromtimestamp(item["dt"]),
            "temp": float(item["main"]["temp"]),
            "wind_speed": float(item["wind"]["speed"]),
            "wind_deg": float(item["wind"].get("deg", 0) or 0),
            "clouds": float(item["clouds"]["all"]),
            "pressure_mmhg": mmhg(item["main"]["pressure"]),
            "descr": item["weather"][0]["description"],
            "pop": pop,
            "rain": rain,
        })

    weather_cache = {"timestamp": now, "data": data, "spot": active_spot_name}
    return data

# ============================
# WATER MODEL
# ============================
def calculate_water_temp() -> float:
    """Обновляет модель для текущего часа (commit=True) и кэширует результат."""
    try:
        weather = get_weather_data()
        cur = weather["current"]
        lat, lon = weather["coords"]
        spot = current_spot()
        params = SpotParams(
            depth_m=spot.get("depth_m", 2.0),
            lake_area_km2=spot.get("lake_area_km2", 1.0),
            kind=spot.get("kind", "lake"),
        )
        model = get_model_for_spot(active_spot_name)
        hour = {
            "temp": cur["temp"],
            "wind_speed": cur.get("wind_speed", 0.0),
            "clouds": cur.get("clouds", 50),
            "dew_point": cur.get("temp", cur["temp"]),
        }
        tw = model.step(hour, lat=lat, lon=lon, params=params)  # commit=True по умолчанию
        water_temp_cache.update({"timestamp": datetime.now(), "value": tw})
        return tw
    except Exception as e:
        logger.error(f"water temp error: {e}")
        return water_temp_cache.get("value") or 15.0

def simulate_water_temp_forecast(items, start_temp: float, params: SpotParams, lat: float, lon: float):
    """DRY-RUN по 3-часовым слотам без изменения state."""
    tmp = WaterTemperatureModel("forecast_" + active_spot_name)
    temps = []
    last = start_temp
    for it in items:
        hour = {
            "temp": it.get("temp"),
            "wind_speed": it.get("wind_speed", 0.0),
            "clouds": it.get("clouds", 50),
            "dew_point": it.get("dew_point", it.get("temp")),
        }
        tmp.prev_tw = last
        last = tmp.step(hour, lat=lat, lon=lon, params=params)
        temps.append(last)
    return temps

# ============================
# BITE SCORE / DAY META
# ============================
def safe_predictor_score(fish: str, params: dict) -> int:
    predictor = PREDICTORS.get(fish)
    if not predictor:
        return 50
    sp = dict(params); sp.setdefault("humidity", 70)
    try:
        sc = predictor.predict(sp)
        sc = int(sc.get("score", 50)) if isinstance(sc, dict) else int(sc)
        return max(0, min(100, sc))
    except Exception as e:
        logger.error(f"predictor error for {fish}: {e}")
        return 50

def day_score_for_fish(fish: str, date_obj: datetime.date, weather: dict) -> tuple[int, dict]:
    lat, lon = weather["coords"]
    spot = current_spot()
    params_spot = SpotParams(depth_m=spot.get("depth_m",2.0),
                             lake_area_km2=spot.get("lake_area_km2",1.0),
                             kind=spot.get("kind","lake"))

    items = [it for it in weather["forecast"] if it["datetime"].date() == date_obj]
    if not items:
        return 50, {"windows":"—","trend":{"press_delta":0.0,"wind_avg":0.0,"rain_prob":0}}

    start_temp = water_temp_cache.get("value") or calculate_water_temp()
    sim_temps = simulate_water_temp_forecast(items, start_temp, params_spot, lat, lon)

    sr, ss = get_sunrise_sunset(lat, lon, datetime.combine(date_obj, datetime.min.time()))

    def scores_near(center_dt):
        scores = []
        for it, tw in zip(items, sim_temps):
            if abs((it["datetime"] - center_dt).total_seconds()) <= 2*3600:
                p = {
                    "date": it["datetime"].date(),
                    "hour": it["datetime"].hour,
                    "water_temp": tw,
                    "air_temp": it["temp"],
                    "pressure": it["pressure_mmhg"],
                    "wind_speed": it["wind_speed"],
                    "wind_dir": wind_dir_text(it.get("wind_deg", 0)),
                    "clouds": it["clouds"],
                    "humidity": weather["current"].get("humidity",70),
                }
                scores.append(safe_predictor_score(fish, p))
        return scores or [50]

    morning = max(scores_near(sr))
    evening = max(scores_near(ss))
    day_score = int(round((morning + evening) / 2))

    p_first = items[0]["pressure_mmhg"]; p_last = items[-1]["pressure_mmhg"]
    wind_mean = sum(it["wind_speed"] for it in items)/len(items)
    pop_max = max((it.get("pop",0.0) for it in items), default=0.0)
    trend = {"press_delta": round(p_last - p_first,1), "wind_avg": round(wind_mean,1), "rain_prob": int(round(pop_max*100))}
    windows = f"{hhmm(sr)} / {hhmm(ss)}"
    return day_score, {"windows":windows, "trend":trend}

# ============================
# UI
# ============================
def kb_main():
    m = InlineKeyboardMarkup(row_width=2)
    m.add(
        InlineKeyboardButton("Карась", callback_data="fish|Карась"),
        InlineKeyboardButton("Судак",  callback_data="fish|Судак"),
        InlineKeyboardButton("Щука",   callback_data="fish|Щука"),
        InlineKeyboardButton("Окунь",  callback_data="fish|Окунь"),
        InlineKeyboardButton("Лещ",    callback_data="fish|Лещ"),
        InlineKeyboardButton("Погода сейчас", callback_data="weather_now"),
        InlineKeyboardButton("📍 Спот", callback_data="spot_menu"),
        InlineKeyboardButton("➕ Добавить спот", callback_data="spot_add_help"),
    )
    return m



def kb_forecast(fish: str):
    # Универсальная клавиатура для карточки прогноза
    m = InlineKeyboardMarkup(row_width=3)
    m.add(
        InlineKeyboardButton("Сегодня", callback_data="Сегодня"),
        InlineKeyboardButton("Завтра",  callback_data="Завтра"),
        InlineKeyboardButton("+2 дня",  callback_data="+2 дня"),
    )
    m.add(InlineKeyboardButton("📄 Подробно", callback_data="Подробно"))
    m.add(InlineKeyboardButton("🏠 В меню", callback_data="back_main"))
    return m
def paginate_spots(page: int, per_page: int = 6):
    names = list(merged_spots().keys())
    total = len(names)
    max_page = max(0, (total - 1) // per_page)
    page = max(0, min(page, max_page))
    start = page * per_page
    end = min(start + per_page, total)
    return names[start:end], page, max_page

def kb_spots(page: int = 0):
    m = InlineKeyboardMarkup(row_width=1)
    names, page, max_page = paginate_spots(page)
    for name in names:
        prefix = "✅ " if name == active_spot_name else ""
        m.add(InlineKeyboardButton(prefix + name, callback_data="set_spot|" + name))
    nav = []
    if page > 0:
        nav.append(InlineKeyboardButton("« Назад", callback_data=f"spot_page|{page-1}"))
    if page < max_page:
        nav.append(InlineKeyboardButton("Вперёд »", callback_data=f"spot_page|{page+1}"))
    if nav:
        m.row(*nav)
    m.add(InlineKeyboardButton("➕ Добавить спот", callback_data="spot_add_help"))
    m.add(InlineKeyboardButton("🏠 В меню", callback_data="back_main"))
    return m

# ============================
# FORMATTING
# ============================
def weather_text_block() -> str:
    w = get_weather_data()
    c = w["current"]
    lat, lon = w["coords"]
    sunrise, sunset = get_sunrise_sunset(lat, lon)
    tw = calculate_water_temp()
    return (
        f"🌤️ <b>Погода — {w['spot_name']}</b>\n"
        f"• {c['weather']}\n"
        f"• Воздух: <b>{c['temp']:.1f}°C</b>\n"
        f"• Вода (модель): <b>{tw:.1f}°C</b>\n"
        f"• Давление: <b>{c['pressure_mmhg']} мм рт.ст.</b>\n"
        f"• Ветер: <b>{c['wind_speed']:.1f} м/с</b>, {wind_dir_text(c.get('wind_deg',0))}\n"
        f"• Облачность: {int(round(c['clouds']))}%\n"
        f"• Восход: {hhmm(sunrise)}, закат: {hhmm(sunset)}"
    )

def three_days_block(fish: str, w: dict) -> str:
    lines = [f"📅 <b>Прогноз на 3 дня</b> — {fish} — {w['spot_name']}"]
    lat, lon = w["coords"]
    spot = current_spot()
    params_spot = SpotParams(depth_m=spot.get("depth_m",2.0),
                             lake_area_km2=spot.get("lake_area_km2",1.0),
                             kind=spot.get("kind","lake"))
    now = datetime.now().date()
    for d in [now, now + timedelta(days=1), now + timedelta(days=2)]:
        items = [it for it in w["forecast"] if it["datetime"].date() == d]
        if not items:
            continue
        start_temp = water_temp_cache.get("value") or calculate_water_temp()
        temps = simulate_water_temp_forecast(items, start_temp, params_spot, lat, lon)
        # слоты около 12–15
        mid_idx = min(range(len(items)), key=lambda i: abs(items[i]["datetime"].hour - 13))
        water_mid = temps[mid_idx]
        tmin = min(it["temp"] for it in items)
        wspd = items[mid_idx]["wind_speed"]
        wdeg = items[mid_idx]["wind_deg"]
        press = items[mid_idx]["pressure_mmhg"]
        score, _meta = day_score_for_fish(fish, d, w)
        wd = "Пн Вт Ср Чт Пт Сб Вс".split()[datetime.weekday(datetime(d.year, d.month, d.day))]
        lines.append(
            f"• {wd} {d:%d.%m} — <b>{score}/100</b> | вода ~ <b>{water_mid:.1f}°C</b> | "
            f"tдн ~ <b>{tmin:.0f}°C</b> | ветер <b>{wspd:.0f} м/с</b> ({wind_dir_text(wdeg)}) | "
            f"давл. <b>{press}</b> мм"
        )
    return "\n".join(lines)

def build_message_for_fish(fish: str) -> str:
    w = get_weather_data()
    today = datetime.now().date()
    score_today, _ = day_score_for_fish(fish, today, w)
    parts = [f"🐟 <b>{fish}</b> | {w['spot_name']} | Оценка: <b>{score_today}/100</b>",
             "", weather_text_block(), "", three_days_block(fish, w), ""]
    # краткая рекомендация из шаблона (если есть)
    try:
        rec = recs_engine.get_recommendations(fish, {}, {}, "day")
        if rec:
            parts.append("🎯 " + rec.split("\n")[0])
    except Exception:
        pass
    return "\n".join(parts).strip()



from telebot.apihelper import ApiTelegramException
import time, traceback, re as _re

def _norm_cb(s: str) -> str:
    if not isinstance(s, str):
        return ""
    s2 = s.replace("📄","").replace("️","").strip().lower()
    return " ".join(s2.split())

_last_edit_ts = {}
_EDIT_COOLDOWN = 2.0

def safe_edit(call, txt, markup=None):
    try:
        chat_id = call.message.chat.id
        mid = call.message.message_id
        now = time.time()
        key = (chat_id, mid)
        if now - _last_edit_ts.get(key, 0) < _EDIT_COOLDOWN:
            try: bot.answer_callback_query(call.id, text="Слишком часто — подождите…", show_alert=False)
            except Exception: pass
            return False
        current = (call.message.text or "").strip()
        newtxt = (txt or "").strip()
        if current == newtxt:
            try: bot.answer_callback_query(call.id)
            except Exception: pass
            return False
        bot.edit_message_text(newtxt, chat_id=chat_id, message_id=mid,
                              parse_mode="HTML", disable_web_page_preview=True,
                              reply_markup=markup)
        _last_edit_ts[key] = now
        return True
    except ApiTelegramException as e:
        s = str(e)
        if "Too Many Requests" in s:
            try: bot.answer_callback_query(call.id, text="Слишком часто — подождите…", show_alert=False)
            except Exception: pass
            return False
        if "message is not modified" in s:
            try: bot.answer_callback_query(call.id)
            except Exception: pass
            return False
        raise

def _three_day_lines_for(fish, w):
    blk = three_days_block(fish, w)
    return [ln.strip() for ln in blk.splitlines() if "вода" in ln and "ветер" in ln]

def _parse_three_line(line):
    def grab(p):
        m = _re.search(p, line, _re.I)
        return m.group(1).replace(",", ".") if m else None
    vals = {}
    tday = grab(r"tдн\s*~\s*([0-9\.,]+)")
    if tday: vals["t_day"] = f"{float(tday):.1f}°C"
    water = grab(r"вода\s*~\s*([0-9\.,]+)")
    if water: vals["water"] = f"{float(water):.1f}°C"
    press = grab(r"давл\.\s*([0-9\.,]+)")
    if press: vals["press"] = f"{float(press):.1f} мм рт.ст."
    m = _re.search(r"ветер\s*([0-9\.,]+)\s*м/с(?:\s*\(([^)]+)\))?", line, _re.I)
    if m:
        spd = f"{float(m.group(1).replace(',', '.')):.1f}"
        dirx = m.group(2)
        vals["wind"] = f"{spd} м/с{(' ('+dirx+')') if dirx else ''}"
    return vals

def render_compact_for_day(fish: str, w: dict, offset: int) -> str:
    base = build_message_for_fish(fish)
    if offset == 0:
        return base
    lines = base.splitlines()
    day_lines = _three_day_lines_for(fish, w)
    if len(day_lines) <= offset:
        return base
    vals = _parse_three_line(day_lines[offset])
    try:
        from datetime import datetime, timedelta
        date_obj = (datetime.now() + timedelta(days=offset)).date()
        score, _ = day_score_for_fish(fish, date_obj, w)
    except Exception:
        score = None
    for i, s in enumerate(lines):
        if s.startswith("🐟 ") and "Оценка:" in s and score is not None:
            lines[i] = _re.sub(r"Оценка:\s*<b>\d+\/100</b>", f"Оценка: <b>{score}/100</b>", s)
            break
    try:
        idx = next(k for k,l in enumerate(lines) if l.lstrip().startswith("🌤"))
    except StopIteration:
        idx = None
    if idx is not None:
        j = idx + 1
        while j < len(lines) and lines[j].strip().startswith("•"):
            s = lines[j].strip()
            if s.startswith("• Воздух") and "t_day" in vals:
                lines[j] = _re.sub(r"(• Воздух[^:]*:\s*).*$", r"\g<1>"+vals["t_day"], lines[j])
            elif s.startswith("• Вода") and "water" in vals:
                lines[j] = _re.sub(r"(• Вода[^:]*:\s*).*$", r"\g<1>"+vals["water"], lines[j])
            elif s.startswith("• Давление") and "press" in vals:
                lines[j] = _re.sub(r"(• Давление:\s*).*$", r"\g<1>"+vals["press"], lines[j])
            elif s.startswith("• Ветер") and "wind" in vals:
                lines[j] = _re.sub(r"(• Ветер:\s*).*$", r"\g<1>"+vals["wind"], lines[j])
            j += 1
    for i in range(len(lines)-1, -1, -1):
        if lines[i].startswith("🎯 "):
            if score is None: break
            if score >= 80: mood = "очень активен"
            elif score >= 60: mood = "активен"
            elif score >= 40: mood = "умеренно активен"
            else: mood = "вялый"
            tip = "держитесь у травы/свалов, экспериментируйте с насадками"
            lines[i] = _re.sub(r"(🎯 <b>Итог:</b>\s*).*$", r"\g<1>"+f"{fish} {mood}; {tip}.", lines[i])
            break
    return "\n".join(lines)
# ============================
# COMMANDS
# ============================
@bot.message_handler(commands=["start", "help"])
def cmd_start(message):
    bot.send_message(
        message.chat.id,
        "Привет! Выберите рыбу, посмотрите погоду или переключите/добавьте спот.\n\n"
        "Добавление спота:\n"
        "<code>/add_spot Название; lat; lon; [глубина_м]; [площадь_км2]; [тип]</code>\n"
        "Также работает формат с запятой: <code>Название; lat, lon; ...</code>\n"
        "Тип: lake|river|sea (озеро|река|море).",
        reply_markup=kb_main()
    )

@bot.message_handler(commands=["karas","sudak","shuka","okun","leshch"])
def cmd_fish_shortcuts(message):
    mapping = {"karas":"Карась","sudak":"Судак","shuka":"Щука","okun":"Окунь","leshch":"Лещ"}
    fish = mapping.get(message.text.split()[0].lstrip("/"))
    if fish:
        try:
            bot.send_message(message.chat.id, build_message_for_fish(fish), reply_markup=kb_main())
        except Exception as e:
            logger.error(f"reply_bite error for {fish}: {e}\n{traceback.format_exc()}")
            bot.send_message(message.chat.id, "Не удалось построить прогноз. Смотрите bot_debug.log.")

@bot.message_handler(commands=["add_spot"])
def cmd_add_spot(message):
    # /add_spot Название; 54.72,20.49; 2.0; 0.8; lake
    txt = message.text
    try:
        parts = txt.split(None, 1)
        if len(parts) < 2:
            raise ValueError("Укажите параметры после команды.")
        payload = parts[1].strip()
        if ';' in payload:
            name, rest = payload.split(';', 1)
            name = name.strip()
        else:
            mnums = re.search(r'(-?\d+[.,]?\d*).+?(-?\d+[.,]?\d*)', payload)
            if not mnums:
                raise ValueError("Не нашёл координаты (lat, lon).")
            name = payload[:mnums.start()].strip()
            rest = payload[mnums.start():]

        rest = rest.replace(',', ' , ').replace(';', ' ; ').replace('|', ' ').replace('\t', ' ')
        rest = re.sub(r'\s+', ' ', rest).strip()
        nums = re.findall(r'-?\d+[.,]?\d*', rest)
        if len(nums) < 2:
            raise ValueError("Нужно указать широту и долготу (пример: 54.12; 20.34).")

        f = lambda s: float(s.replace(',', '.'))
        lat, lon = f(nums[0]), f(nums[1])
        depth = f(nums[2]) if len(nums) >= 3 else 2.0
        area  = f(nums[3]) if len(nums) >= 4 else 0.6

        kind = 'lake'
        m_kind = re.search(r'\b(lake|river|sea|озеро|река|море)\b', rest, flags=re.IGNORECASE)
        if m_kind:
            raw = m_kind.group(1).lower()
            kind = {'озеро': 'lake', 'река': 'river', 'море': 'sea'}.get(raw, raw)

        if not (-90 <= lat <= 90 and -180 <= lon <= 180):
            raise ValueError("Координаты вне диапазона.")

        global USER_SPOTS, active_spot_name, weather_cache
        USER_SPOTS[name] = {"lat": lat, "lon": lon, "depth_m": depth, "lake_area_km2": area, "kind": kind}
        save_user_spots(USER_SPOTS)
        active_spot_name = name
        weather_cache = {"timestamp": None, "data": None, "spot": None}
        bot.send_message(
            message.chat.id,
            f"✅ Спот добавлен и выбран: <b>{name}</b>\n"
            f"lat={lat:.5f}, lon={lon:.5f}, глубина={depth} м, площадь={area} км², тип={kind}",
            reply_markup=kb_main()
        )
    except Exception as e:
        bot.send_message(message.chat.id,
            "❌ Не удалось распарсить.\nПримеры:\n"
            "<code>/add_spot Озеро X; 54.12; 20.34; 2.0; 0.8; lake</code>\n"
            "<code>/add_spot Река Y; 54.12, 20.34; river</code>")

# ============================
# CALLBACKS
# ============================
@bot.callback_query_handler(func=lambda c: True)



def on_cb(call):
    """Unified callback handler: day switching (compact), detail view, back to menu, fish selection."""
    global last_fish_selected
    # Try to answer callback quickly to avoid 'loading' spinner
    try:
        data = call.data or ""
    except Exception:
        data = ""
    d = _norm_cb(data)

    # TODAY
    if data == "Сегодня" or d.startswith("сегод"):
        try:
            if not last_fish_selected:
                bot.answer_callback_query(call.id, text="Выберите рыбу", show_alert=False)
                safe_edit(call, "Выберите рыбу:", kb_main())
                return
            w = get_weather_data()
            txt = render_compact_for_day(last_fish_selected, w, 0)
            bot.answer_callback_query(call.id)
            safe_edit(call, txt, kb_forecast(last_fish_selected))
        except Exception as exc:
            logger.error("today switch error: %s" % (exc,))
        return

    # TOMORROW
    if data == "Завтра" or d.startswith("завтр"):
        try:
            if not last_fish_selected:
                bot.answer_callback_query(call.id, text="Выберите рыбу", show_alert=False)
                safe_edit(call, "Выберите рыбу:", kb_main())
                return
            w = get_weather_data()
            txt = render_compact_for_day(last_fish_selected, w, 1)
            bot.answer_callback_query(call.id)
            safe_edit(call, txt, kb_forecast(last_fish_selected))
        except Exception as exc:
            logger.error("tomorrow switch error: %s" % (exc,))
        return

    # +2 DAYS
    if data == "+2 дня" or "+2" in d:
        try:
            if not last_fish_selected:
                bot.answer_callback_query(call.id, text="Выберите рыбу", show_alert=False)
                safe_edit(call, "Выберите рыбу:", kb_main())
                return
            w = get_weather_data()
            txt = render_compact_for_day(last_fish_selected, w, 2)
            bot.answer_callback_query(call.id)
            safe_edit(call, txt, kb_forecast(last_fish_selected))
        except Exception as exc:
            logger.error("+2 switch error: %s" % (exc,))
        return

    # DETAIL
    if data in ("Подробно", "Подробнее") or "подроб" in d:
        try:
            if not last_fish_selected:
                bot.answer_callback_query(call.id, text="Выберите рыбу", show_alert=False)
                safe_edit(call, "Выберите рыбу:", kb_main())
                return
            w = get_weather_data()
            txt = None
            # Try various builders / signatures
            try:
                txt = build_day_detail(last_fish_selected, w, 0)
            except TypeError:
                try:
                    txt = build_day_detail(last_fish_selected, w)
                except Exception:
                    pass
            if txt is None:
                try:
                    txt = detail_text(last_fish_selected, w, 0)  # optional
                except Exception:
                    try:
                        txt = detail_text(last_fish_selected, w)
                    except Exception:
                        pass
            if txt is None:
                txt = build_message_for_fish(last_fish_selected)
            bot.answer_callback_query(call.id)
            safe_edit(call, txt, kb_forecast(last_fish_selected))
        except Exception as exc:
            logger.error("detail error: %s" % (exc,))
        return

    # BACK TO MAIN
    if data == "back_main":
        try:
            bot.answer_callback_query(call.id)
            safe_edit(call, "Выберите рыбу:", kb_main())
        except Exception as exc:
            logger.error("back_main error: %s" % (exc,))
        return

    # FISH SELECTED
    if data.startswith("fish|"):
        fish = data.split("|", 1)[1]
        last_fish_selected = fish
        try:
            w = get_weather_data()
            txt = build_message_for_fish(fish)
        except Exception as exc:
            logger.error("reply_bite error for %s: %s" % (fish, exc))
            txt = "Не удалось построить прогноз. Смотрите bot_debug.log."
        try:
            bot.answer_callback_query(call.id)
        except Exception:
            pass
        safe_edit(call, txt, kb_forecast(fish))
        return

    # DEFAULT: ack and ignore
    try:
        bot.answer_callback_query(call.id)
    except Exception:
        pass
    return

def build_tomorrow_digest() -> str:
    w = get_weather_data()
    tomorrow = (datetime.now() + timedelta(days=1)).date()
    scores = []
    for fish in FISH_LIST:
        sc, meta = day_score_for_fish(fish, tomorrow, w)
        scores.append((fish, sc, meta))
    scores.sort(key=lambda x: x[1], reverse=True)
    top3 = scores[:3]
    lines = []
    for fish, sc, meta in top3:
        trend = meta["trend"]
        tip = []
        if abs(trend["press_delta"]) >= 4: tip.append("скачок давления")
        if trend["rain_prob"] >= 50: tip.append("возможен дождь")
        if trend["wind_avg"] >= 7: tip.append("ветрено")
        tip_txt = "; ".join(tip) if tip else "стабильно"
        lines.append(f"• {fish}: <b>{sc}/100</b> (восх/закат {meta['windows']}; {tip_txt})")
    header = f"📣 <b>Рыбалка завтра ({tomorrow:%d.%m}) — топ-3</b>\nАктивный спот: <b>{w['spot_name']}</b>"
    return header + "\n" + "\n".join(lines)

def digest_loop():
    while True:
        now = datetime.now()
        target = now.replace(hour=18, minute=0, second=0, microsecond=0)
        if now >= target:
            target += timedelta(days=1)
        sleep_s = max(1, int((target - now).total_seconds()))
        try:
            time.sleep(min(60, sleep_s))
        except KeyboardInterrupt:
            return
        if datetime.now() >= target:
            try:
                bot.send_message(CHAT_ID, build_tomorrow_digest())
            except Exception as e:
                logger.error(f"digest error: {e}")
            time.sleep(5)

# ============================
# MAIN
# ============================
def main():
    if not acquire_lock():
        return
    force_clear_webhook_and_updates()
    try:
        me = bot.get_me()
        logger.info(f"Bot OK: @{me.username}")
    except Exception as e:
        logger.critical(f"Token error: {e}")
        release_lock()
        return

    try:
        bot.send_message(CHAT_ID, "✅ Бот запущен", reply_markup=kb_main())
    except Exception as e:
        logger.warning(f"Cannot send to CHAT_ID: {e}")

    import threading
    threading.Thread(target=digest_loop, daemon=True).start()

    while True:
        try:
            bot.infinity_polling(timeout=30, long_polling_timeout=30)
        except Exception as e:
            msg = str(e)
            logger.error(f"Polling error: {msg}")
            if "409" in msg or "Conflict" in msg:
                force_clear_webhook_and_updates()
                time.sleep(5); continue
            time.sleep(3); continue
        break

if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        pass
    except Exception as e:
        logger.critical(f"Fatal: {e}\n{traceback.format_exc()}")
    finally:
        release_lock()
