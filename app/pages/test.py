import streamlit as st


placeholder = st.empty()

with placeholder.container():
    st.write("Это содержимое контейнера")
    st.button("Нажмите меня")

# Позже где-то в коде
placeholder.empty()