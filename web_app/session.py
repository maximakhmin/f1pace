import base64
import zlib
import json
import pandas as pd
from sqlalchemy import create_engine, text
import os
from datetime import datetime as dt, timezone
from datetime import timedelta as td
from dotenv import load_dotenv
from parse_session import convert_tyre, convert_time
from emulate import parse_line
import logging
import asyncio
from sqlalchemy.ext.asyncio import create_async_engine

load_dotenv()
engine = create_engine(f'postgresql://{os.getenv('DB_USER')}:{os.getenv('DB_PASSWORD')}@localhost:5432/f1pace')
async_engine = create_async_engine(f"postgresql+asyncpg://{os.getenv('DB_USER')}:{os.getenv('DB_PASSWORD')}@localhost:5432/f1pace")
logger = logging.getLogger('Live Time Parser')


def decode(data):
    compressed_bytes = base64.b64decode(data)
    raw_bytes = zlib.decompress(compressed_bytes, wbits=-zlib.MAX_WBITS)
    # raw_bytes = zlib.decompress(compressed_bytes, wbits=16 + zlib.MAX_WBITS)
    json_string = raw_bytes.decode('utf-8')
    return json.loads(json_string)


def parse_to_naive_utc(timestamp_str):
    """Превращает ISO-строку в datetime объект строго без таймзоны (naive), 
    но предварительно переводит в UTC, если был указан другой пояс."""
    parsed = dt.fromisoformat(timestamp_str)
    if parsed.tzinfo is not None:
        # Переводим в UTC и сбрасываем инфо о зоне
        return parsed.astimezone(timezone.utc).replace(tzinfo=None)
    return parsed

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

                async with async_engine.connect() as connection:
                    query = text("UPDATE real_time SET time = :new_time")
                    await connection.execute(query, {"new_time" : current_time})
                    await connection.commit()

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
            connection.execute(text("DELETE FROM real_time_weather"))
            connection.execute(text("INSERT INTO real_time(time) VALUES (:time)"), {"time" : dt.now()})
            connection.commit()

    async def get_current_lap(self, driver_number):
        # Используем асинхронный контекстный менеджер connect()
        async with async_engine.connect() as connection:
            query = text("SELECT MAX(lap_number) FROM real_time_laps WHERE driver_number = :driver_number")
            # Обязательно await при выполнении запроса
            cursor = await connection.execute(query, {"driver_number": driver_number})
            
            # Метод fetchone() у объекта Result в SQLAlchemy выполняется синхронно, 
            # так как данные уже вычитаны из сети на этапе await connection.execute
            row = cursor.fetchone()
            curr_lap = row[0] if row else None
            
        if curr_lap:
            return curr_lap
        return 1

    async def replace_attr(self, driver_number, new_value, attr_name):
        driver_number = int(driver_number)
        async with async_engine.connect() as connection:
            select_query = text("SELECT 1 FROM real_time_results WHERE driver_number = :driver_number")
            update_query = text(f"UPDATE real_time_results SET {attr_name} = :new_value WHERE driver_number = :driver_number")
            insert_query = text(f"INSERT INTO real_time_results(driver_number, {attr_name}) VALUES (:driver_number, :new_value)")

            params = {
                "driver_number": driver_number,
                "new_value": new_value,
            }

            cursor = await connection.execute(select_query, params)
            if cursor.first() is not None:
                await connection.execute(update_query, params)
            else:
                await connection.execute(insert_query, params)
            
            # Подтверждаем транзакцию асинхронно
            await connection.commit()


    async def load(self, line):
        try:
            data_type, data, timestamp = parse_line(line)
            current_timestamp = parse_to_naive_utc(timestamp)
            
            if self.task:
                self.task.cancel()
            self.task = asyncio.create_task(self.update_time_in_db(current_timestamp))

            if data_type.endswith(".z"):
                try:
                    data = decode(data)
                except Exception as e:
                    logger.error(f"Ошибка декодирования строки {line} : {e}")
                    return

            # --- Блок POSITION ---
            if "position" in data_type.lower():
                position_df_data = []
                for positions_with_timestamp in data["Position"]:
                    timestamp = positions_with_timestamp["Timestamp"]
                    for key, value in positions_with_timestamp["Entries"].items():
                        position_df_data.append([int(key), parse_to_naive_utc(timestamp), value["Status"], value["X"], value["Y"], value["Z"]])

                position_df = pd.DataFrame(position_df_data, columns=["driver_number", "time_utc", "status", "x", "y", "z"])
                
                # Альтернатива to_sql: переводим в dict и делаем асинхронный bulk insert
                async with async_engine.begin() as conn:
                    query = text("""
                        INSERT INTO real_time_position (driver_number, time_utc, status, x, y, z) 
                        VALUES (:driver_number, :time_utc, :status, :x, :y, :z)
                    """)
                    await conn.execute(query, position_df.to_dict(orient="records"))

                logger.debug(f"Запись real-time позиции, {len(position_df)} записей")

            # --- Блок RACECONTROLMESSAGES ---
            if "racecontrolmessages" in data_type.lower():
                messages_df_data = []
                for message in data["Messages"].values():
                    messages_df_data.append([parse_to_naive_utc(message["Utc"]), int(message["Lap"]), message["Message"]])

                messages_df = pd.DataFrame(messages_df_data, columns=["time_utc", "lap", "message"])
                
                async with async_engine.begin() as conn:
                    query = text("""
                        INSERT INTO real_time_messages (time_utc, lap, message) 
                        VALUES (:time_utc, :lap, :message)
                    """)
                    await conn.execute(query, messages_df.to_dict(orient="records"))

                logger.info(f"Запись real-time сообщений, {len(messages_df)} записей")

            # --- Блок TIMINGDATA ---
            if "timingdata" in data_type.lower():
                laps = []
                for key, value in data["Lines"].items():
                    try:
                        # Добавлен await для вызовов replace_attr
                        if "GapToLeader" in value.keys():
                            await self.replace_attr(driver_number=key, new_value=value["GapToLeader"], attr_name="gap_leader")
                            logger.debug(f"Запись real-time gap_leader")
                        if "IntervalToPositionAhead" in value.keys():
                            if "Value" in value["IntervalToPositionAhead"].keys():
                                await self.replace_attr(driver_number=key, new_value=value["IntervalToPositionAhead"]["Value"], attr_name="gap_ahead")
                                logger.debug(f"Запись real-time gap_ahead")
                        if "Line" in value.keys():
                            await self.replace_attr(driver_number=key, new_value=value["Line"], attr_name="position")
                            logger.debug(f"Запись real-time driver position")
                        if "LastLapTime" in value.keys() and "NumberOfLaps" in value.keys():
                            lap_time = dt.strptime(value["LastLapTime"]["Value"], "%M:%S.%f") - dt.strptime("00:00", "%M:%S")
                            laps.append([int(key), convert_time(lap_time), value["NumberOfLaps"], current_timestamp])

                    except Exception as e:
                        logger.warning(f"Ошибка парсинга timingdata {e}")
                
                if len(laps) > 0:
                    laps_df = pd.DataFrame(laps, columns=["driver_number", "lap_time", "lap_number", "end_time_utc"])         
                    async with async_engine.begin() as conn:
                        query = text("""
                            INSERT INTO real_time_laps (driver_number, lap_time, lap_number, end_time_utc) 
                            VALUES (:driver_number, :lap_time, :lap_number, :end_time_utc)
                        """)
                        await conn.execute(query, laps_df.to_dict(orient="records"))
                    logger.info(f"Запись real-time кругов, {len(laps_df)} записей")

            # --- Блок TIMINGAPPDATA ---
            if "timingappdata" in data_type.lower():
                stints = []
                for key, value in data["Lines"].items():
                    try:
                        driver_number = int(key)
                        if isinstance(value["Stints"], dict):
                            items = value["Stints"].items()
                        else:
                            items = enumerate(value["Stints"])
                        for key2, value2 in items:
                            stint_number = key2
                            compound = convert_tyre(value2["Compound"])
                            total_laps = value2["TotalLaps"]
                            
                            # Добавлен await — ждем выполнения get_current_lap
                            start_lap = await self.get_current_lap(driver_number)
                            
                            stints.append([int(driver_number), int(stint_number), int(compound), int(total_laps), int(start_lap)])
                    except Exception as e:
                        logger.warning(f"Ошибка парсинга стинта : {value} : {e}")

                if len(stints) > 0:
                    stints_df = pd.DataFrame(stints, columns=["driver_number", "stint_number", "tyre_type", "total_laps", "start_lap"])
                    
                    async with async_engine.begin() as conn:
                        query = text("""
                            INSERT INTO real_time_stints (driver_number, stint_number, tyre_type, total_laps, start_lap) 
                            VALUES (:driver_number, :stint_number, :tyre_type, :total_laps, :start_lap)
                        """)
                        # Названия плейсхолдеров (:Driver_number) должны строго совпадать с колонками DataFrame
                        await conn.execute(query, stints_df.to_dict(orient="records"))
                        
                    

             # --- Блок WEATHERDATA ---
            if "weatherdata" in data_type.lower():
                try:
                    async with async_engine.begin() as conn:
                        query = text("""
                            INSERT INTO real_time_weather (time_utc, air_temp, humidity, pressure, is_rain, track_temp, wind_direction, wind_speed) 
                            VALUES (:time_utc, :air_temp, :humidity, :pressure, :is_rain, :track_temp, :wind_direction, :wind_speed) 
                        """)

                        params = {
                            "time_utc" : current_timestamp,
                            "air_temp" : float(data.get("AirTemp")),
                            "humidity" : float(data.get("Humidity")),
                            "pressure" : float(data.get("Pressure")),
                            "is_rain" : bool(int(data.get("Rainfall"))),
                            "track_temp" : float(data.get("TrackTemp")),
                            "wind_direction" : float(data.get("WindDirection")),
                            "wind_speed" : float(data.get("WindSpeed")),
                        }

                        await conn.execute(query, params)
                        
                        logger.info(f"Запись real-time погоды")
                except Exception as e:
                    logger.error(f"Ошибка записи real-time погоды : {data} : {e}")

        except Exception as e:
            logger.error(f"Ошибка парсинга строки {line} : {e}")
