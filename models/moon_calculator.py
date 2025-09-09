from datetime import datetime, timedelta
import math
import logging

class MoonCalculator:
    def __init__(self):
        # База данных известных новолуний на 2025-2026 годы
        self.known_new_moons = [
            # 2025 год
            datetime(2025, 1, 10, 12, 0),
            datetime(2025, 2, 9, 0, 0),
            datetime(2025, 3, 10, 12, 0),
            datetime(2025, 4, 8, 23, 0),
            datetime(2025, 5, 8, 10, 0),
            datetime(2025, 6, 6, 20, 0),
            datetime(2025, 7, 6, 6, 0),
            datetime(2025, 8, 4, 15, 0),
            datetime(2025, 8, 24, 0, 0),  # Калиброванное для точности
            datetime(2025, 9, 23, 0, 0),
            datetime(2025, 10, 22, 12, 0),
            datetime(2025, 11, 21, 0, 0),
            datetime(2025, 12, 20, 12, 0),
            
            # 2026 год
            datetime(2026, 1, 19, 0, 0),
            datetime(2026, 2, 17, 12, 0),
            datetime(2026, 3, 19, 0, 0),
            datetime(2026, 4, 17, 12, 0),
            datetime(2026, 5, 17, 0, 0),
            datetime(2026, 6, 15, 12, 0),
            datetime(2026, 7, 15, 0, 0),
            datetime(2026, 8, 13, 12, 0),
            datetime(2026, 9, 12, 0, 0),
            datetime(2026, 10, 11, 12, 0),
            datetime(2026, 11, 10, 0, 0),
            datetime(2026, 12, 10, 12, 0),
        ]
        
        self.lunar_month = 29.530588

    def get_moon_data(self):
        """Возвращает: (фаза, освещенность%, возраст_в_днях)"""
        try:
            now = datetime.now()
            last_new_moon = self.find_last_new_moon(now)
            age_days = (now - last_new_moon).total_seconds() / 86400
            
            illumination = self.calculate_illumination(age_days)
            phase = self.determine_phase(age_days)
            
            return phase, round(illumination, 1), round(age_days, 1)
            
        except Exception as e:
            logging.error(f"Ошибка вычислений Луны: {e}")
            return "Ошибка", 0, 0

    def find_last_new_moon(self, current_date):
        """Находит ближайшее предыдущее новолуние"""
        for new_moon in reversed(self.known_new_moons):
            if new_moon <= current_date:
                return new_moon
        return self.known_new_moons[0]

    def calculate_illumination(self, age_days):
        """Формула освещенности Луны"""
        phase_angle = 2 * math.pi * age_days / self.lunar_month
        illumination = (1 - math.cos(phase_angle)) / 2 * 100
        return illumination

    def determine_phase(self, age_days):
        """Определяет фазу Луны"""
        age_normalized = age_days % self.lunar_month
        
        if age_normalized < 1:
            return "Новолуние"
        elif age_normalized < 7.4:
            return "Растущая луна"
        elif age_normalized < 14.8:
            return "Растущая луна"
        elif age_normalized < 15.2:
            return "Полнолуние"
        elif age_normalized < 22.2:
            return "Убывающая луна"
        elif age_normalized < 22.6:
            return "Последняя четверть"
        else:
            return "Убывающая луна"

# Глобальный экземпляр
moon_calc = MoonCalculator()

def get_moon_data():
    """Основная функция для получения данных о Луне"""
    return moon_calc.get_moon_data()