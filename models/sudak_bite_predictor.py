# -*- coding: utf-8 -*-
class SudakBitePredictor:
    """
    Скоринг клёва судака (0..100).
    """
    def predict(self, p: dict) -> int:
        wt = float(p.get("water_temp", 8))
        air = float(p.get("air_temp", 8))
        press = float(p.get("pressure", 755))
        wind = float(p.get("wind_speed", 3))
        clouds = float(p.get("clouds", 50))

        score = 55.0

        if 6 <= wt <= 14: score += 14
        elif wt < 2: score -= 12
        elif wt > 20: score -= 10

        if 746 <= press <= 764: score += 5
        elif press < 738 or press > 772: score -= 7

        if wind <= 1: score -= 2
        elif wind <= 7: score += 5
        else: score -= 7

        if 30 <= clouds <= 90: score += 3
        return max(0, min(100, int(round(score))))
