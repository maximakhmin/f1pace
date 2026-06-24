import logging
import os
import time
from emulation.session import Session
import asyncio

logger = logging.getLogger("Process file")

async def watch_file(file_path, speed):
    s = Session(speed)

    logger.info(f"Начинаю отслеживание файла: {file_path}")

    # Проверяем, существует ли файл, чтобы избежать ошибки
    if not os.path.exists(file_path):
        logger.info(f"Файл {file_path} еще не создан. Ожидаю появления...")
        while not os.path.exists(file_path):
            await asyncio.sleep(1)

    logger.info(f"Файл {file_path} появился")
    with open(file_path, "r", encoding="utf-8") as f:
        # Перемещаем указатель в самый конец файла
        f.seek(0, os.SEEK_END)

        # Инициализируем время последней активности текущим моментом
        last_active_time = time.time()
        TIMEOUT = 10 * 60  # 10 минут в секундах

        while True:
            line = f.readline()

            # Если строка есть — обрабатываем её
            if line:
                asyncio.create_task(s.load(line))
                last_active_time = (
                    time.time()
                )  # Сбрасываем таймер при получении данных
            else:
                # Если строки нет, проверяем, не вышел ли таймаут
                elapsed_time = time.time() - last_active_time
                if elapsed_time > TIMEOUT:
                    logger.info(
                        f"Данных нет уже {int(elapsed_time // 60)} минут. Завершаю отслеживание."
                    )
                    break  # Выходим из цикла и закрываем файл

                # Если таймаут не вышел, ждем секунду перед следующей проверкой
                await asyncio.sleep(0.05)