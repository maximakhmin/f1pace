import requests
from main import BASE_URL, check_status
import pandas as pd
import numpy as np
import plotly.graph_objects as go
import streamlit as st
from scipy.interpolate import Akima1DInterpolator
from datetime import datetime as dt
from bokeh.plotting import figure
from bokeh.models import ColumnDataSource
import time
from streamlit_bokeh import streamlit_bokeh
from io import StringIO

st.set_page_config(page_title="F1 Real Time", layout="wide")

response = requests.get(BASE_URL+"/telemetry/track-corners")
check_status(response)
corners = pd.read_json(StringIO(response.text))

angle_rad = np.radians(corners["rotation"].mean())
# Матрица поворота
rot_matrix = np.array([
    [np.cos(angle_rad), -np.sin(angle_rad)],
    [np.sin(angle_rad),  np.cos(angle_rad)]
])
# Поворачиваем координаты только для отрисовки
rotated_coords = np.dot(corners[['x', 'y']], rot_matrix.T)

data = {
    'x': rotated_coords[:, 0],
    'y': rotated_coords[:, 1]
}
df = pd.DataFrame(data)

df_extended = pd.concat([
    df.iloc[-2:], # Конец трассы добавляем в начало
    df, 
    df.iloc[:2]   # Начало трассы добавляем в конец
], ignore_index=True)

# Считаем кумулятивное расстояние для расширенного набора
dx = df_extended['x'].diff().fillna(0)
dy = df_extended['y'].diff().fillna(0)
distances = np.sqrt(dx**2 + dy**2)
t_extended = np.cumsum(distances).values

# 2. Обычный Akima1DInterpolator, но на расширенных данных
interp_x = Akima1DInterpolator(t_extended, df_extended['x'].values)
interp_y = Akima1DInterpolator(t_extended, df_extended['y'].values)

# Генерируем точки ИМЕННО для участка основной трассы (пропуская «виртуальные» хвосты)
# Основная трасса теперь лежит между индексами 2 и len(df)+2
start_t = t_extended[2]
end_t = t_extended[2 + len(df)]

t_smooth = np.linspace(start_t, end_t, 1000)
x_smooth = interp_x(t_smooth)
y_smooth = interp_y(t_smooth)

padding = 100  # Размер отступа в единицах графика
x_min, x_max = x_smooth.min() - padding, x_smooth.max() + padding
y_min, y_max = y_smooth.min() - padding, y_smooth.max() + padding


col1, gap, col2 = st.columns([10, 1, 10])


@st.fragment(run_every=1)
def render_live_position(container):
    container.empty()
    response = requests.get(BASE_URL + "/telemetry/current-live-timestamp")
    check_status(response)
    current_time = dt.fromisoformat(response.json()["time"])


    response = requests.get(BASE_URL + "/telemetry/positions")
    check_status(response)
    positions = pd.read_json(StringIO(response.text))

    rotated_pilots = np.dot(positions[['x', 'y']], rot_matrix.T)
    positions['rot_x'] = rotated_pilots[:, 0]
    positions['rot_y'] = rotated_pilots[:, 1]

    # Настраиваем холст Bokeh
    p = figure(height=600, match_aspect=True, toolbar_location=None)
    p.axis.visible = False
    p.grid.grid_line_color = None

    # Отрисовка трассы
    p.line(x_smooth, y_smooth, line_color="gray", line_width=4)
    p.line(data['x'], data['y'], line_color='red')

    # Данные пилотов
    source = ColumnDataSource(data=dict(
        x=positions['rot_x'], 
        y=positions['rot_y'], 
        name=positions['abbr'], 
        color=positions['color']
    ))

    p.scatter('x', 'y', size=15, color='color', source=source)
    p.text('x', 'y', text='name', text_baseline="bottom", text_align="center", y_offset=10, source=source)

    with container:
        
        st.title(dt.strftime(current_time, "%H:%M:%S"))
        st.title("Карта в реальном времени")
        streamlit_bokeh(p, use_container_width=True, key="f1_live_track")



@st.fragment(run_every=5)
def render_live_messages(container):
    container.empty()

    response = requests.get(BASE_URL+"/telemetry/messages")
    check_status(response)
    messages = pd.read_json(response.text)
    if messages.empty:
        return
    messages["time_utc"] = pd.to_datetime(messages["time_utc"])

    messages["time"] = messages["time_utc"].apply(lambda x : dt.strftime(x, "%H:%M:%S"))

    # Вызываем плагин вместо встроенной функции.
    # Передаем use_container_width=True и фиксированный key, чтобы Streamlit
    # не пытался переинициализировать ассеты компонента на каждом тике.


    with container:
        st.title("Сообщения дирекции гонки")
        with st.container(height=400):
            st.table(messages[["time", "lap", "message"]])
        # st.dataframe(messages[["time", "lap", "message"]], height=400, use_container_width=True)


# Запуск слоя телеметрии
render_live_position(col1)
render_live_messages(col2)