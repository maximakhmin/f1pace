import pandas as pd
import os
from dotenv import load_dotenv
from sqlalchemy import create_engine, text
from fastf1.plotting import list_driver_abbreviations, get_driver_style, get_team_name_by_driver, get_driver_name


load_dotenv()

engine = create_engine(f'postgresql://{os.getenv('DB_USER')}:{os.getenv('DB_PASSWORD')}@{os.getenv('DB_HOST')}/{os.getenv('DB_NAME')}')


def find_driver(abbr, first_name, last_name):
    abbr = abbr.upper()
    first_name = first_name.capitalize().replace("'", "\'")
    last_name = last_name.capitalize().replace("'", "\'")

    with engine.connect() as conn:
        query = text(f"SELECT id FROM drivers WHERE first_name = :first_name AND last_name = :last_name LIMIT 1")
        cursor = conn.execute(query, {
            "first_name" : first_name, 
            "last_name" : last_name,
        })
        driver_id = cursor.fetchone()
        if driver_id:
            return driver_id[0]
        else:
            query = text("""
                INSERT INTO drivers (abbr, first_name, last_name) 
                VALUES (:abbr, :f_name, :l_name)
            """)
            conn.execute(query, {
                "abbr": abbr, 
                "f_name": first_name, 
                "l_name": last_name
            })
            conn.commit()
            return find_driver(abbr, first_name, last_name)


def convert_time(x):
    return x.seconds +  x.microseconds * 1e-6
    
def calc_time(row):
    cols = ["Time", "Q3", "Q2", "Q1"]
    for col in cols:
        if not pd.isna(row[col]):
            return convert_time(row[col])
    return None

def calc_time_practice(row, laps):
    try:
        return convert_time(laps.pick_drivers(row["Abbreviation"]).pick_fastest()["LapTime"])
    except (ValueError, KeyError, IndexError, TypeError):
        return None

def calc_lap_count(row, laps):
    return len(laps.pick_drivers(row["Abbreviation"]))

def set_status(row):
    st = row["Status"]
    if pd.isna(st) or st=='':
        st = "Unknown"
    with engine.connect() as conn:
        cursor = conn.execute(text(f"SELECT id FROM result_statuses WHERE name = '{st}' LIMIT 1"))
        status_id = cursor.fetchone()
        if status_id:
            return status_id[0]
        else:
            query = text("""
                INSERT INTO result_statuses (name) 
                VALUES (:name)
            """)
            conn.execute(query, {
                "name": st, 
            })
            conn.commit()
            return set_status(row)
        
TYRES = [
    'UNKNOWN',
    'SOFT', 
    'MEDIUM', 
    'HARD', 
    'INTERMEDIATE',
    'WET',
]
def convert_tyre(x):
    if not x in TYRES:
        return TYRES.index("UNKNOWN")
    return TYRES.index(x)

def convert_track_status(x):
    priority = [5, 4, 6, 7, 2, 1, 3]
    for p in priority:
        if str(p) in x:
            return p
    return 3

def find_weather(row, weather):
    time1 = row["Time"]
    for i in range(len(weather)):   
        time2 = weather.loc[i, "Time"] 
        if time2 > time1:
            break
    return weather.loc[i][["AirTemp", "TrackTemp", "Humidity", "Rainfall", "WindDirection", "WindSpeed"]]

def get_first_last_name(row, session):
    full_name = get_driver_name(row["Driver"], session)
    return full_name[:full_name.find(' ')], full_name[full_name.find(' ')+1:]

def parse_results(fastf1_session, session_id):
    if fastf1_session.session_info["Type"] == 'Practice':
        laps = fastf1_session.laps
        results = fastf1_session.results
        results["time"] = results.apply(calc_time_practice, axis=1, laps=laps)
        results["laps"] = results.apply(calc_lap_count, axis=1, laps=laps)
        results["driver_id"] = results.apply(
            lambda row : find_driver(row["Abbreviation"], 
                                     row["FirstName"], 
                                     row["LastName"]), 
            axis = 1
        )
        results["session_id"] = session_id
        results = results.sort_values("time").reset_index()
        results["position"] = results.index + 1
        results["result_status_id"] = results.apply(set_status, axis=1)
        results["classified_position"] = results["ClassifiedPosition"].apply(lambda x : None if x=='' else x)
        
    else:
        results = fastf1_session.results
        results["time"] = results.apply(calc_time, axis=1)
        results["driver_id"] = results.apply(
            lambda row : find_driver(row["Abbreviation"], 
                                     row["FirstName"], 
                                     row["LastName"]), 
            axis = 1
        )
        results["session_id"] = session_id
        results["position"] = results["Position"].astype('Int32')
        results["laps"] = results["Laps"].astype('Int32')
        results["result_status_id"] = results.apply(set_status, axis=1)
        results["classified_position"] = results["ClassifiedPosition"].apply(lambda x : None if x=='' else x)

    results = results.reset_index()

    return results[["session_id", "driver_id", "result_status_id", "position", "time", "laps", "classified_position"]]



def parse_style(fastf1_session, session_id):
    style_data = []
    style_list = ['linestyle', 'marker', 'color', 'facecolor', 'edgecolor']
    style_columns = ['session_id', 'driver_id', 'team', 'number'] + style_list
    abbrs = list_driver_abbreviations(fastf1_session)
    for abbr in abbrs:
        style = get_driver_style(abbr, style_list, fastf1_session, exact_match=True)
        driver_info = fastf1_session.get_driver(abbr)
        full_name = get_driver_name(abbr, fastf1_session, exact_match=True)
        first_name, last_name = full_name.split(" ", 1)
        style_data.append([
            session_id,
            find_driver(abbr, first_name, last_name),
            get_team_name_by_driver(abbr, fastf1_session, short=True, exact_match=True),
            driver_info["DriverNumber"]
            ] +
            [style[attr] for attr in style_list]
        )

    return pd.DataFrame(style_data, columns=style_columns)


def parse_laps(fastf1_session, session_id):

    fastf1_session.load(telemetry=False, laps=True, weather=True)

    laps_df = fastf1_session.laps[["Time", "LapStartTime", "Driver", "DriverNumber", 
                            "LapTime", "Sector1Time", "Sector2Time", "Sector3Time", "PitInTime", "PitOutTime",
                            "LapNumber", "Stint", "TyreLife", "Compound", "Deleted", "TrackStatus", "Position"]].copy()


    laps_df["LapTime"] = laps_df["LapTime"].apply(convert_time)
    laps_df["Sector1Time"] = laps_df["Sector1Time"].apply(convert_time)
    laps_df["Sector2Time"] = laps_df["Sector2Time"].apply(convert_time)
    laps_df["Sector3Time"] = laps_df["Sector3Time"].apply(convert_time)
    laps_df["session_time_start"] = laps_df["LapStartTime"].apply(convert_time)
    laps_df["session_time_end"] = laps_df["Time"].apply(convert_time)
    laps_df["PitInTime"] = laps_df["PitInTime"].apply(convert_time)
    laps_df["PitOutTime"] = laps_df["PitOutTime"].apply(convert_time)

    laps_df["Compound"] = laps_df["Compound"].apply(convert_tyre)
    laps_df["TrackStatus"] = laps_df["TrackStatus"].apply(convert_track_status)
    laps_df["session_id"] = session_id

    laps_df["LapNumber"] = laps_df["LapNumber"].astype('Int64')
    laps_df["TyreLife"] = laps_df["TyreLife"].astype('Int64')
    laps_df["Stint"] = laps_df["Stint"].astype('Int64')
    laps_df["Position"] = laps_df["Position"].astype('Int64')



    laps_df[["FirstName", "LastName"]] = laps_df.apply(get_first_last_name, session=fastf1_session, axis=1, result_type='expand')

    laps_df["driver_id"] = laps_df.apply(
        lambda row : find_driver(row["Driver"], 
                                    row["FirstName"], 
                                    row["LastName"]), 
        axis = 1
    )
   
    laps_df = (
        laps_df
        .rename(columns={
            "PitInTime"    : "pit_in_session_time",
            "PitOutTime"   : "pit_out_session_time",
            "LapTime"      : "lap_time",
            "Sector1Time"  : "lap_s1_time",
            "Sector2Time"  : "lap_s2_time",
            "Sector3Time"  : "lap_s3_time",
            "LapNumber"    : "lap_number",
            "Stint"        : "stint_number",
            "TyreLife"     : "tyre_age",
            "Compound"     : "tyre_type",
            "Deleted"      : "is_deleted",
            "TrackStatus"  : "track_status",
            "Position"     : "position",
        })
    )[["session_id", "driver_id", "position", "session_time_start", "session_time_end", "pit_in_session_time", "pit_out_session_time",
        "lap_time", "lap_s1_time", "lap_s2_time", "lap_s3_time", "lap_number", "stint_number", "tyre_age", 
        "tyre_type", "is_deleted", "track_status"]]

    return laps_df
    

def parse_weather(fastf1_session, session_id):
    weather = fastf1_session.weather_data
    weather["session_time"] = weather["Time"].apply(convert_time)
    weather["session_id"] = session_id
    weather = weather.rename(columns={
        "AirTemp"      : "air_temp", 
        "TrackTemp"    : "track_temp", 
        "Humidity"     : "humidity",
        "Rainfall"     : "is_rain",
        "WindDirection": "wind_direction",
        "WindSpeed"    : "wind_speed",
    })[["session_id", "session_time", "air_temp", "track_temp", "humidity", "is_rain", "wind_direction", "wind_speed"]]

    return weather


