import streamlit as st
import pandas as pd
from dotenv import load_dotenv
from sqlalchemy import create_engine
import os

load_dotenv()
engine = create_engine(f'postgresql://{os.getenv('DB_USER')}:{os.getenv('DB_PASSWORD')}@localhost:5432/f1pace')

query = """select s.id, e.year, e.round, st.name session_type, st.id session_type_id, t.country, t.circuit_name from sessions s
join events e on s.event_id = e.id 
join tracks t on e.track_id = t.id
join session_types st on s.session_type = st.id"""

sessions = pd.read_sql(query, engine)


st.set_page_config(
    page_title="Session results",
    layout="centered",
    initial_sidebar_state="expanded",
)
st.title("Session results")



available_years = sorted(sessions['year'].unique(), reverse=True)
selected_year = st.selectbox("Выберите год", available_years)

mask = (sessions["year"] == selected_year)


rounds_map = dict(zip(sessions[mask]['round'], zip(sessions[mask]['country'], sessions[mask]['circuit_name'])))


available_rounds = sorted(sessions[mask]['round'].unique())
selected_round = st.selectbox(
    "Выберите раунд", 
    options=available_rounds, 
    format_func=lambda x : f"{x} - {rounds_map[x][0]}, {rounds_map[x][1]}")


mask &= (sessions["round"] == selected_round)


available_session_types = sessions[mask]['session_type'].unique()
selected_session_type = st.selectbox("Выберите тип заезда", available_session_types)

mask &= (sessions["session_type"] == selected_session_type)

selected_session = sessions[mask]["id"].values[0]
selected_session_type = sessions[mask]["session_type_id"].values[0]

query = f"""select r.position, r.classified_position, r.laps, r.time, 
d.first_name, d.last_name, si.team, si.color 
from results r
join drivers d on r.driver_id = d.id
join style_info si on si.driver_id=d.id and si.session_id=r.session_id
where r.session_id={selected_session}
order by r.position"""

results = pd.read_sql(query, engine)

if results.empty:
    st.write("The results for this session have not been uploaded yet")
    st.stop()


results["driver_name"] = results.apply(
    lambda row : f":color[▍]{{foreground='{row['color']}'}}{row['first_name']} {row['last_name']}",
    axis=1
)
results["position"] = results["position"].astype('Int32')
results["laps"] = results["laps"].astype('Int32')


def calc_delta_race(row, total_laps):

    if pd.isna(row["classified_position"]):
        return ""

    statuses = {
        "R" : "Retired", 
        "D" : "Disqualified", 
        "E" : "Excluded", 
        "W" : "Withdrawn", 
        "F" : "Failed to qualify", 
        "N" : "Not classified"
    }

    if row["position"] == 1:
        return f"{int(row['time']) // 60}:{row['time'] % 60:06.3f}"
    elif not pd.isna(pd.to_numeric(row["classified_position"], errors='coerce')):
        if row["laps"] == total_laps:
            minutes = int(row['time'] // 60)
            if minutes==0:
                return f"+{row['time'] % 60:06.3f}"
            else:
                return f"+{minutes}:{row['time'] % 60:06.3f}"
        else:
            return f"+{total_laps - row["laps"]} laps"
    else:
        return statuses[row["classified_position"]]

    
def calc_delta(row, first_time):
    if not pd.isna(row["time"]):
        delta = row["time"] - first_time
        minutes = int(delta // 60)
        if minutes==0:
            return f"+{delta % 60:06.3f}"
        else:
            return f"+{minutes}:{delta % 60:06.3f}"
    else:
        return " "
    
def convert_time(row):
    if not pd.isna(row["time"]):
        return f"{int(row['time']) // 60}:{row['time'] % 60:06.3f}"
    else:
        return "No time"
    
table_data = pd.DataFrame()
    
if selected_session_type in (1, 2, 3):
    results["delta"] = results.apply(calc_delta, first_time=results.loc[0, "time"], axis=1)
    results["converted_time"] = results.apply(convert_time, axis=1)
    table_data = results[["position", "driver_name", "team", "laps", "converted_time", "delta"]]
    table_data.columns = ["Pos", "Name", "Team", "Laps", "Time", "Delta"]

elif selected_session_type in (4, 6):
    results["delta"] = results.apply(calc_delta, first_time=results.loc[0, "time"], axis=1)
    results["converted_time"] = results.apply(convert_time, axis=1)
    table_data = results[["position", "driver_name", "team", "converted_time", "delta"]]
    table_data.columns = ["Pos", "Name", "Team", "Time", "Delta"]

elif selected_session_type in (5, 7):
    results["delta"] = results.apply(calc_delta_race, total_laps=results.loc[0, "laps"], axis=1)
    table_data = results[["position", "driver_name", "team", "delta"]]
    table_data.columns = ["Pos", "Name", "Team", "Delta"]

if not table_data.empty:
    st.table(table_data, border="horizontal")