# -*- coding: utf-8 -*-
class OkunBitePredictor:
    """
    Скоринг клёва окуня (0..100).
    """
    def predict(self, p: dict) -> int:
        wt = float(p.get("water_temp", 14))
        air = float(p.get("air_temp", 14))
        press = float(p.get("pressure", 755))
        wind = float(p.get("wind_speed", 3))
        clouds = float(p.get("clouds", 50))

        score = 55.0

        if 10 <= wt <= 20: score += 12
        elif wt < 4: score -= 15
        elif wt > 26: score -= 10

        if 746 <= press <= 764: score += 4
        elif press < 738 or press > 772: score -= 8

        if wind <= 0.7: score -= 2
        elif wind <= 7: score += 6
        else: score -= 6

        if 20 <= clouds <= 90: score += 3
        return max(0, min(100, int(round(score))))
