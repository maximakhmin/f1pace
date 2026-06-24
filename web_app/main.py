import logging
import fastf1
import os
import asyncio
import uvicorn
from uvicorn.config import LOGGING_CONFIG
import multiprocessing



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

    # fastf1.Cache.set_enabled()
    # for year in range(2021, 2027):
    #     parse(year, analyze=True)

    # p1 = multiprocessing.Process(target=start_emulation)
    p2 = multiprocessing.Process(target=start_server)

    # Запускаем оба
    # p1.start()
    p2.start()

    # Ждем их завершения (Ctrl+C остановит основной скрипт)
    try:
        # p1.join()
        p2.join()
    except KeyboardInterrupt:
        # p1.terminate()
        p2.terminate()


