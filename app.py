import streamlit as st

# Access secrets
db_user = st.secrets["database"]["user"]
db_password = st.secrets["database"]["password"]

# Use the secrets, e.g., to connect to a database
