# -*- coding: utf-8 -*-
class ShukaBitePredictor:
    """
    Скоринг клёва щуки (0..100).
    """
    def predict(self, p: dict) -> int:
        wt = float(p.get("water_temp", 10))
        air = float(p.get("air_temp", 10))
        press = float(p.get("pressure", 755))
        wind = float(p.get("wind_speed", 3))
        clouds = float(p.get("clouds", 50))

        score = 55.0

        # Щука активна при 6–16°C, жару не любит
        if 6 <= wt <= 16: score += 14
        elif wt < 2: score -= 12
        elif wt > 22: score -= 10

        if 744 <= press <= 766: score += 5
        elif press < 738 or press > 774: score -= 8

        if wind <= 1: score -= 2
        elif wind <= 8: score += 5
        else: score -= 6

        if 20 <= clouds <= 80: score += 3
        return max(0, min(100, int(round(score))))
