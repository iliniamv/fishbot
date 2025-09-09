
# -*- coding: utf-8 -*-
from __future__ import annotations
from dataclasses import dataclass
from datetime import datetime
import json
import math
import os
import ephem  # для высоты солнца (днём/ночью без UVI)

STATE_DIR = os.path.join(os.path.dirname(__file__), "..", "state")
os.makedirs(STATE_DIR, exist_ok=True)

@dataclass
class SpotParams:
    depth_m: float = 2.0        # характерная глубина точки лова
    lake_area_km2: float = 1.0  # площадь зеркала (влияет на инерцию); для рек ставьте 0.5
    kind: str = "lake"          # 'lake' | 'river' | 'sea'

class WaterTemperatureModel:
    """
    Самокалибрующаяся инерционная модель температуры воды (исправленная).
    Ключевые изменения против предыдущей версии:
      - Исправлена сезонная норма: убран лишний +amp-сдвиг, который завышал летние значения.
      - Понижен дневной прогрев и усилено испарительное охлаждение.
      - Ослаблено «притяжение» к сезонной норме (стала мягче).
    """
    def __init__(self, spot_key: str):
        self.spot_key = self._normalize_key(spot_key)
        self.state_path = os.path.join(STATE_DIR, f"water_{self.spot_key}.json")
        self.prev_tw = None
        self._load_state()

    def step(self, owm_hour: dict, lat: float, lon: float, params: SpotParams) -> float:
        t_air = float(owm_hour.get("temp"))
        wind = max(0.0, float(owm_hour.get("wind_speed", 0.0)))
        clouds = float(owm_hour.get("clouds", 50.0)) / 100.0
        dew_point = float(owm_hour.get("dew_point", t_air))

        now = datetime.now()
        is_day, sun_factor = self._solar_factor(now, lat, lon, clouds)

        if self.prev_tw is None:
            self.prev_tw = self._seasonal_baseline(now.timetuple().tm_yday, params.kind)

        tw = self.prev_tw

        # 1) Инерционное сближение воды с воздухом
        k0 = 0.022  # базовая скорость (доля от разницы за час)
        depth_scale = min(1.0, 2.5 / max(0.7, params.depth_m))          
        area_scale  = 1.0 / (1.0 + 0.3 * max(0.2, params.lake_area_km2))
        wind_scale  = 1.0 + 0.18 * max(0.0, wind - 2.0)                 
        k = k0 * depth_scale * area_scale * wind_scale
        tw += k * (t_air - tw)

        # 2) Дневной прогрев и 3) Испарительное охлаждение
        Q_solar = 0.06 * sun_factor                 # было 0.12 — уменьшили вдвое
        vpd = max(0.0, t_air - dew_point)
        Q_evap = 0.05 * vpd * (1.0 + 0.25 * wind) * (0.65 if is_day else 0.4)

        tw += Q_solar - Q_evap

        # 4) Мягкая калибровка к сезонной норме (ещё мягче)
        baseline = self._seasonal_baseline(now.timetuple().tm_yday, params.kind)
        tw += 0.01 * (baseline - tw)

        # 5) Физические рамки
        tw = max(0.1, min(35.0, round(tw, 1)))

        self.prev_tw = tw
        self._save_state()
        return tw

    # ---------- Вспомогательные ----------
    def _solar_factor(self, now: datetime, lat: float, lon: float, clouds_0_1: float) -> float:
        obs = ephem.Observer()
        obs.lat = str(lat)
        obs.lon = str(lon)
        obs.date = now
        sun = ephem.Sun(obs)
        alt = float(sun.alt)  # радианы
        if alt <= 0:
            return False, 0.0
        raw = math.sin(alt)  # 0..1
        return True, raw * (1.0 - 0.6 * clouds_0_1)

    def _seasonal_baseline(self, doy: int, kind: str) -> float:
        """Исправленная сезонная норма без завышения.
        Подбираем base и amp так, чтобы для Калининграда:
        - зима ~1–3°C, летний пик ~21–22°C, сентябрь ~19–20°C.
        """
        if kind == "sea":
            base, amp, lag = 12.0, 9.0, 35   # море: ниже амплитуда, пик позже
        elif kind == "river":
            base, amp, lag = 11.0, 8.5, 25
        else:  # lake
            base, amp, lag = 11.75, 9.75, 20
        phi = 2 * math.pi * (doy - (172 + lag)) / 365.0
        return round(base + amp * math.sin(phi), 1)

    # ---------- Состояние ----------
    def _normalize_key(self, name: str) -> str:
        return "".join(ch.lower() if ch.isalnum() else "_" for ch in name)[:64]

    def _load_state(self):
        try:
            if os.path.exists(self.state_path):
                with open(self.state_path, "r", encoding="utf-8") as f:
                    data = json.load(f)
                    self.prev_tw = data.get("prev_tw")
        except Exception:
            self.prev_tw = None

    def _save_state(self):
        try:
            with open(self.state_path, "w", encoding="utf-8") as f:
                json.dump({"prev_tw": self.prev_tw}, f, ensure_ascii=False)
        except Exception:
            pass
