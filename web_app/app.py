from parser import parse
import logging
import fastf1
import os
import asyncio
from emulate import run_live_emulation
from process_real_time_data import watch_file


fastf1.logger.set_log_level('ERROR')
logging.getLogger('fastf1').propagate = False

logging.basicConfig(
    filename='web_app/log.log',
    filemode='a',
    level=logging.INFO,
    format='%(asctime)s - [%(name)s] - %(levelname)s - %(message)s',
    datefmt='%Y-%m-%d %H:%M:%S'
)


# for year in range(2026, 2027):
#     parse(year)


async def main():
    real_time_filename = "web_app/real_time.txt"
    if os.path.exists(real_time_filename):
        os.remove(real_time_filename)
    
    # Просто передаем обе корутины в gather
    await asyncio.gather(
        watch_file(real_time_filename),
        run_live_emulation("web_app/testing_data/2024 silverstone race clean.txt", real_time_filename, 1000)
    )



if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        print("\nПрограмма остановлена.")