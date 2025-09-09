
# -*- coding: utf-8 -*-
BOT_TOKEN = "8378469478:AAEr5PeRTbmkyWWN-EcaE0ULYse0vi-ujDw"
CHAT_ID = "-1002963454838"
OPENWEATHER_API_KEY = "e1dded7e27d2f903be8007e5c3167e9e"

# Водоёмы (споты). Площадь и глубина нужны для реалистичной инерции.
SPOTS = {
    "Калининград — Верхнее озеро": {
        "lat": 54.7219,
        "lon": 20.4974,
        "depth_m": 2.0,
        "lake_area_km2": 1.3,  # ориентировочно
        "kind": "lake"
    },
    "Калининград — центр": {
        "lat": 54.7104,
        "lon": 20.4522,
        "depth_m": 2.0,
        "lake_area_km2": 1.0,
        "kind": "lake"
    }
}
DEFAULT_SPOT = "Калининград — Верхнее озеро"
