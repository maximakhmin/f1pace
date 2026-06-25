import streamlit as st

BASE_URL = "http://localhost:8000"
MESSAGE_NO_RESULT = "The results for this session have not been uploaded yet"
MESSAGE_NO_LIVE_TIME_DATA = "There is no live-time data now, try again later"

def check_status(response, message="Unknown error, try again later"):
    if response.status_code!=200 or response.json() == []:
        st.warning(message)
        st.stop()



# Настройка конфигурации страницы (вкладка браузера)
st.set_page_config(
    page_title="F1 Telemetry Analytics",
    page_icon="🏎️",
    layout="wide"
)


# 1. Сначала объявляем все страницы через st.Page
# Относительный путь к файлу, название для меню, иконка
page_main = st.Page("main.py", title="Главная", icon="🏎️", default=True)

page_results = st.Page("pages/results.py", title="Результаты сессий", icon="🏁")
page_pace = st.Page("pages/pace.py", title="Аналитика кругов", icon="⏱️")

page_emulation = st.Page("pages/emulation.py", title="Панель управления эмуляцией", icon="🎛️")
page_pace_live = st.Page("pages/pace_real_time.py", title="Аналитика кругов (Live)", icon="📊")
page_map = st.Page("pages/real_time_map.py", title="Карта трассы", icon="🗺️")

# 2. Структурируем страницы по секциям (словарь, где ключ — название секции)
navigation_structure = {
    "": [page_main],  # Главная будет в самом верху без заголовка секции
    "Исторические данные": [
        page_results,
        page_pace
    ],
    "Live данные": [
        page_emulation,
        page_pace_live,
        page_map
    ]
}

# 3. Инициализируем навигацию (Streamlit сам построит sidebar)
selected_page = st.navigation(navigation_structure)

# 4. Настраиваем общие параметры отображения вкладки
st.set_page_config(
    page_title=f"F1 Analytics — {selected_page.title}",
    page_icon=selected_page.icon,
    # layout="wide"
)


if selected_page == page_main:

    # Заголовок главной страницы
    st.title("🏎️ F1 Telemetry & Telemetry Analytics Center")
    st.subheader("Добро пожаловать в систему анализа гоночных данных")

    st.markdown("---")

    # Сетка из двух колонок для описания модулей приложения
    col1, col2 = st.columns(2)

    with col1:
        st.header("📊 Исторические данные")
        st.markdown("""
        Этот блок предназначен для глубокого пост-анализа прошедших гран-при и сессий.
        * **🏁 Результаты сессий:** Итоговые протоколы, позиции, тайминги.
        * **⏱️ Аналитика кругов:** Сравнение темпа пилотов и стратегий.
        """)

    with col2:
        st.header("📡 Live данные & Эмуляция")
        st.markdown("""
        Инструменты для работы с данными в реальном времени (или в режиме воспроизведения гонки).
        * **🎛️ Панель управления:** Запуск, остановка и настройка шагов эмуляции сессии.
        * **🗺️ Карта трассы:** Интерактивный трек с живым отображением позиций гонщиков и сообщений дирекции гонки.
        * **📊 Аналитика кругов (Live):** Динамическое обновление и предсказание графиков темпа прямо по ходу заездов.
        """)

else:
    # Этот метод берет код из выбранного файла (например, pages/results.py) и отрисовывает его
    selected_page.run()


