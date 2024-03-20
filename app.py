import streamlit as st

# The very first command in the script:
st.set_page_config(page_title="Login Page", page_icon="🔑")

from streamlit_authenticator import Authenticate
import yaml
from yaml.loader import SafeLoader

# Assuming dashboard.show_dashboard does not call st.set_page_config itself
from dashboard import show_dashboard

# Continue with the rest of your script after setting the page config
with open('config.yaml') as file:
    config = yaml.load(file, Loader=SafeLoader)

authenticator = Authenticate(
    config['credentials'],
    config['cookie']['name'],
    config['cookie']['key'],
    config['cookie']['expiry_days'],
    config['preauthorized']
)

name, authentication_status, username = authenticator.login('main')

if authentication_status:
    st.success(f'Welcome {name}!')
    show_dashboard()
elif authentication_status == False:
    st.error('Username/password is incorrect')
elif authentication_status == None:
    st.warning('Please enter your username and password')
