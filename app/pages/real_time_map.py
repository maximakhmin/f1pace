import requests
from main import BASE_URL, check_status, MESSAGE_NO_LIVE_TIME_DATA
import pandas as pd
import numpy as np
import streamlit as st
from datetime import datetime as dt
from io import StringIO
import pydeck as pdk # Импортируем PyDeck


# Вспомогательная функция для конвертации HEX в RGB (PyDeck использует RGB 0-255)
def hex_to_rgb(hex_str):
    if not hex_str or not isinstance(hex_str, str):
        return [255, 255, 255] # Default white
    hex_str = hex_str.lstrip('#')
    return [int(hex_str[i:i+2], 16) for i in (0, 2, 4)]


st.set_page_config(page_title="F1 Real Time", layout="wide")
col1, gap, col2 = st.columns([14, 1, 10])
with col1:
    placeholder1 = st.empty()
with col2:
    placeholder2 = st.empty()


response = requests.get(f"{BASE_URL}/live/track-corners")
check_status(response, MESSAGE_NO_LIVE_TIME_DATA)
corners = pd.read_json(StringIO(response.text))
angle_rad = np.radians(corners["rotation"].mean())


response = requests.get(f"{BASE_URL}/live/track-map")
check_status(response, MESSAGE_NO_LIVE_TIME_DATA)
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


max_track_val = max(map['rot_x'].abs().max(), map['rot_y'].abs().max())

TARGET_DEGREE = 0.05 
COORD_SCALE = max_track_val / TARGET_DEGREE
MAP_CENTER_X = map['rot_x'].mean() / COORD_SCALE
MAP_CENTER_Y = map['rot_y'].mean() / COORD_SCALE
MAP_ZOOM = 12.9      

bg_layer = pdk.Layer(
    "PolygonLayer",
    data=[{"polygon": [[-5, 5], [5, 5], [5, -5], [-5, -5]]}],
    get_polygon="polygon",
    get_fill_color=[255, 255, 255], # Идеально белый цвет
    filled=True,
    stroked=False,
    pickable=False
)

# Масштабируем саму трассу
track_coords = (map[['rot_x', 'rot_y']] / COORD_SCALE).values.tolist()

track_layer = pdk.Layer(
    "PathLayer",
    data=[{"path": track_coords}],
    get_path="path",
    get_color=[77, 77, 77],
    width_min_pixels=8,
    pickable=False
)


# Оптимизированный интервал для PyDeck
@st.fragment(run_every=0.25) 
def render_live_position_pydeck():
    # Инициализация кэша состояний
    if 'f1_last_positions_df' not in st.session_state:
        st.session_state.f1_last_positions_df = None
    if 'f1_last_time' not in st.session_state:
        st.session_state.f1_last_time = None

    new_data = None
    current_time_str = "--:--:--"

    try:
        response = requests.get(BASE_URL + "/live/current-live-timestamp", timeout=0.2)
        check_status(response, MESSAGE_NO_LIVE_TIME_DATA)
        current_time_str = dt.fromisoformat(response.json()["time"]).strftime("%H:%M:%S")

        response_pos = requests.get(BASE_URL + "/live/positions", timeout=0.2)
        check_status(response, MESSAGE_NO_LIVE_TIME_DATA)
        new_data = pd.read_json(StringIO(response_pos.text))
    except Exception:
        if st.session_state.f1_last_time:
            current_time_str = st.session_state.f1_last_time

    if new_data is not None:
        # Поворот координат пилотов
        rotated_pilots = np.dot(new_data[['x', 'y']], rot_matrix.T)
        new_data['rot_x'] = rotated_pilots[:, 0]
        new_data['rot_y'] = rotated_pilots[:, 1]

        # Динамическое масштабирование координат пилотов
        new_data['scaled_x'] = new_data['rot_x'] / COORD_SCALE
        new_data['scaled_y'] = new_data['rot_y'] / COORD_SCALE
        new_data['coordinates'] = new_data.apply(lambda r: [r['scaled_x'], r['scaled_y']], axis=1)
        
        new_data['color_rgb'] = new_data['color'].apply(hex_to_rgb)
        
        # КРИТИЧЕСКИ ДЛЯ TEXTLAYER: принудительно делаем строки и убираем NaN
        new_data['abbr'] = new_data['abbr'].astype(str).fillna('?')

        st.session_state.f1_last_positions_df = new_data
        st.session_state.f1_last_time = current_time_str
    
    if st.session_state.f1_last_positions_df is None:
        st.warning("Ожидание данных телеметрии...")
        return

    positions_df = st.session_state.f1_last_positions_df

    car_layer = pdk.Layer(
        "ScatterplotLayer",
        data=positions_df,
        get_position="coordinates",
        get_color="color_rgb",
        radius_min_pixels=7,
        radius_max_pixels=7,
        stroked=True,
        get_line_color=[255, 255, 255],
        line_width_min_pixels=1,
        pickable=False
    )

    text_layer = pdk.Layer(
        "TextLayer",
        data=positions_df,
        get_position="coordinates",
        get_text="abbr",               # Имя колонки со строками
        get_color=[0, 0, 0],           # Белый цвет букв
        get_size=16,                   # Стандартный размер шрифта
        size_min_pixels=16,            # Запрещаем уменьшаться при зуме
        size_max_pixels=16,            # Запрещаем увеличиваться
        get_pixel_offset=[12, -12],    # Сдвиг в пикселях: вправо (12) и вверх (-12) от точки
        billboard=True,                # Текст всегда повернут лицом к экрану
        get_outline_color=[0, 0, 0, 255], # Черная обводка (RGBA) вокруг букв для читаемости
        get_outline_width=2
    )
    with placeholder1.container():

        st.title(st.session_state.f1_last_time)
        st.title("Карта в реальном времени")

        custom_static_view = pdk.View(type="MapView", controller=False)

        view_state = pdk.ViewState(
            longitude=MAP_CENTER_X, 
            latitude=MAP_CENTER_Y,  
            zoom=MAP_ZOOM,
            min_zoom=MAP_ZOOM,   # Карта физически не сможет стать ближе
            max_zoom=MAP_ZOOM,
            pitch=0, 
            bearing=0
        )
        st.markdown(
            """
            <style>
            /* 1. Запрещаем любые клики и перетаскивания мыши */
            [data-testid="stElementContainer"] {
                pointer-events: none;
            }
            
            /* 2. Полностью скрываем кнопки "+" и "-" и любые другие панели управления */
            [data-testid="stElementContainer"] button {
                display: none !important;
            }
            
            /* Дополнительная страховка на случай, если кнопки внедрены через встроенные стили Mapbox/DeckGL */
            .mapboxgl-ctrl, .deck-controller, .styles_controlsContainer__2Z_gX {
                display: none !important;
            }
            </style>
            """,
            unsafe_allow_html=True
        )
        st.pydeck_chart(pdk.Deck(
            # views=[custom_static_view],
            initial_view_state=view_state,
            layers=[bg_layer, track_layer, car_layer, text_layer],
            tooltip=False
        ))

@st.fragment(run_every=5)
def render_live_messages():
    response = requests.get(BASE_URL+"/live/messages")
    check_status(response, MESSAGE_NO_LIVE_TIME_DATA)
    messages = pd.read_json(StringIO(response.text))
    if messages.empty:
        return
    messages["time_utc"] = pd.to_datetime(messages["time_utc"])

    messages["time"] = messages["time_utc"].apply(lambda x : dt.strftime(x, "%H:%M:%S"))

    # Вызываем плагин вместо встроенной функции.
    # Передаем use_container_width=True и фиксированный key, чтобы Streamlit
    # не пытался переинициализировать ассеты компонента на каждом тике.


    with placeholder2.container():
        st.title("")
        st.title("Сообщения дирекции")
        with st.container(height=400):
            st.table(messages[["time", "lap", "message"]])
        # st.dataframe(messages[["time", "lap", "message"]], height=400, use_container_width=True)


# Запуск слоя телеметрии
render_live_position_pydeck()
render_live_messages()