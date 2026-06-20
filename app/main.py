import streamlit as st

BASE_URL = "http://localhost:8000"

def check_status(response):
    if response.status_code!=200:
        st.write("The results for this session have not been uploaded yet")
        st.stop()