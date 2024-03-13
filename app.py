import streamlit as st
from streamlit_authenticator import Authenticate
from dashboard import *

# Access secrets. # Use the secrets, e.g., to connect to a database
db_user = st.secrets["database"]["user"]
db_password = st.secrets["database"]["password"]


import yaml
from yaml.loader import SafeLoader
with open('config.yaml') as file:
    config = yaml.load(file, Loader=SafeLoader)

authenticator = Authenticate(
    config['credentials'],
    config['cookie']['name'],
    config['cookie']['key'],
    config['cookie']['expiry_days'],
    config['preauthorized']
)

# Display login form and authenticate user
name, authentication_status, username = authenticator.login('main')

if authentication_status:
    st.write(f'Welcome *{name}*!')
    # Your app's main functionality goes here
    if st.button("Fetch Questionnaire Data"):
        data = fetch_questionnaire_data()
        if data:
            st.subheader("Questionnaire Details")
            st.json(data)  # Display JSON data in a clear format

    # Logout button
    if st.button('Logout'):
        authenticator.logout('main')
        st.write('You have been logged out.')

elif authentication_status == False:
    st.error('Username/password is incorrect')

elif authentication_status == None:
    st.warning('Please enter your username and password')
