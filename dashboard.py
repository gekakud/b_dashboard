import streamlit as st
import pandas as pd
import numpy as np
import random
from faker import Faker
import requests
from twilio.rest import Client
from private_config import *
import firebase_admin
from firebase_admin import credentials
from firebase_admin import messaging


# Initialize the Firebase Admin SDK
cred_path = '/Users/alongetz/Downloads/booggii-5895-firebase-adminsdk-rnglh-2974cf81b1.json'  
if not firebase_admin._apps:
    cred = credentials.Certificate(cred_path)
    firebase_admin.initialize_app(cred)


# Function to send a push notification
def send_firebase_notification(token, title, body):
    # Create the message
    message = messaging.Message(
        notification=messaging.Notification(
            title=title,
            body=body,
        ),
        token=token,
    )
    # Send the message
    response = messaging.send(message)
    return response

# Cache this function to prevent Streamlit from running it every time the app rerenders.
@st.cache_data
def get_profile_dataset(number_of_items: int = 20):
    """Generates a dataset of fake profiles using the Faker library."""
    Faker.seed(0)  # Ensures consistent results on app reloads
    fake = Faker()  # Create a Faker generator
    data = []
    
    # Generate fake profile data
    for _ in range(number_of_items):
        profile = fake.profile(fields=['name', 'username', 'sex', 'ssn'])
        data.append({
            "Name": profile['name'],
            "Nickname": profile['username'],
            "Gender": profile['sex'],
            "ID": profile['ssn'],
            "Empatica Connected": random.choice([True, False]),
            "Events 24h": np.random.randint(0, 15),
            "Battery Status": round(random.uniform(0, 100), 2),
            "Daily Activity": np.random.randint(0, 2, 24),
        })

    # Create a DataFrame from the generated data
    df = pd.DataFrame(data)
    df["Gender"] = df["Gender"].astype("category")  # Set 'Gender' as a category type for efficient storage
    return df

def send_notification_to_backend(user_nickname, questionnaire_option):
    """Sends a push notification request to a specified backend URL."""
    backend_url = 'https://your-backend-service.com/notifications/send'  # URL of your notification service backend
    payload = {
        'user_nickname': user_nickname,
        'questionnaire_option': questionnaire_option
    }
    try:
        response = requests.post(backend_url, json=payload)  # Send the POST request
        # Handle response
        if response.status_code == 200:
            return True, "Notification sent successfully!"
        else:
            return False, "Failed to send notification."
    except Exception as e:
        return False, str(e)

def fetch_events_data():
    """Fetches questionnaire data from a predefined URL."""
 #   url = "https://virtserver.swaggerhub.com/YoadGidron/Booggii/1.0.2/questionnaire"
 #   url = "https://r4jlflfk41.execute-api.eu-west-1.amazonaws.com/Dev/questionnaire/"
    url = "https://r4jlflfk41.execute-api.eu-west-1.amazonaws.com/Dev/events/"
    try:
        response = requests.get(url)  # Attempt to GET the data
        # Handle response
        if response.ok:
            return response.json()
        else:
            return None
    except Exception:
        return None

def fetch_questionnaire_data():
    """Fetches questionnaire data from a predefined URL."""
 #   url = "https://virtserver.swaggerhub.com/YoadGidron/Booggii/1.0.2/questionnaire"
    url = "https://r4jlflfk41.execute-api.eu-west-1.amazonaws.com/Dev/questionnaire/"
    try:
        response = requests.get(url)  # Attempt to GET the data
        # Handle response
        if response.ok:
            return response.json()
        else:
            return None
    except Exception:
        return None
    
def send_whatsapp_message():
    client = Client(account_sid, auth_token)
    try:
        message = client.messages.create(
            from_='whatsapp:+14155238886',  # Your Twilio WhatsApp number
            body='ניסיון שני',  # Message you want to send
            to='whatsapp:+972545485895'  # Recipient's number
        )
        return True, message.sid
    except Exception as e:
        return False, str(e)


def show_dashboard():
    """Main function to display the Streamlit dashboard."""
    
    st.subheader("Profile Data")
    
    # Configuration for displaying each column in the DataFrame
    column_configuration = {
        # Configure columns with specific attributes for better UI/UX
        "Name": st.column_config.TextColumn("User Name", help="The name of the user", max_chars=50),
        "Nickname": st.column_config.TextColumn("User Nickname", help="The nickname of the user", max_chars=100),
        "Gender": st.column_config.SelectboxColumn("Gender", width="small", options=["male", "female", "other"]),
        "ID": st.column_config.TextColumn("User ID", width="small", help="The id of the user", max_chars=20),
        "Empatica Connected": st.column_config.CheckboxColumn("Empatica connected?", width="small", help="Is the user active?"),
        "Events 24h": st.column_config.NumberColumn("Events (24h)", width="small", min_value=0, max_value=100, format="%d events", help="The user's events for last 24 hours"),
        "Battery Status": st.column_config.ProgressColumn("Battery", width="small", min_value=0, max_value=100, format="%d"),
        "Daily Activity": st.column_config.BarChartColumn(label="Activity(daily)", width=None, help="The user's activity in the last 25 days", y_min=0, y_max=1),
    }
    
    df = get_profile_dataset()
    
    # Display the data editor with custom column configurations
    st.data_editor(
        df,
        column_config=column_configuration,
        hide_index=True,
        num_rows="fixed",
    )
    
    # Fetch and display event data automatically
    event_data = fetch_events_data()
    if event_data:
        events_df = pd.DataFrame(event_data)
        st.subheader("Events Details")
        st.dataframe(events_df)  # Display events data as a DataFrame
    else:
        st.error("Failed to fetch data or no data available.")
        
    # Horizontal line as a divider
    st.markdown("<hr>", unsafe_allow_html=True)
 
    # Use columns to lay out the selectors and button
    col1, col2, col3 = st.columns(3, gap="small")

    with col1:
        # Dropdown for user selection
        user_options = df['Nickname'].tolist()
        selected_user = st.selectbox("Select User for Notification", user_options)

    with col2:
        # Dropdown for questionnaire selection
        questionnaire_options = ["Option 1", "Option 2", "Option 3", "Option 4", "Option 5"]
        selected_questionnaire = st.selectbox("Select Questionnaire Option", questionnaire_options)

    with col3:
        # Custom CSS to adjust the button's vertical position
        st.markdown("""
        <style>
        div.stButton > button {
            margin-top: 12px;  
        }
        </style>
        """, unsafe_allow_html=True)
        # Button to send notification
        if st.button("Send App Notification"):
            # Presuming you have defined `fcm_token` and `send_firebase_notification` somewhere above
            if fcm_token:
                try:
                    title = selected_user  # Set the notification title
                    body = selected_questionnaire  # Set the notification body
                    response = send_firebase_notification(fcm_token, title, body)
                    st.success(f'Firebase Notification sent! Response: {response}')
                except Exception as e:
                    st.error(f'Failed to send Firebase notification. Error: {str(e)}')

    # Horizontal line as a divider
    st.markdown("<hr>", unsafe_allow_html=True)

    # Button and logic to fetch questionnaire data
    # if st.button("Fetch Events Data"):
    #     data = fetch_events_data()
    #     if data:
    #         questionnaire_df = pd.DataFrame(data)
    #         st.subheader("Events Details")
    #         st.dataframe(questionnaire_df)  # Display events data as a DataFrame
    #     else:
    #         st.write("Failed to fetch data or no data available.")
    
    if st.button("Fetch Questionnaire Data"):
        data = fetch_questionnaire_data()
        if data:
            questionnaire_df = pd.DataFrame(data)
            st.subheader("Questionnaire Details")
            st.dataframe(questionnaire_df)  # Display questionnaire data as a DataFrame
        else:
            st.write("Failed to fetch data or no data available.")
        
    # Add functionality to send "Hi" via WhatsApp
    if st.button("Send 'Hi' via WhatsApp"):
        success, response = send_whatsapp_message()
        if success:
            st.success(f"Message sent successfully! Message SID: {response}")
        else:
            st.error(f"Failed to send message. Error: {response}")


if __name__ == "__main__":
    show_dashboard()
