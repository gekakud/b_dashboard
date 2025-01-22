import streamlit as st
import pandas as pd
import datetime
import pytz

from api import (
    add_participant_to_db, 
    update_participant_to_db,
    post_event_to_db
)
israel_tz = pytz.timezone("Asia/Jerusalem")

def update_participant_form(container):
    ''' This function creates a form that enables updating participant's data
        If the update buttin is pressed it returns True so the display will be updated, otherwise it returns False
    '''
    with st.form("update_participant_form"):
        patientId = st.text_input("Patient ID", key="patientId")
        nickName = st.text_input("Nickname", key="nickName")
        phone = st.text_input("Phone", key="phone")
        empaticaId = st.text_input("Empatica ID", key="empaticaId")
        firebaseId = st.text_input("Firebase ID", key="firebaseId")
        trialStartingDate = st.date_input("Trial Starting Date (Date)", key="trialStartingDate_date-Update")
        trialStartingTime = st.time_input("Trial Starting Time", key="trialStartingDate_time-Update")
        isActive = st.selectbox("Is Active", [True, False], key="isActive")

        submit_button = st.form_submit_button("Submit Update")
        if submit_button:
            if trialStartingDate and trialStartingTime:
                trial_dt = datetime.datetime.combine(trialStartingDate, trialStartingTime)
                trial_dt_aware = israel_tz.localize(trial_dt)
                trialStartingDateTimeStr = trial_dt_aware.isoformat()
            else:
                trialStartingDateTimeStr = None

            updates = {
                "patientId": patientId,
                **({"nickName": nickName} if nickName else {}),
                **({"phone": phone} if phone else {}),
                **({"empaticaId": empaticaId} if empaticaId else {}),
                **({"firebaseId": firebaseId} if firebaseId else {}),
                **({"trialStartingDate": trialStartingDateTimeStr} if trialStartingDateTimeStr else {}),
                **({"isActive": isActive} if isActive is not None else {})
            }
            response = update_participant_to_db(patientId, updates)
            if response.status_code == 200:
                st.success("Participant updated successfully!")
                st.session_state['show_update_participant_form'] = False
                container.empty()
            else:
                st.error(f"Failed to update participant. Status code: {response.status_code}")
            
            # Update button was pressed, tell the display to refresh data
            return True
        else:
            # The button was not pressed, no need to update the display
            return False    
            

def add_participant_form(form_expander):
    with st.form("new_participant_form"):
        nickName = st.text_input("Nickname")
        phone = st.text_input("Phone")
        empaticaId = st.text_input("Empatica ID")
        firebaseId = st.text_input("Firebase ID")
        trialStartingDate = st.date_input("Trial Starting Date (Date)", key="trialStartingDate_date-Add")
        trialStartingTime = st.time_input("Trial Starting Time", key="trialStartingDate_time-Add")

        submit_button = st.form_submit_button("Submit")
        if submit_button:
            if trialStartingDate and trialStartingTime:
                trial_dt = datetime.datetime.combine(trialStartingDate, trialStartingTime)
                # Convert to ISO format with timezone if you want
                trial_dt_aware = israel_tz.localize(trial_dt)  
                trialStartingDateTimeStr = trial_dt_aware.isoformat()
            else:
                trialStartingDateTimeStr = None

            response = add_participant_to_db(nickName, phone, empaticaId, firebaseId, trialStartingDateTimeStr)

            if response.status_code == 201:
                st.success("Participant added successfully!")
                form_expander.empty()
                return True
            else:
                st.error(f"Failed to add participant. Status code: {response.status_code}")
                return False
                            
        else:
            return False
                
                
                
def add_event_form(form_expander, participant_data):
   # participant_data = fetch_participants_data()
    participant_df = pd.DataFrame(participant_data)
    
    with st.form("add_event_form"):
        selected_user = st.selectbox("Select Participant", participant_df['nickName'])
        eventType = st.selectbox("Event Type", ["dissociation", "sadness", "anger", "anxiety", "other" ])   
        activity = st.selectbox("Activity", ["rest", "eating", "exercise", "other"])
        severity = st.slider("Severity", 0, 4, 3)
        eventDate = st.date_input("Event Date (Date)", key="eventDate_date-Add")
        eventTime = st.time_input("Event Time", key="eventDate_time-Add")

        submit_button = st.form_submit_button("Submit")
        if submit_button:
            if eventDate and eventTime:
                # 1) Combine into a naive datetime
                event_dt = datetime.datetime.combine(eventDate, eventTime)
                
                # 2) Localize to Israel time
                israel_tz = pytz.timezone("Asia/Jerusalem")
                event_dt_aware = israel_tz.localize(event_dt)
                
                # 3) Convert to UTC
                event_dt_utc = event_dt_aware.astimezone(pytz.utc)
                
                # 4) Format as 'yyyy-MM-dd HH:mm:ss.SSSZ' with 3 decimal places
                #    e.g. "2025-01-01 15:00:00.123Z"
                #    We'll format microseconds and then slice off to 3 decimals:
#                eventDateTimeStr = event_dt_utc.strftime("%Y-%m-%d %H:%M:%S.%fZ")
                eventDateTimeStr = event_dt_utc.strftime("%Y-%m-%d %H:%M:%S.%f")

            else:
                eventDateTimeStr = None

            st.write(f"Combined Datetime: {eventDateTimeStr}")
            
            lat = 0.0
            long = 0.0            
            selected_participant = participant_df[participant_df['nickName'] == selected_user].iloc[0]
            patientId = selected_participant['patientId']
            deviceId = patientId
            location = {"lat": lat, "long": long}
            origin = "assistant"

            response = post_event_to_db(patientId, deviceId, eventDateTimeStr, location, eventType, activity, severity, origin)
            if response.status_code == 201:
                st.success("Event posted successfully!")
                form_expander.empty()
            else:
                st.error(f"Failed to post event. Status code: {response.status_code}")
