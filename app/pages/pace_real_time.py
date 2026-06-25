import pandas as pd
import numpy as np
import streamlit as st
import plotly.graph_objects as go
from plotly.subplots import make_subplots
import requests
from main import BASE_URL, check_status, MESSAGE_NO_RESULT, MESSAGE_NO_LIVE_TIME_DATA
from io import StringIO
from datetime import datetime as dt
from streamlit_autorefresh import st_autorefresh

response = requests.get(BASE_URL+"/info/track-statuses")
check_status(response)
statuses_info = pd.read_json(StringIO(response.text))
statuses_info = dict(zip(statuses_info["id"].values, zip(statuses_info["name"].values, statuses_info["color"].values)))

response = requests.get(BASE_URL+"/info/tyres")
check_status(response)
tyres_info = pd.read_json(StringIO(response.text))
tyres_info = dict(zip(tyres_info["id"].values, zip(tyres_info["name"].values, tyres_info["color"].values)))

def hex_to_rgba(hex_color, opacity=1.0):
    """
    Преобразует HEX (#RRGGBB) в rgba(R, G, B, A).
    """
    hex_color = hex_color.lstrip('#')
    # Переводим HEX в целые числа (int)
    r, g, b = tuple(int(hex_color[i:i+2], 16) for i in (0, 2, 4))
    return f"rgba({r}, {g}, {b}, {opacity})"


def calculate_deltas(laps_1, laps_2, over_zero=False):
    if min(len(laps_1), len(laps_2)) == 0:
        return [1], [0]
    
    laps_number = []
    deltas = []
    deltas_prev=None
    for i in range(min(len(laps_1), len(laps_2))):
        laps_number.append(int(laps_1.loc[i, "lap_number"]))
        if deltas_prev:
            lap_1_time = laps_1.loc[i, "lap_time"]
            lap_2_time = laps_2.loc[i, "lap_time"]
            new_delta = deltas_prev + lap_2_time - lap_1_time
            deltas.append(new_delta)
            deltas_prev = new_delta
        else:
            lap_1_time = dt.fromisoformat(laps_1.loc[i, "end_time_utc"])
            lap_2_time = dt.fromisoformat(laps_2.loc[i, "end_time_utc"])
            new_delta = (lap_2_time - lap_1_time).total_seconds()
            deltas.append(new_delta)
            deltas_prev = new_delta

    if not over_zero:
        return laps_number, deltas
    
    deltas_x = [laps_number[0]]
    deltas_y = [deltas[0]]
    negative = (deltas[0] < 0)
    for i in range(1, len(deltas)):
        new_lap = laps_number[i]
        old_lap = deltas_x[-1]
        new_delta = deltas[i]
        old_delta = deltas_y[-1]
        new_negative = (deltas[i] < 0)
        if negative == new_negative:
            deltas_x.append(new_lap)
            deltas_y.append(new_delta)
        else:
            # x_zero = x1 - y1 * (x2 - x1) / (y2 - y1)
            deltas_x.append(old_lap - old_delta * (new_lap - old_lap) / (new_delta - old_delta))
            deltas_y.append(0)

            deltas_x.append(new_lap)
            deltas_y.append(new_delta)

            negative = new_negative

    return deltas_x, deltas_y

def convert_time(t):
    if not pd.isna(t):
        return f"{int(t) // 60}:{t % 60:06.3f}"
    else:
        return ""
    
def driver_select_format_func(x):
    if x==0:
        return "Clear"
    color = styles[styles['driver_number'] == x]['color'].values[0]
    abbr = styles[styles['driver_number'] == x]['abbr'].values[0]
    return f":color[▍]{{foreground='{color}'}}**{abbr}**"

st.set_page_config(layout="wide")
st.title("🏎️ Сравнение времен круга в реальном времени")
fig = make_subplots(specs=[[{"secondary_y": True}]])

response = requests.get(f"{BASE_URL}/emulation/status")
check_status(response)
session_id = response.json()["current_session_id"]

response = requests.get(f"{BASE_URL}/live/laps")
check_status(response, MESSAGE_NO_LIVE_TIME_DATA)
laps = pd.read_json(StringIO(response.text))

if laps.empty:
    st.warning("There is no live data now")
    st.stop()


last_lap_number = laps["lap_number"].max()

response = requests.get(f"{BASE_URL}/historical/styles/{session_id}")
check_status(response, MESSAGE_NO_RESULT)
styles = pd.read_json(StringIO(response.text))


# ---------------------------- select driver ----------------------------

all_drivers = [0] + list(styles['driver_number'].unique())

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


# ---------------------------- lap times ----------------------------
added_colors = []

for i in range(len(selected_drivers)):
    driver_number = selected_drivers[i]
    data = laps[(laps["driver_number"] == driver_number)].copy()
    if data.empty:
        continue

    driver_abbr = styles[styles['driver_number'] == driver_number]['abbr'].values[0]
    driver_color = styles[styles["driver_number"] == driver_number]["color"].values[0]

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

    actual_data = data[~data["is_predicted_future"]]
    predicted_data = data[data["is_predicted_future"]]

    if not predicted_data.empty and not actual_data.empty:
        # Берем последнюю реальную точку
        last_actual_row = actual_data.tail(1).copy()

        # Секрет: обнуляем текст подсказки (customdata) для этой точки в треке предсказаний
        # Чтобы при наведении на неё Plotly там ничего не показывал
        last_actual_row["formatted"] = ""
        predicted_data["formatted"] = "[predicted] " + predicted_data["formatted"]

        # Соединяем
        predicted_data = pd.concat([last_actual_row, predicted_data])
        


    # 2. Добавляем линию для РЕАЛЬНЫХ данных (основная, жирная)
    fig.add_trace(
        go.Scatter(
            x=actual_data["lap_number"],
            y=actual_data["lap_time"],
            name="Lap Time (Actual)",
            mode="lines",
            line=dict(color=driver_color, width=3, dash=driver_linestyle),
            marker=dict(
                symbol=driver_marker, size=8, line=dict(width=1, color="black")
            ),
            customdata=actual_data["formatted"],
            hovertemplate="%{customdata}<extra></extra>",
            yaxis="y2",
        ),
    )

    # 3. Добавляем линию для ПРЕДСКАЗАНИЙ (более тонкая, например, width=1.5)
    if not predicted_data.empty:
        fig.add_trace(
            go.Scatter(
                x=predicted_data["lap_number"],
                y=predicted_data["lap_time"],
                name="Lap Time (Predicted)",
                mode="lines",
                # Изменяем width на 1.5. Также можно заменить dash на 'dot' или 'dash', если хочется пунктир
                line=dict(color=driver_color, width=1.5, dash="dot"),
                marker=dict(
                    symbol=driver_marker, size=6, line=dict(width=1, color="black")
                ),
                customdata=predicted_data["formatted"],
                hovertemplate="%{customdata}<extra></extra>",
                yaxis="y2",
                # Скрываем дублирующую легенду, если нужно, чтобы они управлялись вместе
                showlegend=True,
            ),
        )

    data_tyres = data.groupby("stint_number").first()
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
            yaxis='y2',
            hoverinfo='skip',
        ),
    )

# ---------------------------- detla ----------------------------
if len(selected_drivers)==2:
    laps_1 = laps[laps["driver_number"] == selected_drivers[0]].reset_index()
    laps_2 = laps[laps["driver_number"] == selected_drivers[1]].reset_index()
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
            yaxis='y',      
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
            yaxis='y',   
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
            yaxis='y',  
        ),
    )
    

    fig.update_layout(
        yaxis=dict(
            title="Delta",
            side="right",
            range=[-axis_limit, axis_limit],
            zeroline=True,
            zerolinewidth=2,
            zerolinecolor='grey',
            showgrid=False,
        ),
        annotations=[
            dict(
                x=0.95,            
                y=1.1,        
                xref="paper",
                yref="paper",
                text=f"{styles[styles['driver_number'] == selected_drivers[0]]['abbr'].values[0]} ahead",
                showarrow=False,
                font=dict(size=12, color="grey"), 
                xanchor="left"
            ),
            dict(
                x=0.95,            
                y=-0.1,        
                xref="paper",
                yref="paper",
                text=f"{styles[styles['driver_number'] == selected_drivers[1]]['abbr'].values[0]} ahead",
                showarrow=False,
                font=dict(size=12, color="grey"), 
                xanchor="left"
            ),
        ]
    )


# ---------------------------- axis ----------------------------
fig.update_layout(

    yaxis2=dict(
        title="Lap time",
        overlaying="y",
        side="left",
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

count = st_autorefresh(interval=60000, key="datarefresh")
st.plotly_chart(fig, config={'displayModeBar': False})