from sqlalchemy import create_engine, text
import os
from dotenv import load_dotenv
from fastf1 import get_session
from fastf1.exceptions import RateLimitExceededError
import pandas as pd
from parser.parse_session import parse_results, parse_style, parse_laps, parse_weather
import logging
import time
from parser.analyze import analyze_laps
import requests


load_dotenv()
engine = create_engine(f'postgresql://{os.getenv('DB_USER')}:{os.getenv('DB_PASSWORD')}@localhost:5432/f1pace')
parser_logger = logging.getLogger('Parser')


def parse_and_save(session_year, session_round, session_type, session_id, event_id, multiviewer_api_key):
    
    headers = {
        "accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,image/apng,*/*;q=0.8,application/signed-exchange;v=b3;q=0.7",
        "accept-language": "ru,en;q=0.9,en-GB;q=0.8,en-US;q=0.7",
        "cache-control": "max-age=0",
        "if-modified-since": "Mon, 22 Jun 2026 12:17:52 GMT",
        "priority": "u=0, i",
        "sec-ch-ua": '"Microsoft Edge";v="149", "Chromium";v="149", "Not)A;Brand";v="24"',
        "sec-ch-ua-mobile": "?0",
        "sec-ch-ua-platform": '"Windows"',
        "sec-fetch-dest": "document",
        "sec-fetch-mode": "navigate",
        "sec-fetch-site": "none",
        "sec-fetch-user": "?1",
        "upgrade-insecure-requests": "1",
        "user-agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/149.0.0.0 Safari/537.36 Edg/149.0.0.0",
    }

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
        cursor = conn.execute(text(f"SELECT * FROM track_map WHERE event_id = {event_id}"))
        curr_s_track_map = cursor.fetchall()

    condition = (len(curr_s_results)!=0 and 
                 len(curr_s_style_info)!=0 and 
                 len(curr_s_laps)!=0 and 
                 len(curr_s_track_corners)!=0 and 
                 len(curr_s_weather)!=0)

    if condition and len(curr_s_track_map)!=0:
        parser_logger.info(f"Уже есть запись везде с session_id={session_id}")
        return

    if not condition:
        fastf1_session = get_session(session_year, session_round, session_type)
        fastf1_session.load()

    try:
        if len(curr_s_results)==0:
            results = parse_results(fastf1_session, session_id)
            results.to_sql("results", engine, if_exists='append', index=False,)
            parser_logger.info(f"Запись в results с session_id={session_id}")
    except Exception as e:
        parser_logger.error(f"Ошикба записи в results с session_id={session_id} - {type(e)} - {e}")

    try:
        if len(curr_s_style_info)==0:
            style_info = parse_style(fastf1_session, session_id)
            style_info.to_sql('style_info', engine, index=False, if_exists='append')
            parser_logger.info(f"Запись в style_info с session_id={session_id}")
    except Exception as e:
        parser_logger.error(f"Ошикба записи в style_info с session_id={session_id} - {type(e)} - {e}")

    try:
        if len(curr_s_laps)==0:
            laps = parse_laps(fastf1_session, session_id)
            laps.to_sql('laps', engine, index=False, if_exists='append')
            parser_logger.info(f"Запись в laps с session_id={session_id}")
    except Exception as e:
        parser_logger.error(f"Ошикба записи в laps с session_id={session_id} - {type(e)} - {e}")

    try:
        if len(curr_s_weather)==0:
            weather = parse_weather(fastf1_session, session_id)
            weather.to_sql('weather', engine, index=False, if_exists='append')
            parser_logger.info(f"Запись в weather с session_id={session_id}")
    except Exception as e:
        parser_logger.error(f"Ошикба записи в weather с session_id={session_id} - {type(e)} - {e}")
    


    try:
        if len(curr_s_track_corners)==0:
            circuit_info = fastf1_session.get_circuit_info()
            corners = circuit_info.corners[["X", "Y", "Angle", "Number", "Distance"]]
            corners.columns = ["x", 'y', 'angle', 'number', 'distance']
            corners["event_id"] = event_id
            corners["rotation"] = circuit_info.rotation
            corners.to_sql('track_corners', engine, if_exists='append', index=False)
            parser_logger.info(f"Запись в track_corners с session_id={session_id} event_id={event_id}")
    except Exception as e:
        parser_logger.error(f"Ошикба записи в track_corners с session_id={session_id} event_id={event_id} - {type(e)} - {e}")

    try:
        if len(curr_s_track_map)==0:
            response = requests.get(f"https://api.multiviewer.app/api/v1/circuits/{multiviewer_api_key}/{session_year}", headers=headers)
            if response.status_code==200:
                map = response.json()
                length = len(map["x"])
                data = [[i, map["x"][i], map["y"][i]] for i in range(length)]
                map = pd.DataFrame(data, columns=['idx', 'x', 'y'])
                map["event_id"] = event_id
                map.to_sql('track_map', engine, if_exists='append', index=False)
                parser_logger.info(f"Запись в track_map с session_id={session_id} event_id={event_id}")
            else:
                parser_logger.error(f"Ошибка track_map с session_id={session_id} event_id={event_id}, response status_code={response.status_code}")
    except Exception as e:
        parser_logger.error(f"Ошикба записи в track_map с session_id={session_id} event_id={event_id} - {type(e)} - {e}")

    

def parse(year, analyze=True):
    query = f"""
        SELECT s.id, st.name, e.year, e.round, s.event_id, t.multiviewer_api_key 
        FROM sessions s 
        JOIN events e ON s.event_id = e.id 
        JOIN session_types st ON s.session_type=st.id 
        join tracks t on t.id = e.track_id 
        WHERE e.year = {year}
    """

    sessions = pd.read_sql(query, engine)

    i = 0
    while i < len(sessions):
        try:
            parse_and_save(
                sessions.loc[i, "year"], 
                sessions.loc[i, "round"], 
                sessions.loc[i, "name"], 
                sessions.loc[i, "id"],
                sessions.loc[i, "event_id"], 
                sessions.loc[i, "multiviewer_api_key"]
            )
            
        except RateLimitExceededError as e: 
            parser_logger.error(f"Rate limit to fastf1, sleep 300s. Retrying session_id={sessions.loc[i, "id"]}...")
            time.sleep(300)
            i -= 1
        except Exception as e:
            parser_logger.error(f"Ошикба парсинга с session_id={sessions.loc[i, "id"]} : {type(e)}")
        finally:
            i += 1

    if analyze:
        analyze_laps()


    

        
        