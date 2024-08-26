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
    message = messaging.Message(
        notification=messaging.Notification(
            title=title,
            body=body,
        ),
        data=data,
        token=token,
    )
    response = messaging.send(message)
    return response

def fetch_events_data():
    url = f"{BASE_URL}/events/"
    try:
        response = requests.get(url)
        if response.ok:
            return response.json()
        else:
            return None
    except Exception:
        return None

def fetch_questionnaire_data():
    url = f"{BASE_URL}/questionnaire/"
    try:
        response = requests.get(url)
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
        active_participants = [p for p in participants_data if p.get('is_active', False)]
        for entry in active_participants:
            entry['created_at'] = entry.pop('createdAt', entry.get('created_at', ''))
            entry['updated_at'] = entry.pop('updatedAt', entry.get('updated_at', ''))
            entry['empatica_status'] = entry.pop('empaticaStatus', entry.get('empatica_status', ''))
            entry['num_of_events_current_date'] = entry.pop('numOfEventsCurrentDate', entry.get('num_of_events_current_date', ''))
            entry['is_active'] = entry.pop('isActive', entry.get('is_active', ''))
            entry.pop('createdAt', None)
            entry.pop('updatedAt', None)
            entry.pop('isActive', None)
            entry.pop('numOfEventsCurrentDate', None)
            entry.pop('empaticaStatusß', None)
        return active_participants
    except Exception as e:
        return None

def highlight_old_updates(row):
    threshold_hours = 10
    current_time = pd.Timestamp.now()
    empatica_last_update = pd.to_datetime(row['empatica_last_update'], errors='coerce')
    if pd.notnull(empatica_last_update):
        time_diff = current_time - empatica_last_update
        if time_diff.total_seconds() > threshold_hours * 3600:
            return ['background-color: yellow'] * len(row)
    return [''] * len(row)

def refresh_and_display_participants(placeholder):
    participant_data = fetch_participants_data()
    event_data = fetch_events_data()

    if participant_data and event_data:
        participant_df = pd.DataFrame(participant_data)
        event_df = pd.DataFrame(event_data)
        event_counts = event_df.groupby('patientId').size().reset_index(name='num_of_events')
        participant_df = pd.merge(participant_df, event_counts, how='left', left_on='patientId', right_on='patientId')
        participant_df['num_of_events'].fillna(0, inplace=True)
        participant_df['num_of_events'] = participant_df['num_of_events'].astype(int)
        column_order = (
            ['nickName', 'empatica_status', 'empatica_last_update', 'num_of_events'] + 
            [col for col in participant_df.columns if col not in ['nickName', 'empatica_status', 'empatica_last_update', 'num_of_events', 'num_of_events_current_date']] + 
            ['num_of_events_current_date']
        )
        participant_df = participant_df[column_order]
        styled_df = participant_df.style.apply(highlight_old_updates, axis=1)
        placeholder.dataframe(styled_df, use_container_width=True, hide_index=True)
    else:
        st.error("Failed to fetch participants or events data.")

def show_participants_data():
    participant_data = fetch_participants_data()
    if participant_data:
        participant_df = pd.DataFrame(participant_data)
        column_order = [
            'nickName',
            'phone',
            'patientId',
            'empatica_status',
            'created_at',
            'empaticaId'
        ]
        participant_df = participant_df[column_order]
        st.subheader("Participants Data")
        st.dataframe(participant_df, use_container_width=True, hide_index=True)
    else:
        st.error("Failed to fetch participants data.")

def transform_questionnaire_data(questionnaire_data):
    df = pd.DataFrame(questionnaire_data)
    df.rename(columns={'num': 'מס שאלה', 'type': 'סוג', 'question': 'השאלה'}, inplace=True)
    days_of_week = {1: 'Sunday', 2: 'Monday', 3: 'Tuesday', 
                    4: 'Wednesday', 5: 'Thursday', 6: 'Friday', 7: 'Saturday'}
    hours = ['10:00', '14:00', '18:00']
    timetable = pd.DataFrame(index=hours, columns=days_of_week.values())
    timetable = timetable.fillna('')
    for index, row in df.iterrows():
        question_number = row['מס שאלה']
        for day in row['days']:
            day_name = days_of_week.get(day)
            for hour in row['hours']:
                hour_str = f'{hour}:00'
                cell_value = timetable.at[hour_str, day_name]
                if str(question_number) not in cell_value.split(', '):
                    if cell_value == '':
                        timetable.at[hour_str, day_name] = str(question_number)
                    else:
                        timetable.at[hour_str, day_name] += f', {question_number}'
    df = df[['סוג', 'השאלה', 'מס שאלה']]
    return df, timetable

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

def add_participant_form(form_expander, placeholder):
    with st.form("new_participant_form"):
        nickName = st.text_input("Nickname")
        phone = st.text_input("Phone")
        empaticaId = st.text_input("Empatica ID")
        firebaseId = st.text_input("Firebase ID")
        submit_button = st.form_submit_button("Submit")

        if submit_button:
            response = add_participant_to_db(nickName, phone, empaticaId, submit_button)
            if response.status_code == 201:
                st.success("Participant added successfully!")
                form_expander.empty()
                refresh_and_display_participants(placeholder)
            else:
                st.error(f"Failed to add participant. Status code: {response.status_code}")

def update_participant_form(container, placeholder):
    with st.form("update_participant_form"):
        patientId = st.text_input("Patient ID", key="patientId")
        nickName = st.text_input("Nickname", key="nickName")
        phone = st.text_input("Phone", key="phone")
        empaticaId = st.text_input("Empatica ID", key="empaticaId")
        firebaseId = st.text_input("Firebase ID", key="firebaseId")
        isActive = st.selectbox("Is Active", [True, False], key="isActive")
        submit_button = st.form_submit_button("Submit Update")

        if submit_button:
            updates = {
                "patientId": patientId,
                **({"nickName": nickName} if nickName else {}),
                **({"phone": phone} if phone else {}),
                **({"empaticaId": empaticaId} if empaticaId else {}),
                **({"firebaseId": firebaseId} if firebaseId else {}),
                **({"isActive": isActive} if isActive is not None else {})
            }
            response = update_participant_to_db(patientId, updates)
            if response.status_code == 200:
                st.success("Participant updated successfully!")
                st.session_state['show_update_participant_form'] = False
                container.empty()
                refresh_and_display_participants(placeholder)
            else:
                st.error(f"Failed to update participant. Status code: {response.status_code}")

def get_questions(patient_id):
    url = f"{BASE_URL}/questions?patientId={patient_id}"
    response = requests.get(url)
    if response.status_code == 200:
        return response.json()
    else:
        st.error("Failed to retrieve questions.")
        return None

def show_questions(patient_id, questionnaire_df):
    questions_data = get_questions(patient_id)
    if questions_data and questionnaire_df is not None:
        sorted_questions = sorted(questions_data, key=lambda x: x['timestamp'], reverse=True)
        timestamps = []
        question_texts = []
        answers = []
        for question in sorted_questions:
            question_num = question.get('questionNum')
            question_text = questionnaire_df.loc[questionnaire_df['מס שאלה'] == question_num, 'השאלה'].iloc[0]
            answer = question.get('answer', 'No answer provided')
            timestamp = question.get('timestamp', 'No timestamp provided')
            formatted_timestamp = pd.to_datetime(timestamp).strftime('%Y-%m-%d %H:%M:%S')
            timestamps.append(formatted_timestamp)
            question_texts.append(question_text)
            answers.append(answer)

        questions_df = pd.DataFrame({
            'Timestamp': timestamps,
            'Question': question_texts,
            'Answer': answers
        })
        questions_html = questions_df.to_html(index=False, escape=False, justify='right')
        st.markdown(f"<div style='direction: rtl; text-align: right;'>{questions_html}</div>", unsafe_allow_html=True)
        csv = questions_df.to_csv(index=False).encode('utf-8-sig')
        file_name = f"questions_{patient_id}.csv"
        st.download_button(label="Download Questions as CSV", data=csv, file_name=file_name, mime='text/csv')
    else:
        st.error("Failed to retrieve questions or questionnaire data.")

def show_dashboard():
    st.subheader("Participants Data")
    show_participants_data()
    
    st.subheader("Participants Status")
    participants_placeholder = st.empty()
    refresh_and_display_participants(participants_placeholder)
    
    with st.expander("Add New Participant"):
        add_participant_form(st, participants_placeholder)
    
    with st.expander("Update Participant"):
        update_participant_form(st, participants_placeholder)

    st.markdown("<hr>", unsafe_allow_html=True)

    st.subheader("Events Data")
    events_placeholder = st.empty()

    def display_events_data():
        event_data = fetch_events_data()
        participant_data = fetch_participants_data()
        if event_data and participant_data:
            participant_df = pd.DataFrame(participant_data)
            events_df = pd.DataFrame(event_data)
            events_df['timestamp'] = pd.to_datetime(events_df['timestamp'])
            merged_df = pd.merge(events_df, participant_df[['patientId', 'nickName']], on='patientId', how='left')
            if 'deviceId' in merged_df.columns:
                merged_df.drop(columns=['deviceId'], inplace=True)
            reordered_columns = ['timestamp', 'nickName', 'severity', 'eventType', 'activity', 'patientId', 'location']
            merged_df = merged_df[reordered_columns]
            events_df_sorted = merged_df.sort_values(by='timestamp', ascending=False)
            events_placeholder.dataframe(events_df_sorted, use_container_width=True, hide_index=True)
        else:
            events_placeholder.error("Failed to fetch data or no data available.")

    if st.button('Refresh Events'):
        st.cache_data.clear()

    display_events_data()

    st.markdown("<hr>", unsafe_allow_html=True)

    st.subheader("Push Notification")
    col1, col2, col3 = st.columns(3, gap="small")

    with col1:
        participant_data = fetch_participants_data()
        if participant_data:
            participant_df = pd.DataFrame(participant_data)
            user_options = participant_df['nickName'].tolist()
            selected_user = st.selectbox("Select User for Notification", user_options)
        else:
            st.error("Failed to fetch participants data.")
        
    with col2:
        questionnaire_options = ["נא למלא שאלון אירוע", "נא לוודא חיבור שעון", "נא לוודא שעון על היד"]
        selected_questionnaire = st.selectbox("Select Questionnaire Option", questionnaire_options)

    with col3:
        st.markdown("""
        <style>
        div.stButton > button {
            margin-top: 12px;  
        }
        </style>
        """, unsafe_allow_html=True)
        
        custom_data = {
            "Nick": "Mario",
            "Room": "PortugalVSDenmark"
        }

        if st.button("Send App Notification"):
            try:
                selected_participant = participant_df[participant_df['nickName'] == selected_user].iloc[0]
                fcm_token = selected_participant['firebaseId']
                title = selected_user
                body = selected_questionnaire
                response = send_firebase_notification(fcm_token, title, body, data=custom_data)
                st.success(f'Firebase Notification sent! Response: {response}')
            except Exception as e:
                st.error(f'Failed to send Firebase notification. Error: {str(e)}')
  
    st.markdown("<hr>", unsafe_allow_html=True)

    questionnaire_data = fetch_questionnaire_data()
    if questionnaire_data:
        questionnaire_df, timetable_df = transform_questionnaire_data(questionnaire_data)
        st.subheader("Questionnaire Details")
        st.dataframe(questionnaire_df, hide_index=True)
        st.subheader("Questionnaire Timetable")
        st.dataframe(timetable_df)
    else:
        st.error("Failed to fetch questionnaire data or no data available.")
        
    st.subheader("Retrieve Questions")
    user_options2 = participant_df['nickName'].tolist()
    selected_user2 = st.selectbox("Select User for retrieving questions", user_options2)
    
    if st.button("Get User's Questions"):
        try:
            selected_partici = participant_df[participant_df['nickName'] == selected_user2].iloc[0]
            patient_id = selected_partici['patientId']
            if patient_id and questionnaire_df is not None:
                show_questions(patient_id, questionnaire_df)
                st.success(f'Questions from user arrived!')
        
        except Exception as e:
            st.error(f'Failed to get questions from user. Error: {str(e)}')

if __name__ == "__main__":
    show_dashboard()
