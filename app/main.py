import streamlit as st

BASE_URL = "http://localhost:8000"
MESSAGE_NO_RESULT = "The results for this session have not been uploaded yet"
MESSAGE_NO_LIVE_TIME_DATA = "There is no live-time data now, try again later"

def check_status(response, message="Unknown error, try again later"):
    if response.status_code!=200:
        st.write(message)
        st.stop()