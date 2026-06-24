import os
from dotenv import load_dotenv
import pandas as pd
from sqlalchemy import create_engine, text
import logging

load_dotenv()
engine = create_engine(f'postgresql://{os.getenv('DB_USER')}:{os.getenv('DB_PASSWORD')}@localhost:5432/f1pace')

logger = logging.getLogger("Analyze")

def analyze_laps():
    try:
        laps = pd.read_sql("SELECT * FROM laps ORDER BY session_id, driver_id, lap_number", engine)

        laps["is_first_lap"] = laps.apply(lambda row : True if row["lap_number"] == 1 else False, axis=1)

        laps["is_last_lap"] = False
        last_laps = laps.groupby(["session_id", "driver_id"])["id"].last().values
        for last_lap_id in last_laps:
            laps.loc[laps["id"] == last_lap_id, "is_last_lap"] = True

        laps["is_pit_out_lap"] = False
        pit_in_laps = laps.groupby(["session_id", "driver_id"])["stint_number"].diff()

        laps.loc[(pit_in_laps > 0), "is_pit_out_lap"] = True

        laps["is_pit_in_lap"] = False

        mask = laps["is_pit_out_lap"].shift(-1) == True

        laps.loc[mask, "is_pit_in_lap"] = True

        mask = (
            (pd.isna(laps["lap_time"]))
        )

        laps.loc[mask, "lap_time"] = laps.loc[mask, "session_time_end"] - laps.loc[mask, "session_time_start"]
        
        
        laps.to_sql("laps_cleaned", engine, index=False, if_exists='replace')

        logger.info("Translated laps into laps_cleaned")

    except Exception as e:
        logger.exception(f"Ошибка при создании laps_cleaned : {str(e)}")
