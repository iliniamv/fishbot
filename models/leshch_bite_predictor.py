# -*- coding: utf-8 -*-
class LeshchBitePredictor:
    """
    Скоринг клёва леща (0..100).
    Ожидает: water_temp, air_temp, pressure, wind_speed, wind_dir, clouds.
    """
    def predict(self, p: dict) -> int:
        wt = float(p.get("water_temp", 12))
        air = float(p.get("air_temp", 12))
        press = float(p.get("pressure", 755))
        wind = float(p.get("wind_speed", 3))
        clouds = float(p.get("clouds", 50))

        score = 55.0

        # Лещ любит стабильную погоду и 12–20°C
        if 12 <= wt <= 20: score += 12
        elif wt < 6: score -= 12
        elif wt > 24: score -= 8

        if 748 <= press <= 762: score += 6
        elif press < 740 or press > 770: score -= 8

        if wind <= 1: score -= 2
        elif wind <= 7: score += 5
        else: score -= 8

        if 20 <= clouds <= 80: score += 3

        if air < 0 or air > 28: score -= 4

        return max(0, min(100, int(round(score))))
