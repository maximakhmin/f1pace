import ast
from datetime import datetime
import time
import json
import logging
import asyncio

logger = logging.getLogger("Emulator")


def parse_line(line):
    """Парсит строку файла обратно в Python-массив."""
    line = line.strip()
    if not line:
        return None
    try:
        data = json.loads(line)
        return data[0], data[1], data[2]
    except Exception as e:
        logger.error(f"Ошибка парсинга строки {line}: {e}")
        return None


async def run_live_emulation(file_path, real_time_path, speed_factor=1.0):
    """Имитирует поступление данных в реальном времени на основе меток времени.

    speed_factor: позволяет ускорить эмуляцию (например, 2.0 — в два раза
    быстрее)
    """
    logger.info(
        f"Запуск эмуляции файла {file_path}... (Скорость: {speed_factor}x)."
    )

    prev_time = None

    with open(file_path, "r", encoding="utf-8") as f:
        with open(real_time_path, 'w') as f_real_time:
            for line in f:
                data = parse_line(line)
                if not data:
                    continue

                # Распаковываем элементы по вашему условию
                packet_type, payload, time_str = data

                # Конвертируем строку времени в объект datetime
                # Отрезаем букву 'Z' в конце для корректного парсинга
                current_time = datetime.fromisoformat(time_str.replace("Z", ""))

                # Если это не первая строка, считаем паузу перед выводом
                if prev_time is not None:
                    # Находим разницу между текущим пакетом и предыдущим
                    time_delta = (current_time - prev_time).total_seconds()

                    # Если разница положительная, усыпляем поток
                    if time_delta > 0:
                        await asyncio.sleep(time_delta / speed_factor)

                # --- ТУТ НАЧИНАЕТСЯ ОБРАБОТКА ДАННЫХ (Ваш код) ---
                # Данные отправляются в реал тайм файл
                f_real_time.write(f"{line}")
                # -------------------------------------------------

                # Запоминаем время текущего пакета для следующего шага
                prev_time = current_time