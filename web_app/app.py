from parser import parse
import logging
import fastf1


fastf1.logger.set_log_level('ERROR')
logging.getLogger('fastf1').propagate = False

logging.basicConfig(
    filename='log.log',
    filemode='a',
    level=logging.INFO,
    format='%(asctime)s - [%(name)s] - %(levelname)s - %(message)s',
    datefmt='%Y-%m-%d %H:%M:%S'
)


for year in range(2026, 2027):
    parse(year)