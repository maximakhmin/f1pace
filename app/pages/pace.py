from sqlalchemy import create_engine
import pandas as pd
import numpy as np
import streamlit as st
import plotly.graph_objects as go
from plotly.subplots import make_subplots
import requests
from main import BASE_URL, check_status
from io import StringIO

response = requests.get(BASE_URL+"/track-statuses")
check_status(response)
statuses_info = pd.read_json(StringIO(response.text))
statuses_info = dict(zip(statuses_info["id"].values, zip(statuses_info["name"].values, statuses_info["color"].values)))

response = requests.get(BASE_URL+"/tyres")
check_status(response)
tyres_info = pd.read_json(StringIO(response.text))
tyres_info = dict(zip(tyres_info["id"].values, zip(tyres_info["name"].values, tyres_info["color"].values)))

response = requests.get(BASE_URL+"/sessions?only_races=true")
check_status(response)
sessions = pd.read_json(StringIO(response.text))

def calculate_deltas(laps_1, laps_2, over_zero=False):
    if min(len(laps_1), len(laps_2)) == 0:
        return [1], [0]
    
    deltas = []
    for i in range(min(len(laps_1), len(laps_2))):
        if laps_1.loc[i, "track_status"] == 5:
            deltas.append(0)
        else:
            lap_1_time = laps_1.loc[i, "session_time_end"]
            lap_2_time = laps_2.loc[i, "session_time_end"]
            deltas.append(lap_2_time-lap_1_time)

    if not over_zero:
        return np.arange(1, len(deltas)+1), deltas
    
    deltas_x = [1]
    deltas_y = [deltas[0]]
    negative = (deltas[0] < 0)
    for i in range(1, len(deltas)):
        new_delta = deltas[i]
        old_delta = deltas_y[-1]
        new_negative = (deltas[i] < 0)
        if negative == new_negative:
            deltas_x.append(i+1)
            deltas_y.append(new_delta)
        else:
            # x_zero = x1 - y1 * (x2 - x1) / (y2 - y1)
            deltas_x.append(i - old_delta * 1 / (new_delta - old_delta))
            deltas_y.append(0)

            deltas_x.append(i+1)
            deltas_y.append(new_delta)

            negative = new_negative

    return deltas_x, deltas_y

def track_statuses_ranges(laps):
    lap_numbers = laps["lap_number"].values
    statuses = laps["track_status"].values

    ranges = []
    statuses_for_ranges = []

    start = lap_numbers[0] - 0.5
    current_status = statuses[0]
    for i in range(len(lap_numbers)):
        if statuses[i] != current_status:
            ranges.append((start, lap_numbers[i] - 0.5))
            start = lap_numbers[i] - 0.5
            statuses_for_ranges.append(current_status)
            current_status = statuses[i]

    ranges.append((start, lap_numbers[-1] + 0.5))
    statuses_for_ranges.append(statuses[-1])

    return ranges, statuses_for_ranges

def hex_to_rgba(hex_color, opacity=1.0):
    """
    Преобразует HEX (#RRGGBB) в rgba(R, G, B, A).
    """
    hex_color = hex_color.lstrip('#')
    # Переводим HEX в целые числа (int)
    r, g, b = tuple(int(hex_color[i:i+2], 16) for i in (0, 2, 4))
    return f"rgba({r}, {g}, {b}, {opacity})"

def convert_time(t):
    if not pd.isna(t):
        return f"{int(t) // 60}:{t % 60:06.3f}"
    else:
        return ""
    
def driver_select_format_func(x):
    if x==0:
        return "Clear"
    color = styles[styles['driver_id'] == x]['color'].values[0]
    abbr = styles[styles['driver_id'] == x]['abbr'].values[0]
    return f":color[▍]{{foreground='{color}'}}**{abbr}**"

st.set_page_config(page_title="F1 Lap Analyzer", layout="wide")
st.title("🏎️ Сравнение времен круга")
fig = make_subplots(specs=[[{"secondary_y": True}]])

# ---------------------------- select session ---------------------------

col1, col2, col3 = st.columns([1, 6, 3])

with col1:
    available_years = sorted(sessions['year'].unique(), reverse=True)
    selected_year = st.selectbox("Выберите год", available_years)
    mask = (sessions["year"] == selected_year)

with col2:
    rounds_map = dict(zip(sessions[mask]['round'], zip(sessions[mask]['country'], sessions[mask]['circuit_name'])))

    available_rounds = sorted(sessions[mask]['round'].unique())
    selected_round = st.selectbox(
        "Выберите раунд", 
        options=available_rounds, 
        format_func=lambda x : f"{x} - {rounds_map[x][0]}, {rounds_map[x][1]}")

    mask &= (sessions["round"] == selected_round)

with col3:
    available_session_types = sessions[mask]['session_type'].unique()
    selected_session_type = st.selectbox("Выберите тип заезда", available_session_types)

    mask &= (sessions["session_type"] == selected_session_type)

session_id = sessions[mask]["id"].values[0]

response = requests.get(f"{BASE_URL}/laps/{session_id}")
check_status(response)
laps = pd.read_json(StringIO(response.text))

response = requests.get(f"{BASE_URL}/styles/{session_id}")
check_status(response)
styles = pd.read_json(StringIO(response.text))

if laps.empty:
    st.write("The results for this session have not been uploaded yet")
    st.stop()
# ---------------------------- select driver ----------------------------

all_drivers = [0] + list(styles['driver_id'].unique())

if "selected_drivers" not in st.session_state:
    st.session_state.selected_drivers = [all_drivers[1]]

if 0 in  st.session_state.selected_drivers:
    st.session_state.selected_drivers = []

selected_drivers = st.pills(
    label="Выберите пилотов для сравнения",
    options=all_drivers, 
    selection_mode="multi",
    format_func=driver_select_format_func,
    key="selected_drivers"
)

# ---------------------------- track status ----------------------------
last_lap_number = laps["lap_number"].max()
first_driver_id = laps[(laps["lap_number"] == last_lap_number) & (laps["position"] == 1)]["driver_id"].min()

data = laps[laps["driver_id"] == first_driver_id].copy()
data["formatted"] = data["track_status"].apply(lambda x : statuses_info[x][0])
ranges, statuses_for_ranges = track_statuses_ranges(data)

for r, sfr in zip(ranges, statuses_for_ranges):
    status_name = statuses_info[sfr][0]
    color_hex = statuses_info[sfr][1]
    fig.add_trace(
        go.Scatter(
            x=r,
            y=[0.1]*2,
            mode="none",
            fill="tozeroy",
            # fillcolor=hex_to_rgba(color_hex, 1),
            fillgradient=dict(
                type="vertical", 
                colorscale=[
                    [0.0, hex_to_rgba(color_hex, 0.4)], 
                    [1.0, hex_to_rgba(color_hex, 0.0)],  
                ],
            ),
            hoverinfo='skip',
            yaxis='y',
        )
    )

fig.add_trace(
    go.Scatter(
        x=data["lap_number"],
        y=data["track_status"],
        name='Track status',
        mode='none',
        customdata=data["formatted"],
        hovertemplate="%{customdata}<extra></extra>",
        yaxis='y'
    )
)

# ---------------------------- lap times ----------------------------
added_colors = []

for i in range(len(selected_drivers)):
    driver_id = selected_drivers[i]
    data = laps[(laps["driver_id"] == driver_id) & (laps["track_status"]!=5)].copy()
    if data.empty:
        continue

    driver_abbr = styles[styles['driver_id'] == driver_id]['abbr'].values[0]
    driver_color = styles[styles["driver_id"] == driver_id]["color"].values[0]

    if driver_color in added_colors:
        driver_linestyle = "dash"
        driver_marker = "circle-open"
    else:
        driver_linestyle = "solid"
        driver_marker = "0"

    added_colors.append(driver_color)

    # replace_dict = {
    #     "solid" : "solid", 
    #     "dashed" : "dash",
    #     "x" : "0",
    #     "o" : "circle-open",
    # }
    # driver_linestyle = replace_dict[styles[styles["driver_id"] == driver_id]["linestyle"].values[0]]
    # driver_marker = replace_dict[styles[styles["driver_id"] == driver_id]["marker"].values[0]]
    
    data["formatted"] = f"<b>{driver_abbr}</b>: " + data["lap_time"].apply(convert_time)

    fig.add_trace(
        go.Scatter(
            x=data['lap_number'],
            y=data['lap_time'],
            name='Lap Time',
            mode='lines',
            line=dict(color=driver_color, width=3, dash=driver_linestyle),
            marker=dict(symbol=driver_marker, size=8, line=dict(width=1, color='black')),
            customdata=data["formatted"],
            hovertemplate="%{customdata}<extra></extra>",
            yaxis='y3'
        ),
    )

    data_tyres = data[(data["lap_number"] == 1) | (data["is_pit_out_lap"] == True)]
    marker_colors = [tyres_info[tyre_type][1] for tyre_type in data_tyres['tyre_type']]
    fig.add_trace(
        go.Scatter(
            x=data_tyres['lap_number'],
            y=data_tyres['lap_time'],
            name='Tyre info',
            mode='markers',
            marker=dict(symbol='circle', 
                        size=12, 
                        color=marker_colors,
                        line=dict(
                            width=1.5,
                            color='grey' 
                        ),
            ),
            yaxis='y3',
            hoverinfo='skip',
        ),
    )

# ---------------------------- detla ----------------------------
if len(selected_drivers)==2:
    laps_1 = laps[laps["driver_id"] == selected_drivers[0]].reset_index()
    laps_2 = laps[laps["driver_id"] == selected_drivers[1]].reset_index()
    deltas_x, deltas_y = calculate_deltas(laps_1, laps_2, over_zero=True)
    axis_limit = max(abs(min(deltas_y)), abs(max(deltas_y))) * 1.1

    fig.add_trace(
        go.Scatter(
            x=deltas_x,
            y=np.maximum(deltas_y, 0),
            name='Delta',
            mode='lines',
            line=dict(width=0),
            fill='tozeroy',
            fillcolor='rgba(59, 158, 87 , 0.8)',
            hoverinfo='skip',
            yaxis='y2',      
        ),
    )
    fig.add_trace(
        go.Scatter(
            x=deltas_x,
            y=np.minimum(deltas_y, 0),
            name='Delta',
            mode='lines',
            line=dict(width=0),
            fill='tozeroy',
            fillcolor='rgba(217, 78, 78, 0.8)',
            hoverinfo='skip',
            yaxis='y2',   
        ),
    )
    deltas_x, deltas_y = calculate_deltas(laps_1, laps_2, over_zero=False)
    fig.add_trace(
        go.Scatter(
            x=deltas_x,
            y=deltas_y,
            name='Delta',
            mode='lines',
            line=dict(color='grey', width=2),
            marker=dict(size=8, line=dict(width=1, color='black')),
            hovertemplate="<b>Delta</b>: %{y:.3f}<extra></extra>",
            yaxis='y2',  
        ),
    )
    

    fig.update_layout(
        yaxis2=dict(
            title="Delta",
            side="right",
            range=[-axis_limit, axis_limit],
            zeroline=True,
            zerolinewidth=2,
            zerolinecolor='grey',
            showgrid=False,
            overlaying="y",
        ),
        annotations=[
            dict(
                x=0.95,            
                y=1.1,        
                xref="paper",
                yref="paper",
                text=f"{styles[styles['driver_id'] == selected_drivers[0]]['abbr'].values[0]} ahead",
                showarrow=False,
                font=dict(size=12, color="grey"), 
                xanchor="left"
            ),
            dict(
                x=0.95,            
                y=-0.1,        
                xref="paper",
                yref="paper",
                text=f"{styles[styles['driver_id'] == selected_drivers[1]]['abbr'].values[0]} ahead",
                showarrow=False,
                font=dict(size=12, color="grey"), 
                xanchor="left"
            ),
        ]
    )


# ---------------------------- axis ----------------------------
fig.update_layout(

    yaxis3=dict(
        title="Lap time",
        side="left",
        overlaying="y",
    ),
    yaxis=dict(
        visible=False,
        range=[0, 1],
    ),

    showlegend=False,
    hovermode="x unified",
    
    xaxis=dict(
        title="Lap Number",
        showspikes=True,
        spikemode="across",
        spikethickness=1, 
        spikedash="solid",
        spikecolor="grey", 
        dtick=1,
        range=[0, last_lap_number]
    ),
)


st.plotly_chart(fig, config={'displayModeBar': False})