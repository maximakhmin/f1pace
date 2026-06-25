import logging
import fastf1
import uvicorn
from uvicorn.config import LOGGING_CONFIG
import multiprocessing
from parser.parser import parse
import time



def start_server():
    uvicorn.run(
        "server:app", 
        host="127.0.0.1", 
        port=8000, 
        reload=False, 
        workers=1, 
        log_config=None
    )


def start_parsing(year=2026):
    parse(year)
    time.sleep(3600*24) 

if __name__ == "__main__":

    fastf1.logger.set_log_level('ERROR')
    logging.getLogger('fastf1').propagate = False

    logging.basicConfig(
        level=logging.INFO,
        format='%(asctime)s - [%(name)s] - %(levelname)s - %(message)s',
        datefmt='%Y-%m-%d %H:%M:%S',
        handlers=[
            logging.FileHandler("app.log"), 
        ]
    )

    # fastf1.Cache.set_enabled()
    # for year in range(2021, 2027):
    #     parse(year, analyze=True)

    p1 = multiprocessing.Process(target=start_server)
    p2 = multiprocessing.Process(target=start_parsing)

    # Запускаем оба
    p1.start()
    p2.start()

    try:
        p1.join()
        p2.join()
    except KeyboardInterrupt:
        p1.terminate()
        p2.terminate()


