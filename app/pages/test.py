import requests
from main import BASE_URL, check_status
import pandas as pd
import numpy as np
import plotly.graph_objects as go
import streamlit as st
from datetime import datetime as dt
from bokeh.plotting import figure
from bokeh.models import ColumnDataSource
import time
from streamlit_bokeh import streamlit_bokeh
from io import StringIO

st.set_page_config(page_title="F1 Real Time", layout="wide")

response = requests.get("http://localhost:8000/telemetry/track-corners")
corners = pd.read_json(StringIO(response.text))
angle_rad = np.radians(corners["rotation"].mean())


response = requests.get("http://localhost:8000/telemetry/track-map")
map = pd.read_json(StringIO(response.text))

# Матрица поворота
rot_matrix = np.array([
    [np.cos(angle_rad), -np.sin(angle_rad)],
    [np.sin(angle_rad),  np.cos(angle_rad)]
])

# Поворачиваем координаты только для отрисовки
corners[["rot_x", "rot_y"]] = np.dot(corners[['x', 'y']], rot_matrix.T)
map[["rot_x", "rot_y"]] = np.dot(map[['x', 'y']], rot_matrix.T)

padding = 1000  # Размер отступа в единицах графика
x_min, x_max = map["rot_x"].min() - padding, map["rot_x"].max() + padding
y_min, y_max = map["rot_y"].min() - padding, map["rot_y"].max() + padding

R = 350  # Дистанция выноса текста от трассы (подберите под масштаб)
radians = np.radians(corners['angle']) + angle_rad # Переводим градусы в радианы

# Считаем новые координаты ИМЕННО ДЛЯ ТЕКСТА
corners['text_x'] = corners['rot_x'] + R * np.cos(radians)
corners['text_y'] = corners['rot_y'] + R * np.sin(radians)


col1, gap, col2 = st.columns([10, 1, 10])
with col1:
    placeholder1 = st.empty()
with col2:
    placeholder2 = st.empty()


@st.fragment(run_every=1) 
def render_live_position():
    # 1. Инициализируем хранилище для последней удачной отрисовки
    if 'f1_last_fig' not in st.session_state:
        st.session_state.f1_last_fig = None
    if 'f1_last_time' not in st.session_state:
        st.session_state.f1_last_time = None

    data_updated = False

    try:
        # 2. Добавляем жесткий timeout (например, 0.2 секунды). 
        # Если сервер тупит, вылетит ошибка, и мы перейдем к отрисовке старого графика.
        response = requests.get(BASE_URL + "/telemetry/current-live-timestamp", timeout=0.2)
        check_status(response)
        current_time = dt.fromisoformat(response.json()["time"])

        response_pos = requests.get(BASE_URL + "/telemetry/positions", timeout=0.2)
        check_status(response_pos)
        positions = pd.read_json(StringIO(response_pos.text))
        
        data_updated = True

    except Exception:
        # Если не успели получить данные (таймаут или ошибка сервера), 
        # просто игнорируем. data_updated останется False.
        pass

    # 3. Строим новую фигуру ТОЛЬКО если получили свежие данные
    if data_updated:
        # Матричное умножение делаем ровно ОДИН раз (в исходном коде было дважды)
        rotated_pilots = np.dot(positions[['x', 'y']], rot_matrix.T)
        positions['rot_x'] = rotated_pilots[:, 0]
        positions['rot_y'] = rotated_pilots[:, 1]

        fig = go.Figure()

        # Отрисовка трассы
        fig.add_trace(go.Scatter(
            x=map['rot_x'], 
            y=map['rot_y'],
            mode='lines',
            line=dict(color="#4d4d4d", width=6),
        ))

        # Отрисовка номеров поворотов
        fig.add_trace(go.Scatter(
            x=corners['text_x'], y=corners['text_y'],
            mode='text',
            text=corners['number'],
            textfont=dict(size=12, color='#4d4d4d', family='Arial Black'),
            showlegend=False
        ))

        # Отрисовка маркеров пилотов
        fig.add_trace(go.Scatter(
            x=positions['rot_x'], 
            y=positions['rot_y'],
            mode='markers',
            marker=dict(
                size=15,
                color=positions['color'],
                line=dict(width=2, color='white')
            ),
            hoverinfo='skip'
        ))

        # Аннотации с аббревиатурами пилотов
        annotations = []
        for idx, row in positions.iterrows():
            annotations.append(
                dict(
                    x=row['rot_x'],
                    y=row['rot_y'],
                    text=row['abbr'],
                    showarrow=True,
                    arrowhead=0,
                    arrowsize=1,
                    arrowwidth=1,
                    arrowcolor='gray',
                    ax=15,
                    ay=-25,
                    font=dict(size=12, color='white', family='Arial Black'),
                    bgcolor='#4d4d4d',
                    bordercolor='white',
                    borderwidth=1,
                    borderpad=4,
                )
            )

        fig.update_layout(
            annotations=annotations,
            xaxis=dict(
                scaleanchor="y", 
                scaleratio=1, 
                constrain='domain',
                range=[x_min, x_max],
                visible=False
            ),
            yaxis=dict(
                constrain='domain',
                range=[y_min, y_max],
                visible=False 
            ),
            showlegend=False,
            hovermode=False,
            margin=dict(l=0, r=0, t=0, b=0), 
            transition={'duration': 0}, # Отключаем внутренние анимации Plotly
        )

        # Сохраняем удачный график в кэш
        st.session_state.f1_last_fig = fig
        st.session_state.f1_last_time = current_time

    # 4. Отрисовка в UI
    # ВАЖНО: Мы больше не используем `with placeholder1.container():`
    # Фрагмент сам обновляет свою область.
    with placeholder1.container():
        if st.session_state.f1_last_fig is not None:
            st.title(dt.strftime(st.session_state.f1_last_time, "%H:%M:%S"))
            st.title("Карта в реальном времени")
            st.plotly_chart(
                st.session_state.f1_last_fig, 
                use_container_width=True, # Более надежный способ задать ширину в современном Streamlit
                key="f1_live_track",             
                config={
                    'staticPlot': True,
                    'displayModeBar': False
                }
            )


@st.fragment(run_every=5)
def render_live_messages():
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


    with placeholder2.container():
        st.title("")
        st.title("Сообщения дирекции гонки")
        with st.container(height=400):
            st.table(messages[["time", "lap", "message"]])
        # st.dataframe(messages[["time", "lap", "message"]], height=400, use_container_width=True)


# Запуск слоя телеметрии
render_live_position()
render_live_messages()