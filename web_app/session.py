import base64
import zlib
import json
import pandas as pd
from sqlalchemy import create_engine, text
import os
from datetime import datetime as dt
from datetime import timedelta as td
from dotenv import load_dotenv
from parse_session import convert_tyre, convert_time
from emulate import parse_line
import logging
import asyncio

load_dotenv()
engine = create_engine(f'postgresql://{os.getenv('DB_USER')}:{os.getenv('DB_PASSWORD')}@localhost:5432/f1pace')
logger = logging.getLogger('Live Time Parser')

def decode(data):
    compressed_bytes = base64.b64decode(data)
    raw_bytes = zlib.decompress(compressed_bytes, wbits=-zlib.MAX_WBITS)
    # raw_bytes = zlib.decompress(compressed_bytes, wbits=16 + zlib.MAX_WBITS)
    json_string = raw_bytes.decode('utf-8')
    return json.loads(json_string)

class Session:
    def __init__(self, speed):
        self.speed = speed
        self.clean_database()
        self.task = None

    async def update_time_in_db(self, start_time):
        """
        Асинхронно обновляет время в базе данных 10 раз в секунду.
        """
        current_time = start_time
        interval = 0.1 

        logger.debug("Начинаю обновление времени в бд")
        
        try:
            while True:

                current_time += td(seconds=(interval * self.speed))
                with engine.connect() as connection:
                    query = text("UPDATE real_time SET time = :new_time")
                    connection.execute(query, {"new_time" : current_time})
                    connection.commit()
                await asyncio.sleep(interval)
                
        except Exception as e:
            logger.error(f"Ошибка записи времени {e}")


    def clean_database(self):
        with engine.connect() as connection:
            connection.execute(text("DELETE FROM real_time_position"))
            connection.execute(text("DELETE FROM real_time_messages"))
            connection.execute(text("DELETE FROM real_time_results"))
            connection.execute(text("DELETE FROM real_time_laps"))
            connection.execute(text("DELETE FROM real_time_stints"))
            connection.execute(text("DELETE FROM real_time"))
            connection.execute(text("INSERT INTO real_time(time) VALUES (:time)"), {"time" : dt.now()})
            connection.commit()

    def get_current_lap(self, driver_number):
        with engine.connect() as connection:
            query = text("SELECT MAX(lap_number) FROM real_time_laps WHERE driver_number = :driver_number")
            cursor = connection.execute(query, {"driver_number" : driver_number})
        curr_lap = cursor.fetchone()[0]
        if curr_lap:
            return curr_lap
        else:
            return 1

    def replace_attr(self, driver_number, new_value, attr_name):
        with engine.connect() as connection:

            select_query = text("SELECT 1 FROM real_time_results WHERE driver_number= :driver_number ")
            update_query = text(f"UPDATE real_time_results SET {attr_name} = :new_value WHERE driver_number= :driver_number")
            insert_query = text(f"INSERT INTO real_time_results(driver_number, {attr_name}) VALUES (:driver_number, :new_value)")

            params = {
                "driver_number" : driver_number,
                "new_value" : new_value,
            }

            cursor = connection.execute(select_query, params)
            if cursor.first() is not None:
                connection.execute(update_query, params)
            else:
                connection.execute(insert_query, params)
            connection.commit()


    def load(self, line):
        
        try:

            data_type, data, timestamp = parse_line(line)

            current_timestamp = dt.fromisoformat(timestamp)
            if self.task:
                self.task.cancel()
            self.task = asyncio.create_task(self.update_time_in_db(current_timestamp))

            if data_type.endswith(".z"):
                try:
                    data = decode(data)
                except Exception as e:
                    logger.error(f"Ошибка декодирования строки {line} : {e}")
                    return

            if "position" in data_type.lower():

                position_df_data = []
                for positions_with_timestamp in data["Position"]:
                    timestamp = positions_with_timestamp["Timestamp"]
                    for key, value in positions_with_timestamp["Entries"].items():
                        position_df_data.append([int(key), dt.fromisoformat(timestamp), value["Status"], value["X"], value["Y"], value["Z"]])

                position_df = pd.DataFrame(position_df_data, columns=["driver_number", "time_utc", "status", "x", "y", "z"])
                position_df.to_sql("real_time_position", engine, if_exists="append", index=False)

                logger.debug(f"Запись real-time позиции, {len(position_df)} записей")

            if "racecontrolmessages" in data_type.lower():
                
                messages_df_data = []

                for message in data["Messages"].values():
                    messages_df_data.append([dt.fromisoformat(message["Utc"]), int(message["Lap"]), message["Message"]])

                messages_df = pd.DataFrame(messages_df_data, columns=["time_utc", "lap", "message"])
                messages_df.to_sql("real_time_messages", engine, if_exists="append", index=True, index_label="id")

                logger.info(f"Запись real-time сообщений, {len(messages_df)} записей")


            if "timingdata" in data_type.lower():
                laps = []
                for key, value in data["Lines"].items():
                    try:
                        if "GapToLeader" in value.keys():
                            self.replace_attr(driver_number=key, new_value=value["GapToLeader"], attr_name="gap_leader")
                            logger.debug(f"Запись real-time gap_leader")
                        if "IntervalToPositionAhead" in value.keys():
                            if "Value" in value["IntervalToPositionAhead"].keys():
                                self.replace_attr(driver_number=key, new_value=value["IntervalToPositionAhead"]["Value"], attr_name="gap_ahead")
                                logger.debug(f"Запись real-time gap_ahead")
                        if "Line" in value.keys():
                            self.replace_attr(driver_number=key, new_value=value["Line"], attr_name="position")
                            logger.debug(f"Запись real-time driver position")
                        if "LastLapTime" and "NumberOfLaps" in value.keys():
                            lap_time = dt.strptime(value["LastLapTime"]["Value"], "%M:%S.%f") - dt.strptime("00:00", "%M:%S")
                            laps.append([int(key), convert_time(lap_time), value["NumberOfLaps"]])

                    except Exception as e:
                        logger.warning(f"Ошибка парсинга timingdata {e}")
                
                if len(laps) > 0:
                    laps_df = pd.DataFrame(laps, columns=["driver_number", "lap_time", "lap_number"])         
                    laps_df.to_sql("real_time_laps", engine, if_exists="append", index=False)
                    logger.info(f"Запись real-time кругов, {len(laps_df)} записей")


            if "timingappdata" in data_type.lower():
                laps = []
                stints = []
                for key, value in data["Lines"].items():
                    try:
                        driver_number = int(key)
                        if type(value["Stints"]) == dict:
                            items = value["Stints"].items()
                        else:
                            items = enumerate(value["Stints"])
                        for key2, value2 in items:
                            stint_number = key2
                            compound = convert_tyre(value2["Compound"])
                            total_laps = value2["TotalLaps"]
                            start_lap = self.get_current_lap(driver_number)
                            
                            stints.append([int(driver_number), int(stint_number), int(compound), int(total_laps), int(start_lap)])
                    except Exception as e:
                        logger.warning(f"Ошибка парсинга стинта : {value} : {e}")

                if len(stints) > 0:
                    stints_df = pd.DataFrame(stints, columns=["Driver_number", "stint_number", "tyre_type", "total_laps", "start_lap"])
                    stints_df.to_sql("real_time_stints", engine, if_exists="append", index=True, index_label="id")
                    logger.info(f"Запись real-time стинтов, {len(stints_df)} записей")

        except Exception as e:
            logger.error(f"Ошибка парсинга строки {line} : {e}")
