# -*- coding: utf-8 -*-
class CrucianCarpBitePredictor:
    """
    Простая скоринговая модель клёва карася (0..100).
    Ожидает ключи: water_temp, air_temp, pressure (мм рт.ст.), wind_speed (м/с), wind_dir (строка), clouds (%).
    """
    def predict(self, p: dict) -> int:
        wt = float(p.get("water_temp", 15))
        air = float(p.get("air_temp", 15))
        press = float(p.get("pressure", 755))
        wind = float(p.get("wind_speed", 3))
        clouds = float(p.get("clouds", 50))

        score = 55.0

        # Температура воды — оптимум 16–23°C
        if 16 <= wt <= 23: score += 15
        elif wt < 10: score -= 15
        elif wt > 27: score -= 10
        else: score += 3

        # Давление — слегка повышенное/стабильное лучше
        if 748 <= press <= 762: score += 8
        elif press < 740 or press > 770: score -= 10

        # Ветер — слабый/умеренный лучше
        if wind < 0.8: score -= 3
        elif wind <= 6: score += 6
        else: score -= 8

        # Облачность — умеренная лучше
        if 30 <= clouds <= 80: score += 4

        # Температура воздуха — экстремумы минус
        if air < 5 or air > 30: score -= 6

        return max(0, min(100, int(round(score))))
