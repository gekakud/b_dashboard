import streamlit as st
import yaml
from yaml.loader import SafeLoader

from streamlit_authenticator import Authenticate

# Your custom module that shows the main dashboard
from dashboard import show_dashboard

# 1) Set the page to wide
st.set_page_config(
    page_title="Booggii",
    page_icon="/Users/alongetz/Library/CloudStorage/GoogleDrive-alon.getz@gmail.com/My Drive/GTS/Rafael-PTSD/ptsd-icon.png",
    layout="wide"
)

# 2) Load config for Streamlit Authenticator
with open('config.yaml') as file:
    config = yaml.load(file, Loader=SafeLoader)

authenticator = Authenticate(
    config['credentials'],
    config['cookie']['name'],
    config['cookie']['key'],
    config['cookie']['expiry_days'],
    config['preauthorized']
)

# 3) We place the login form in a narrower column,
#    but the overall page is still wide.
if 'authentication_status' not in st.session_state:
    st.session_state['authentication_status'] = None

if st.session_state['authentication_status'] != True:
    # Create three columns: left spacer, center content, right spacer
    col_left, col_center, col_right = st.columns([3, 2, 3])

    with col_center:
#        st.image("/Users/alongetz/Library/CloudStorage/GoogleDrive-alon.getz@gmail.com/My Drive/GTS/Rafael-PTSD/ptsd-icon.png", width=80)
        st.title("Login")

        # Authenticator login returns (name, authentication_status, username)
        name, authentication_status, username = authenticator.login("main")

        if authentication_status == False:
            st.error('Username/password is incorrect')
        elif authentication_status is None:
            st.warning('Please enter your username and password')
        else:
            # If authentication_status == True, store it in session_state
            st.session_state['authentication_status'] = True
            st.session_state['name'] = name
            st.experimental_rerun()  # Reload the page so we skip this block next time

# 4) If user is logged in, show the dashboard
if st.session_state.get('authentication_status', False) == True:
    st.success(f'Welcome {st.session_state["name"]}!')
    show_dashboard()
