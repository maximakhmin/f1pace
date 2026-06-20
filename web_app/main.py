from parser import parse
import logging
import fastf1
import os
import asyncio
from emulate import run_live_emulation
from process_real_time_data import watch_file
import uvicorn
from uvicorn.config import LOGGING_CONFIG
import multiprocessing



async def run_emulation(session_filename, speed=1):
    '''
    Запускает эмуляцию сессии, записанной в файле session_filename
    '''
    real_time_filename = "web_app/real_time.txt"
    if os.path.exists(real_time_filename):
        os.remove(real_time_filename)
    
    await asyncio.gather(
        watch_file(real_time_filename, speed),
        run_live_emulation(session_filename, real_time_filename, speed)
    )

def start_emulation():
    # Процесс потребует свой собственный цикл событий asyncio
    asyncio.run(run_emulation("web_app/testing_data/2024 silverstone race clean.txt"))

def start_server():
    uvicorn.run(
        "server:app", 
        host="127.0.0.1", 
        port=8000, 
        reload=False, 
        workers=1, 
        log_config=None
    )

if __name__ == "__main__":

    fastf1.logger.set_log_level('ERROR')
    logging.getLogger('fastf1').propagate = False

    logging.basicConfig(
        # filename='web_app/log.log',
        # filemode='a',
        level=logging.INFO,
        format='%(asctime)s - [%(name)s] - %(levelname)s - %(message)s',
        datefmt='%Y-%m-%d %H:%M:%S',
        handlers=[
            logging.FileHandler("web_app/app.log"), # Все логи сохранятся в файл server.log
        ]
    )

    p1 = multiprocessing.Process(target=start_emulation)
    p2 = multiprocessing.Process(target=start_server)

    # Запускаем оба
    p1.start()
    p2.start()

    # Ждем их завершения (Ctrl+C остановит основной скрипт)
    try:
        p1.join()
        p2.join()
    except KeyboardInterrupt:
        p1.terminate()
        p2.terminate()


