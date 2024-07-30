import streamlit as st
import pandas as pd
import numpy as np
import random
import requests
from twilio.rest import Client
from private_config import *
import firebase_admin
from firebase_admin import credentials
from firebase_admin import messaging
from api import fetch_participants
from api import update_participant_to_db



# Initialize the Firebase Admin SDK
if not firebase_admin._apps:
    cred = credentials.Certificate(FIREBASE_CRED_PATH)
    firebase_admin.initialize_app(cred)


def send_firebase_notification(token, title, body, data=None):
    # Create the message with an optional data payload
    message = messaging.Message(
        notification=messaging.Notification(
            title=title,
            body=body,
        ),
        data=data,  # Add custom data payload to the message
        token=token,
    )
    # Send the message
    response = messaging.send(message)
    return response

"""Fetches events data from a predefined URL."""
def fetch_events_data():
    url = f"{BASE_URL}/events/"

    try:
        response = requests.get(url)  # Attempt to GET the data
        # Handle response
        if response.ok:
            return response.json()
        else:
            return None
    except Exception:
        return None

"""Fetches questionnaire data from a predefined URL."""
def fetch_questionnaire_data():
    url = f"{BASE_URL}/questionnaire/"

    try:
        response = requests.get(url)  # Attempt to GET the data
        # Handle response
        if response.ok:
            return response.json()
        else:
            return None
    except Exception:
        return None

def fetch_participants_data():
    url = f"{BASE_URL}/participants/"
  
    try:
        participants_data = fetch_participants()

        response = requests.get(url)
        active_participants = [p for p in participants_data if p.get('is_active', False) == True]  # Filter only active participants

        # Normalize the column names here, for example:
        for entry in active_participants:
            # Normalize datetime columns to one format
            entry['created_at'] = entry.pop('createdAt', entry.get('created_at', ''))
            entry['updated_at'] = entry.pop('updatedAt', entry.get('updated_at', ''))
            entry['empatica_status'] = entry.pop('empaticaStatus', entry.get('empatica_status', ''))
            entry['num_of_events_current_date'] = entry.pop('numOfEventsCurrentDate', entry.get('num_of_events_current_date', ''))
            # Normalize boolean columns to one format
            entry['is_active'] = entry.pop('isActive', entry.get('is_active', ''))
            # Remove the camelCase keys if they exist
            entry.pop('createdAt', None)
            entry.pop('updatedAt', None)
            entry.pop('isActive', None)
            entry.pop('numOfEventsCurrentDate', None)
            entry.pop('empaticaStatusß', None)
        return active_participants
    except Exception as e:
        return None
    
    
# Function to refresh and display participant data
def refresh_and_display_participants(placeholder):
    participant_data = fetch_participants_data()
    if participant_data:
        # Convert the participant data to a pandas DataFrame
        participant_df = pd.DataFrame(participant_data)
        # Reorder the columns to make nickName the first column
        column_order = ['nickName'] + [col for col in participant_df.columns if col != 'nickName']
        participant_df = participant_df[column_order]
        # Use the original placeholder or expander to display the new dataframe
        placeholder.dataframe(participant_df, use_container_width=True, hide_index=True)

    else:
        st.error("Failed to fetch participants data.")
        


"""Transforms the questionnaire data to the desired format and creates a timetable."""
def transform_questionnaire_data(questionnaire_data):
    # Convert to DataFrame
    df = pd.DataFrame(questionnaire_data)
    
    # Map 'num' to 'Question Number' and 'type' to 'Type'
    df.rename(columns={'num': 'מס שאלה', 'type': 'סוג', 'question': 'השאלה'}, inplace=True)
    
    # 'days' are 1 (Sunday) to 7 (Saturday)
    days_of_week = {1: 'Sunday', 2: 'Monday', 3: 'Tuesday', 
                    4: 'Wednesday', 5: 'Thursday', 6: 'Friday', 7: 'Saturday'}
    
    # Define hours and format them with ':00'
    hours = ['10:00', '14:00', '18:00']
    
    # Create the timetable DataFrame with slots for each day and formatted hour
    timetable = pd.DataFrame(index=hours, columns=days_of_week.values())
    timetable = timetable.fillna('')  # Initialize cells with empty string

    # Populate the timetable with question numbers based on 'days' and 'hours' lists
    for index, row in df.iterrows():
        question_number = row['מס שאלה']
        for day in row['days']:
            day_name = days_of_week.get(day)
            for hour in row['hours']:
                hour_str = f'{hour}:00'  # Format hour as string with minutes
                cell_value = timetable.at[hour_str, day_name]
                if str(question_number) not in cell_value.split(', '):
                    if cell_value == '':
                        timetable.at[hour_str, day_name] = str(question_number)
                    else:
                        timetable.at[hour_str, day_name] += f', {question_number}'

    # Select only the columns we need for the final display
    df = df[['סוג', 'השאלה', 'מס שאלה']]

    return df, timetable


# Function to post data to the API endpoint
def add_participant_to_db(nickName, phone, empaticaId, firebaseId):
    url = f"{BASE_URL}/participants/"

    
    payload = {
        "nickName": nickName,
        "phone": phone,
        "empaticaId": empaticaId,
        "firebaseId": firebaseId
    }
    headers = {
        'Content-Type': 'application/json'
    }
    response = requests.post(url, json=payload, headers=headers)
    return response



def add_participant_form(form_expander,placeholder):
    with st.form("new_participant_form"):
        nickName = st.text_input("Nickname")
        phone = st.text_input("Phone")
        empaticaId = st.text_input("Empatica ID")
        firebaseId = st.text_input("Firebase ID")
        submit_button = st.form_submit_button("Submit")

        if submit_button:
            # Make the POST request here with the form data
            response = add_participant_to_db(nickName, phone, empaticaId, submit_button)

            if response.status_code == 201:
                st.success("Participant added successfully!")
                # This line will hide the expander/form after submission
                form_expander.empty()
                refresh_and_display_participants(placeholder)  # Refresh the participant data

            else:
                st.error(f"Failed to add participant. Status code: {response.status_code}")


def update_participant_form(container, placeholder):
    with st.form("update_participant_form"):
        patientId = st.text_input("Patient ID", key="patientId")
        nickName = st.text_input("Nickname", key="nickName")
        phone = st.text_input("Phone", key="phone")
        empaticaId = st.text_input("Empatica ID", key="empaticaId")
        firebaseId = st.text_input("Firebase ID", key="firebaseId")
#        empaticaStatus = st.selectbox("Empatica Status", [True, False], key="empaticaStatus")
        isActive = st.selectbox("Is Active", [True, False], key="isActive")
        submit_button = st.form_submit_button("Submit Update")

        if submit_button:
            updates = {
                "patientId": patientId,  # patientId must be sent for identification
                **({"nickName": nickName} if nickName else {}),
                **({"phone": phone} if phone else {}),
                **({"empaticaId": empaticaId} if empaticaId else {}),
                **({"firebaseId": firebaseId} if firebaseId else {}),
 #               **({"empaticaStatus": empaticaStatus} if empaticaStatus is not None else {}),
                **({"isActive": isActive} if isActive is not None else {})
            }

            response = update_participant_to_db(patientId, updates)
            if response.status_code == 200:
                st.success("Participant updated successfully!")
                st.session_state['show_update_participant_form'] = False
                container.empty()
                refresh_and_display_participants(placeholder)  # Refresh the participant data
            else:
                st.error(f"Failed to update participant. Status code: {response.status_code}")

def get_questions(patient_id):
    # Construct the URL with the patientId as a query parameter
    url = f"{BASE_URL}/questions?patientId={patient_id}"
    
    # Make the GET request to the API
    response = requests.get(url)
    
    # Check if the request was successful
    if response.status_code == 200:
        # Parse the response JSON
        questions_data = response.json()
        return questions_data
    else:
        st.error("Failed to retrieve questions.")
        return None

def show_questions(patient_id, questionnaire_df):
    # Retrieve questions for the given patientId
    questions_data = get_questions(patient_id)

    if questions_data and questionnaire_df is not None:
        # Sort questions by timestamp in descending order
        sorted_questions = sorted(questions_data, key=lambda x: x['timestamp'], reverse=True)

        # Prepare lists to store our data
        timestamps = []
        question_texts = []
        answers = []

        # Populate the lists with sorted data
        for question in sorted_questions:
            question_id = question.get('questionId')
            question_num = question.get('questionNum')
            question_text = questionnaire_df.loc[questionnaire_df['מס שאלה'] == question_num, 'השאלה'].iloc[0]
            answer = question.get('answer', 'No answer provided')
            timestamp = question.get('timestamp', 'No timestamp provided')

            # Format timestamp to remove milliseconds
            formatted_timestamp = pd.to_datetime(timestamp).strftime('%Y-%m-%d %H:%M:%S')
            timestamps.append(formatted_timestamp)
            question_texts.append(question_text)
            answers.append(answer)

        # Create a DataFrame with the collected data
        questions_df = pd.DataFrame({
            'Timestamp': timestamps,
            'Question': question_texts,
            'Answer': answers
        })

        # Convert DataFrame to HTML and use style to align text to the right
        questions_html = questions_df.to_html(index=False, escape=False, justify='right')

        # Use Markdown to display the HTML DataFrame, adjusting CSS for right alignment
        st.markdown(f"<div style='direction: rtl; text-align: right;'>{questions_html}</div>", unsafe_allow_html=True)

        # Convert DataFrame to CSV for download
        csv = questions_df.to_csv(index=False).encode('utf-8-sig')
        file_name = f"questions_{patient_id}.csv"  # Dynamically set the filename with patientId

        st.download_button(
            label="Download Questions as CSV",
            data=csv,
            file_name=file_name,
            mime='text/csv',
        )
    else:
        st.error("Failed to retrieve questions or questionnaire data.")

def show_dashboard():
    """Main function to display the Streamlit dashboard."""
    st.subheader("Participants Data")
    participants_placeholder = st.empty()
    
    # Fetch and display real participant data from the API
    refresh_and_display_participants(participants_placeholder)
    
    # Expander for adding new participant
    with st.expander("Add New Participant"):
        add_participant_form(st, participants_placeholder)
    
    # Expander for updating participant
    with st.expander("Update Participant"):
        update_participant_form(st, participants_placeholder)



    # Horizontal line as a divider
    st.markdown("<hr>", unsafe_allow_html=True)

    st.subheader("Events Data")

   # At the beginning of your show_dashboard() function, add a placeholder
    events_placeholder = st.empty()

    # Function to display the events data
    def display_events_data():
        event_data = fetch_events_data()
        if event_data:
            events_df = pd.DataFrame(event_data)
            events_df['timestamp'] = pd.to_datetime(events_df['timestamp'])
            events_df_sorted = events_df.sort_values(by='timestamp', ascending=False)
            # Use the placeholder to display the DataFrame
            events_placeholder.dataframe(events_df_sorted, use_container_width=True, hide_index=True)
        else:
            events_placeholder.error("Failed to fetch data or no data available.")

    # Button to refresh event data
    if st.button('Refresh Events'):
        st.cache_data.clear()  # Clear the memoized cache

    display_events_data()

        
    # Horizontal line as a divider
    st.markdown("<hr>", unsafe_allow_html=True)
    
    st.subheader("Push Notification")
 
    # Use columns to lay out the selectors and button
    col1, col2, col3 = st.columns(3, gap="small")

    with col1:
        # Dropdown for user selection
        participant_data = fetch_participants_data()
        if participant_data:
        # Convert the participant data to a pandas DataFrame
            participant_df = pd.DataFrame(participant_data)
            user_options = participant_df['nickName'].tolist()
            selected_user = st.selectbox("Select User for Notification", user_options)
        else:
            st.error("Failed to fetch participants data.")
        

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
        
        custom_data = {
            "Nick" : "Mario",
            "Room" : "PortugalVSDenmark"
            # ... additional key-value pairs
        }

        # Button to send notification
        if st.button("Send App Notification"):
            try:
                # Fetch the firebaseId for the selected user
                selected_participant = participant_df[participant_df['nickName'] == selected_user].iloc[0]
                fcm_token = selected_participant['firebaseId']  # Assuming the column name in the df is 'firebaseId'

                title = selected_user  # Set the notification title
                body = selected_questionnaire  # Set the notification body
                response = send_firebase_notification(fcm_token, title, body, data=custom_data)
                st.success(f'Firebase Notification sent! Response: {response}')
            except Exception as e:
                st.error(f'Failed to send Firebase notification. Error: {str(e)}')
  
    # Horizontal line as a divider
    st.markdown("<hr>", unsafe_allow_html=True)

    # Automatically fetch and display questionnaire data
    questionnaire_data = fetch_questionnaire_data()
    if questionnaire_data:
        # Transform and display questionnaire data
        questionnaire_df, timetable_df = transform_questionnaire_data(questionnaire_data)
        
        st.subheader("Questionnaire Details")
                
        # Ensure that we reset the index before displaying and not include it in the DataFrame
        st.dataframe(questionnaire_df, hide_index=True)

        st.subheader("Questionnaire Timetable")
        st.dataframe(timetable_df)  # Display timetable
        
    else:
        st.error("Failed to fetch questionnaire data or no data available.")
        
    # Add text input and button to get questions
    st.subheader("Retrieve Questions")
#    patient_id_input = st.text_input("Enter Patient ID to retrieve questions:")
    
    user_options2 = participant_df['nickName'].tolist()
    selected_user2 = st.selectbox("Select User for retrieving questions", user_options2)
    
    if st.button("Get User's Questions"):
        try:
            # Fetch the firebaseId for the selected user
            selected_partici = participant_df[participant_df['nickName'] == selected_user2].iloc[0]
            patient_id = selected_partici['patientId'] 
            if patient_id and questionnaire_df is not None:
                show_questions(patient_id, questionnaire_df)
                st.success(f'Questions from user arrived!')
        
        except Exception as e:
            st.error(f'Failed to get questions from user. Error: {str(e)}')
            
    
    #if st.button('Get Questions'):
    #    if patient_id_input and questionnaire_df is not None:
    #        show_questions(patient_id_input, questionnaire_df)
    #    else:
    #        st.error("Please enter a valid Patient ID and ensure questionnaire data is loaded.")

if __name__ == "__main__":
    show_dashboard()
