from sqlalchemy import create_engine, text
import os
from dotenv import load_dotenv
from fastf1 import get_session, RateLimitExceededError
import fastf1
from tqdm import tqdm
import pandas as pd
from parse_session import parse_results, parse_style, parse_laps, parse_weather
import logging
import time

logging.basicConfig(
    filename='parser.log',
    filemode='w',
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s',
    datefmt='%Y-%m-%d %H:%M:%S'
)

load_dotenv()
fastf1.logger.set_log_level('ERROR')
logging.getLogger('fastf1').propagate = False

engine = create_engine(f'postgresql://{os.getenv('DB_USER')}:{os.getenv('DB_PASSWORD')}@localhost:5432/f1pace')


def parse_and_save(session_year, session_round, session_type, session_id, event_id):
   
    with engine.connect() as conn:
        cursor = conn.execute(text(f"SELECT * FROM results WHERE session_id = {session_id}"))
        curr_s_results = cursor.fetchall()
        cursor = conn.execute(text(f"SELECT * FROM style_info WHERE session_id = {session_id}"))
        curr_s_style_info = cursor.fetchall()
        cursor = conn.execute(text(f"SELECT * FROM laps WHERE session_id = {session_id}"))
        curr_s_laps = cursor.fetchall()
        cursor = conn.execute(text(f"SELECT * FROM weather WHERE session_id = {session_id}"))
        curr_s_weather = cursor.fetchall()
        cursor = conn.execute(text(f"SELECT * FROM track_corners WHERE event_id = {event_id}"))
        curr_s_track_corners = cursor.fetchall()

    condition = (len(curr_s_results)!=0 and 
                 len(curr_s_style_info)!=0 and 
                 len(curr_s_laps)!=0 and 
                 len(curr_s_track_corners)!=0 and 
                 len(curr_s_weather)!=0)

    if condition:
        logging.info(f"Уже есть запись везде с session_id={session_id}")
        return

    fastf1_session = get_session(session_year, session_round, session_type)
    fastf1_session.load(laps=True, telemetry=False, weather=True, messages=False,)

    try:
        if len(curr_s_results)==0:
            results = parse_results(fastf1_session, session_id)
            results.to_sql("results", engine, if_exists='append', index=False,)
            logging.info(f"Запись в results с session_id={session_id}")
    except Exception as e:
        logging.error(f"Ошикба записи в results с session_id={session_id} - {type(e)} - {e}")

    try:
        if len(curr_s_style_info)==0:
            style_info = parse_style(fastf1_session, session_id)
            style_info.to_sql('style_info', engine, index=False, if_exists='append')
            logging.info(f"Запись в style_info с session_id={session_id}")
    except Exception as e:
        logging.error(f"Ошикба записи в style_info с session_id={session_id} - {type(e)} - {e}")

    try:
        if len(curr_s_laps)==0:
            laps = parse_laps(fastf1_session, session_id)
            laps.to_sql('laps', engine, index=False, if_exists='append')
            logging.info(f"Запись в laps с session_id={session_id}")
    except Exception as e:
        logging.error(f"Ошикба записи в laps с session_id={session_id} - {type(e)} - {e}")

    try:
        if len(curr_s_weather)==0:
            weather = parse_weather(fastf1_session, session_id)
            weather.to_sql('weather', engine, index=False, if_exists='append')
            logging.info(f"Запись в weather с session_id={session_id}")
    except Exception as e:
        logging.error(f"Ошикба записи в weather с session_id={session_id} - {type(e)} - {e}")
    


    try:
        if len(curr_s_track_corners)==0:
            circuit_info = fastf1_session.get_circuit_info()
            corners = circuit_info.corners[["X", "Y", "Angle", "Number"]]
            corners.columns = ["x", 'y', 'angle', 'number']
            corners["event_id"] = event_id
            corners["rotation"] = circuit_info.rotation
            corners.to_sql('track_corners', engine, if_exists='append', index=False)
            logging.info(f"Запись в track_corners с session_id={session_id} event_id={event_id}")
    except Exception as e:
        logging.error(f"Ошикба записи в track_corners с session_id={session_id} event_id={event_id} - {type(e)} - {e}")

    

def parse(year):
    sessions = pd.read_sql(f"SELECT s.id, st.name, e.year, e.round, s.event_id FROM sessions s JOIN events e ON s.event_id = e.id JOIN session_types st ON s.session_type=st.id WHERE e.year = {year}", engine)

    i = 0
    while i < len(sessions):
        try:
            parse_and_save(
                sessions.loc[i, "year"], 
                sessions.loc[i, "round"], 
                sessions.loc[i, "name"], 
                sessions.loc[i, "id"],
                sessions.loc[i, "event_id"], 
            )
            
        except RateLimitExceededError as e: 
            logging.error(f"Rate limit to fastf1, sleep 300s. Retrying session_id={sessions.loc[i, "id"]}...")
            time.sleep(300)
            i -= 1
        except Exception as e:
            logging.error(f"Ошикба парсинга с session_id={sessions.loc[i, "id"]} - {type(e)} - {e}")
        finally:
            i += 1


    

        
        