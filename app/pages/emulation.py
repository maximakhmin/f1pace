import streamlit as st
import requests
import pandas as pd
import time
from main import BASE_URL, check_status

st.set_page_config(
    page_title="F1 Emulation Control Panel", 
    layout="centered",
    initial_sidebar_state="expanded",
)

st.title("🏎️ Панель управления")
st.markdown("---")

# 1. Функция для получения статуса эмуляции с сервера
def get_emulation_status():
    try:
        response = requests.get(f"{BASE_URL}/emulation/status")
        if response.status_code == 200:
            return response.json()
    except requests.exceptions.ConnectionError:
        st.error("Ошибка: Не удалось подключиться к серверу FastAPI. Проверьте, запущен ли он.")
    return {"is_running": False, "current_session_id": None}

# 2. Функция для получения списка доступных сессий
@st.cache_data(ttl=60)  # Кэшируем список сессий на 1 минуту, чтобы не спамить базу
def get_available_sessions():
    try:
        response = requests.get(f"{BASE_URL}/emulation/sessions")
        if response.status_code == 200:
            return response.json()
    except Exception as e:
        st.error(f"Не удалось загрузить список сессий: {e}")
    return []

# Получаем актуальный статус
status_data = get_emulation_status()
is_running = status_data.get("is_running", False)
current_session_id = status_data.get("current_session_id")

# --- СЕКЦИЯ 1: ТЕКУЩИЙ СТАТУС СЕРВЕРА ---
st.subheader("Состояние эмуляции")
col_status, col_id = st.columns(2)

with col_status:
    if is_running:
        st.success("● ЭМУЛЯЦИЯ АКТИВНА")
    else:
        st.info("○ Эмуляция ожидает запуск")

with col_id:
    if is_running and current_session_id:
        st.info(f"ID текущей сессии: {current_session_id}")

st.markdown("---")

# --- СЕКЦИЯ 2: УПРАВЛЕНИЕ ---
st.subheader("Управление эмуляцией")

# Загружаем сессии для отображения в таблице/выборе
sessions_list = get_available_sessions()

if not sessions_list:
    st.warning("В таблице emulated_sessions нет доступных записей.")
else:
    # Превращаем данные в DataFrame для удобного отображения и поиска
    df_sessions = pd.DataFrame(sessions_list)
    
    # Создаем красивое текстовое описание для выпадающего списка
    df_sessions['display_name'] = df_sessions.apply(
        lambda r: f"[{r['id']}] {r['year']}, round {r['round']} - {r['country']}, {r['circuit_name']} ({r['session_type']})", axis=1
    )
    
    # Блокируем элементы управления, если эмуляция уже идет
    selected_session_text = st.selectbox(
        "Выберите сессию для запуска:", 
        options=df_sessions['display_name'].tolist(),
        disabled=is_running
    )
    
    # Вытаскиваем чистый id из выбранной строки
    selected_session_id = int(df_sessions[df_sessions['display_name'] == selected_session_text]['id'].values[0])
    
    # Настройка скорости
    speed = st.slider("Скорость эмуляции (X)", min_value=1.0, max_value=10.0, value=1.0, step=0.5, disabled=is_running)
    
    st.markdown("### Действия")
    col_btn_start, col_btn_stop = st.columns(2)
    
    # Кнопка СТАРТ
    with col_btn_start:
        if st.button("▶ ЗАПУСТИТЬ", type="primary", disabled=is_running, use_container_width=True):
            payload = {"session_id": selected_session_id, "speed": speed}
            try:
                res = requests.post(f"{BASE_URL}/emulation/start", params=payload)
                if res.status_code == 200:
                    st.toast("Сигнал на запуск отправлен!", icon="🚀")
                    time.sleep(1)  # Даем серверу долю секунды обновиться
                    st.rerun()
                else:
                    st.error(f"Ошибка старта: {res.json().get('detail')}")
            except Exception as e:
                st.error(f"Ошибка запроса: {e}")
                
    # Кнопка СТОП
    with col_btn_stop:
        if st.button("⏹ ОСТАНОВИТЬ", type="secondary", disabled=not is_running, use_container_width=True):
            try:
                res = requests.post(f"{BASE_URL}/emulation/stop")
                if res.status_code == 200:
                    st.toast("Эмуляция останавливается...", icon="🛑")
                    time.sleep(1)
                    st.rerun()
                else:
                    st.error("Не удалось остановить эмуляцию.")
            except Exception as e:
                st.error(f"Ошибка запроса: {e}")

    # Показываем таблицу со всеми доступными сессиями внизу для справки
    with st.expander("Посмотреть все доступные для эмуляции сессии"):
        st.dataframe(
            df_sessions[['id', 'year', 'round', 'session_type', 'country', 'circuit_name']], 
            use_container_width=True,
            hide_index=True
        )

# --- АВТООБНОВЛЕНИЕ СТРАНИЦЫ ---
# Если эмуляция активна, заставляем интерфейс обновляться каждую секунду, чтобы видеть актуальный статус
if is_running:
    time.sleep(1.0)
    st.rerun()