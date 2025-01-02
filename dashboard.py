import streamlit as st
import pandas as pd
import numpy as np
import requests
from private_config import *
import firebase_admin
from firebase_admin import credentials
from firebase_admin import messaging
import re
import datetime


from api import (
    fetch_participants, 
    fetch_questionnaire_data, 
    fetch_events_data,
    update_participant_to_db,
    get_questions, 
    add_participant_to_db, 
    post_event_to_db
)
import datetime
import pytz

# ----------------------------
# GLOBALS
# ----------------------------
status_placeholder = None
participants_placeholder = None

# Set a global timezone for the entire app
israel_tz = pytz.timezone('Asia/Jerusalem')

# Initialize the Firebase Admin SDK
if not firebase_admin._apps:
    cred = credentials.Certificate(FIREBASE_CRED_PATH)
    firebase_admin.initialize_app(cred)

def send_firebase_notification(token, title, body, data=None):
    message = messaging.Message(
        notification=messaging.Notification(title=title, body=body),
        data=data,
        token=token,
    )
    response = messaging.send(message)
    return response

# ----------------------------
# FETCH + PROCESS PARTICIPANTS
# ----------------------------
def fetch_participants_data():
    participant_data = fetch_participants()
    if participant_data:
        for entry in participant_data:
            # Rename fields to unify naming
            entry['created_at'] = entry.pop('createdAt', entry.get('created_at', ''))
            entry['updated_at'] = entry.pop('updatedAt', entry.get('updated_at', ''))
            entry['trial_starting_date'] = entry.get('trialStartingDate', '')  # Adding trialStartingDate
            entry['empatica_status'] = entry.pop('empaticaStatus', entry.get('empatica_status', ''))
            entry['num_of_events_current_date'] = entry.pop('numOfEventsCurrentDate', entry.get('num_of_events_current_date', ''))
            entry['is_active'] = entry.pop('isActive', entry.get('is_active', ''))
        return participant_data
    else:
        return None

# ----------------------------
# STYLING & FORMATTING
# ----------------------------
def highlight_old_updates(row):
    """
    Highlights rows where Empatica hasn't updated for > threshold_hours hours
    """
    threshold_hours = 10
    current_time = pd.Timestamp.now(tz=israel_tz)
    empatica_last_update = pd.to_datetime(row['empatica_last_update'], errors='coerce')
    # Force to tz-aware if not already
    if empatica_last_update is not None and empatica_last_update.tz is None:
#        empatica_last_update = empatica_last_update.tz_localize(israel_tz, nonexistent='shift_forward', ambiguous='NaT')
        empatica_last_update = empatica_last_update.tz_localize(israel_tz)
    if pd.notnull(empatica_last_update):
        time_diff = current_time - empatica_last_update
        if time_diff.total_seconds() > threshold_hours * 3600:
            return ['background-color: yellow'] * len(row)
    return [''] * len(row)

def format_timestamp_without_subseconds(timestamp):
    """
    Convert a timestamp to ISO8601 (no microseconds).
    """
    if pd.notnull(timestamp):
        return pd.to_datetime(timestamp).strftime('%Y-%m-%dT%H:%M:%S')
    else:
        return "N/A"

# ----------------------------
# SHOW PARTICIPANTS DATA
# ----------------------------
def refresh_and_display_participants(placeholder):
    participant_data = fetch_participants_data()
    event_data = fetch_events_data()

    if participant_data and event_data:
        participant_df = pd.DataFrame(participant_data)
        event_df = pd.DataFrame(event_data)

        # Merge the total events count
        event_counts = event_df.groupby('patientId').size().reset_index(name='num_of_events')
        participant_df = pd.merge(participant_df, event_counts, how='left', left_on='patientId', right_on='patientId')
        participant_df['num_of_events'].fillna(0, inplace=True)
        participant_df['num_of_events'] = participant_df['num_of_events'].astype(int)

        column_order = (
            ['nickName', 'empatica_status', 'empatica_last_update', 'num_of_events'] + 
            [col for col in participant_df.columns 
                if col not in ['nickName', 'empatica_status', 'empatica_last_update', 'num_of_events', 'num_of_events_current_date']
            ] + ['num_of_events_current_date']
        )
        participant_df = participant_df[column_order]

        styled_df = participant_df.style.apply(highlight_old_updates, axis=1)
        placeholder.dataframe(styled_df, use_container_width=True, hide_index=True)
    else:
        st.error("Failed to fetch participants or events data.")

def show_participants_data():
    global participants_placeholder
    participant_data = fetch_participants()
    event_data = fetch_events_data()

    if participant_data:
        participant_df = pd.DataFrame(participant_data)

        # Format columns
        participant_df['created_at'] = participant_df['created_at'].apply(format_timestamp_without_subseconds)
        participant_df['trial_starting_date'] = participant_df['trial_starting_date'].apply(format_timestamp_without_subseconds)

        participant_df['Events total'] = calculate_num_events(event_data, participant_df, days=None)

        column_order = [
            'nickName',
            'phone',
            'patientId',
            'empaticaStatus',
            'created_at',
            'trial_starting_date',
            'empaticaId',
            'firebaseId',
            'Events total',
            'isActive'
        ]
        participant_df = participant_df[column_order]

        participants_placeholder.dataframe(participant_df, use_container_width=True, hide_index=True)
    else:
        st.error("Failed to fetch participants data.")

# ----------------------------
# QUESTIONNAIRE TIMETABLE
# ----------------------------
def transform_questionnaire_data(questionnaire_data):
    df = pd.DataFrame(questionnaire_data)
    df.rename(columns={'num': 'מס שאלה', 'type': 'סוג', 'question': 'השאלה'}, inplace=True)
    days_of_week = {
        1: 'Sunday', 2: 'Monday', 3: 'Tuesday', 
        4: 'Wednesday', 5: 'Thursday', 6: 'Friday', 7: 'Saturday'
    }
    hours = ['10:00', '14:00', '18:00']
    timetable = pd.DataFrame(index=hours, columns=days_of_week.values()).fillna('')

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

def calculate_percentage_of_nan_questions_last_x_hrs(questions_data, timetable_df, current_time, hrs):
    """
    % of unanswered questions in the last `hrs` hours, tz-aware.
    """
    if isinstance(questions_data, list):
        questions_data = pd.DataFrame(questions_data)

    if 'timestamp' not in questions_data.columns:
        raise ValueError("The 'timestamp' column is missing from questions_data.")

    # 1. total scheduled
    #total_scheduled = calculate_scheduled_questions_last_X_hours(timetable_df, current_time, hrs)
    end_date = current_time
    start_date = end_date - pd.Timedelta(hours=hrs)

    total_scheduled = calculate_displayed_questions(timetable_df, start_date, end_date)


    # 2. convert question timestamps -> tz-aware
    questions_data['timestamp'] = pd.to_datetime(questions_data['timestamp'], errors='coerce')
    # localize as Israel
    questions_data['timestamp'] = questions_data['timestamp'].dt.tz_localize(israel_tz)

    # 3. window for answered questions
    answered_questions = questions_data[
        (questions_data['timestamp'] >= start_date) &
        (questions_data['timestamp'] < end_date)
    ]

    answered_count = len(answered_questions)
    unanswered_count = total_scheduled - answered_count
    if total_scheduled > 0:
        unanswered_percentage = (unanswered_count / total_scheduled) * 100
    else:
        unanswered_percentage = 0.0

    return unanswered_percentage

def calculate_num_events(event_data, participant_df, days=None):
    """
    Return a Series with event counts for each participant, tz-aware approach.
    """
    if isinstance(event_data, list):
        event_data = pd.DataFrame(event_data)

    if 'timestamp' not in event_data.columns:
        raise ValueError("The 'timestamp' column is missing from event_data.")

    # Convert events to tz-aware
    event_data['timestamp'] = pd.to_datetime(event_data['timestamp'], errors='coerce')
   # event_data['timestamp'] = event_data['timestamp'].dt.tz_localize(israel_tz, nonexistent='shift_forward', ambiguous='NaT')
    event_data['timestamp'] = event_data['timestamp'].dt.tz_localize(israel_tz)

    if days is not None:
        cutoff_time = pd.Timestamp.now(tz=israel_tz) - pd.Timedelta(days=days)
        event_data = event_data[event_data['timestamp'] >= cutoff_time]

    grouped = event_data.groupby('patientId')['timestamp'].agg(['min','max','count'])
    grouped['days'] = (grouped['max'] - grouped['min']).dt.days + 1
    grouped['days'] = grouped['days'].replace(0, 1)

    # We'll store the raw count in 'average_daily_events'
    grouped['average_daily_events'] = grouped['count']

    participant_df = participant_df.set_index('patientId').join(grouped[['average_daily_events']]).reset_index()
    participant_df['average_daily_events'].fillna(0, inplace=True)

    return participant_df['average_daily_events']

def calculate_time_since_last_connection(empatica_last_update):
    """
    Returns hours since last connection, tz-aware.
    """
    if pd.isna(empatica_last_update):
        return float('nan')

    if empatica_last_update.tz is None:
        # localize it if you stored it as naive
  #      empatica_last_update = empatica_last_update.tz_localize(israel_tz, nonexistent='shift_forward', ambiguous='NaT')
        empatica_last_update = empatica_last_update.tz_localize(israel_tz)

    current_time = pd.Timestamp.now(tz=israel_tz)
    time_diff = current_time - empatica_last_update
    return time_diff.total_seconds() / 3600

def format_time_since_update(hours):
    if pd.isna(hours):
        return "N/A"
    if hours < 24:
        return f"{hours:.1f} Hrs"
    else:
        days = int(hours // 24)
        remaining_hours = hours % 24
        return f"{days} days, {remaining_hours:.1f} Hrs"

# ----------------------------
# PERCENTAGE NAN (TRIAL RANGE)
# ----------------------------
def calculate_percentage_of_nan_questions(questions_data, timetable_df, start_date, end_date):
    """
    % of unanswered within a date range [start_date, end_date], tz-aware.
    """
    df = pd.DataFrame(questions_data)
    if df.empty:
        return 100.0

    # Convert to tz-aware
    df['timestamp'] = pd.to_datetime(df['timestamp'], errors='coerce')
    df['timestamp'] = df['timestamp'].dt.tz_localize(israel_tz)



    # Convert the start_date / end_date to tz-aware if naive
    start_date = pd.to_datetime(start_date, errors='coerce')
    if start_date is not None and start_date.tzinfo is None:
        start_date = israel_tz.localize(start_date)

    end_date = pd.to_datetime(end_date, errors='coerce')
    if end_date is not None and end_date.tzinfo is None:
        end_date = israel_tz.localize(end_date)

    if pd.isna(start_date) or pd.isna(end_date):
        return 100.0  # if we can't parse the dates, fallback

    df_filtered = df[(df['timestamp'] >= start_date) & (df['timestamp'] <= end_date)]

    # Convert answers to numeric
    df_filtered['answer'] = pd.to_numeric(df_filtered['answer'], errors='coerce')
    valid_answers_count = df_filtered['answer'].between(0, 4, inclusive='both').sum()

    # How many were scheduled in that date range?
    total_questions_displayed = calculate_displayed_questions(timetable_df, start_date, end_date)

    if total_questions_displayed == 0:
        return 100.0

    unanswered_percentage = 100.0 * (1 - (valid_answers_count / total_questions_displayed))
    return int(round(unanswered_percentage))

def calculate_displayed_questions(timetable_df, start_date, end_date):
    """
    How many questions were scheduled from start_date to end_date, tz-aware.
    """
    start_date = start_date.tz_convert("Asia/Jerusalem")
    end_date = end_date.tz_convert("Asia/Jerusalem")
    # Ensure tz-aware
    if start_date.tzinfo is None:
        start_date = israel_tz.localize(start_date)
    if end_date.tzinfo is None:
        end_date = israel_tz.localize(end_date)
    if end_date < start_date:
        end_date = start_date + pd.Timedelta(hours=36)

    total_questions_displayed = 0
    # If start_date and end_date are both tz-aware in Asia/Jerusalem:
    date_range = pd.date_range(
        start=start_date, 
        end=end_date,
        freq='D'
    )
    # No tz parameter needed; Pandas takes the timezone from start/end.
    days_of_week_map = {0: 'Monday', 1: 'Tuesday', 2: 'Wednesday', 3: 'Thursday',
                        4: 'Friday', 5: 'Saturday', 6: 'Sunday'}

    for current_day in date_range:
        day_of_week = current_day.strftime('%A')  # e.g. 'Monday'
        if day_of_week in timetable_df.columns:
            for time in timetable_df.index:
                question_set = timetable_df.at[time, day_of_week]
                if question_set:
                    # Build a dt for this date+time
                    question_time_str = f"{current_day.strftime('%Y-%m-%d')} {time}"
    #                question_time = pd.to_datetime(question_time_str, errors='coerce').tz_localize(israel_tz, ambiguous='NaT', nonexistent='shift_forward')
                    question_time = pd.to_datetime(question_time_str, errors='coerce').tz_localize(israel_tz)
                    # Now skip if outside the actual [start_date, end_date] range
                    if question_time < start_date:
                        continue
                    if question_time > end_date:
                        continue
                    question_list = question_set.split(', ')
                    total_questions_displayed += len(question_list)

    return total_questions_displayed

def compute_valid_answers_count(questions_data, start_date, end_date):
    """
    Number of valid answers (0-4) in [start_date, end_date], tz-aware.
    """
    df = pd.DataFrame(questions_data)
    if df.empty:
        return 0

    df['timestamp'] = pd.to_datetime(df['timestamp'], errors='coerce')
#   df['timestamp'] = df['timestamp'].dt.tz_localize(israel_tz, nonexistent='shift_forward', ambiguous='NaT')
    df['timestamp'] = df['timestamp'].dt.tz_localize(israel_tz)
 

    # localize start/end if needed
    start_date = pd.to_datetime(start_date, errors='coerce')
    if start_date is not None and start_date.tzinfo is None:
        start_date = israel_tz.localize(start_date)

    end_date = pd.to_datetime(end_date, errors='coerce')
    if end_date is not None and end_date.tzinfo is None:
        end_date = israel_tz.localize(end_date)

    df_filtered = df[(df['timestamp'] >= start_date) & (df['timestamp'] <= end_date)]
    df_filtered['answer'] = pd.to_numeric(df_filtered['answer'], errors='coerce')
    valid_answers_count = df_filtered['answer'].between(0, 4, inclusive='both').sum()
    return int(valid_answers_count)

# ----------------------------
# FETCH & SHOW PARTICIPANTS STATUS
# ----------------------------
def fetch_participants_status(participant_data, event_data):
    """
    Builds a DataFrame of participants' status, including:
      - Time since last Empatica update
      - % unanswered last 36 hours
      - % unanswered total
      - Valid answers since trial start
      - Displayed questions since trial start (NEW COLUMN)
      - Events last 7 days & total
    """
    if participant_data and event_data:
        participant_df = pd.DataFrame(participant_data)
 #       participant_df = participant_df[participant_df["is_active"] == "True"]

        # Convert empatica_last_update to tz-aware
        participant_df['empatica_last_update'] = pd.to_datetime(participant_df['empatica_last_update'], errors='coerce')
        participant_df['empatica_last_update'] = participant_df['empatica_last_update'].apply(
   #         lambda x: x.tz_localize(israel_tz, nonexistent='shift_forward', ambiguous='NaT') if pd.notnull(x) and x.tzinfo is None else x
            lambda x: x.tz_localize(israel_tz) if pd.notnull(x) and x.tzinfo is None else x
        )

        # Add columns
        participant_df['NaN ans last 36 hours (%)'] = 0.0
        participant_df['NaN ans total (%)'] = 0.0
        participant_df['Valid Answers Since Trial'] = 0
        # NEW COLUMN for how many questions were displayed 
        participant_df['Displayed Questions Since Trial'] = 0

        questionnaire_data = fetch_questionnaire_data()
        questionnaire_df, timetable_df = transform_questionnaire_data(questionnaire_data)

        end_date_36hr = pd.Timestamp.now(tz=israel_tz)  # tz-aware now

        for idx, participant in participant_df.iterrows():
            patient_id = participant['patientId']
            questions_data = get_questions(patient_id)

            # trial start date
            patient_start_str = participant.get('trialStartingDate', None)
            if not patient_start_str or patient_start_str == 'None':
                # default to 30 days ago
                patient_start_trial = end_date_36hr - pd.Timedelta(days=30)
            else:
                patient_start_trial = pd.to_datetime(patient_start_str, errors='coerce')
                if pd.isna(patient_start_trial):
                    patient_start_trial = end_date_36hr - pd.Timedelta(days=14)
                # localize if naive
                if patient_start_trial.tzinfo is None:
                    patient_start_trial = israel_tz.localize(patient_start_trial)

            # trial is 30 days
            total_end_date = patient_start_trial + pd.Timedelta(days=30)
            # if it’s in future, cap it
            if total_end_date > end_date_36hr:
                total_end_date = end_date_36hr

            if questions_data:
                # 1. last 36 hours unanswered
                current_time = pd.Timestamp.now(tz=israel_tz)
                perc_36_hrs = calculate_percentage_of_nan_questions_last_x_hrs(questions_data, timetable_df, current_time, 36)

                # 2. total unanswered from trial start
                perc_total = calculate_percentage_of_nan_questions(questions_data, timetable_df, patient_start_trial, total_end_date)

                # 3. valid answers from trial start
                valid_answers_count = compute_valid_answers_count(
                    questions_data, 
                    start_date=patient_start_trial, 
                    end_date=total_end_date
                )
                
                # 4) Displayed questions in [trialStart, now]
                displayed_q_count = calculate_displayed_questions(
                    timetable_df, 
                    start_date=patient_start_trial, 
                    end_date=total_end_date
                )

                participant_df.at[idx, 'NaN ans last 36 hours (%)'] = perc_36_hrs
                participant_df.at[idx, 'NaN ans total (%)'] = perc_total
                participant_df.at[idx, 'Valid Answers Since Trial'] = valid_answers_count
                participant_df.at[idx, 'Displayed Questions Since Trial'] = displayed_q_count

            else:
                # if no questions data
                participant_df.at[idx, 'NaN ans last 36 hours (%)'] = 100.0
                participant_df.at[idx, 'NaN ans total (%)'] = 100.0
                participant_df.at[idx, 'Valid Answers Since Trial'] = 0
                participant_df.at[idx, 'Displayed Questions Since Trial'] = 0


        # time since last update
        participant_df['Time Since Empatica Update'] = participant_df['empatica_last_update'].apply(calculate_time_since_last_connection)
        participant_df['Time Since Empatica Update'] = participant_df['Time Since Empatica Update'].apply(format_time_since_update)

        # events in the last 7 days & total
        participant_df['Events last 7 days'] = calculate_num_events(event_data, participant_df, days=7)
        participant_df['Events total'] = calculate_num_events(event_data, participant_df, days=None)

        participant_df = participant_df[participant_df["is_active"] == "True"].copy()

        # reorder columns
        # Reorder columns (including the new one)
        column_order = [
            'nickName',
            'Time Since Empatica Update',
     #       'Valid Answers Since Trial',
     #       'Displayed Questions Since Trial',  # <-- NEW
            'NaN ans last 36 hours (%)',
            'NaN ans total (%)',
            'Events last 7 days',
            'Events total'
        ]
        participant_df = participant_df[column_order]
        return participant_df
    else:
        st.error("Failed to fetch participant or event data.")
        return None

def show_participants_status(participants_status_df):
    global status_placeholder
    if participants_status_df is not None:
        status_placeholder.dataframe(participants_status_df, use_container_width=True, hide_index=True)
    else:
        st.error("Failed to fetch participants status data.")

# ----------------------------
# FORMS
# ----------------------------
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
                participant_data = fetch_participants_data()
                show_participants_data()
                event_data = fetch_events_data()
                participants_status_df = fetch_participants_status(participant_data, event_data)
                show_participants_status(participants_status_df)
            else:
                st.error(f"Failed to add participant. Status code: {response.status_code}")

def update_participant_form(container):
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
                participant_data = fetch_participants_data()
                show_participants_data()
                event_data = fetch_events_data()
                participants_status_df = fetch_participants_status(participant_data, event_data)
                show_participants_status(participants_status_df)
            else:
                st.error(f"Failed to update participant. Status code: {response.status_code}")

def add_event_form(form_expander):
    participant_data = fetch_participants_data()
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
                eventDateTimeStr = event_dt_utc.strftime("%Y-%m-%d %H:%M:%S.%fZ")

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

# ----------------------------
# SHOW QUESTIONS + EVENTS
# ----------------------------
def show_questions(patient_id, questionnaire_df):
    questions_data = get_questions(patient_id)
    if questions_data and questionnaire_df is not None:
        timestamps = []
        question_texts = []
        answers = []

        for question in questions_data:
            answer = question.get('answer', None)
            question_num = question.get('questionNum')
            row_match = questionnaire_df.loc[questionnaire_df['מס שאלה'] == question_num, 'השאלה']
            question_text = row_match.iloc[0] if not row_match.empty else "(Missing question)"
            timestamp = question.get('timestamp', 'No timestamp provided')
            # Parse tz-aware
            parsed_ts = pd.to_datetime(timestamp, errors='coerce')
            if parsed_ts is not None and not pd.isna(parsed_ts):
                if parsed_ts.tzinfo is None:
                    parsed_ts = israel_tz.localize(parsed_ts)
 #                   parsed_ts = israel_tz.localize(parsed_ts, nonexistent='shift_forward', ambiguous='NaT')
                formatted_ts = parsed_ts.strftime('%Y-%m-%d %H:%M:%S %Z')
            else:
                formatted_ts = "Invalid or missing"

            timestamps.append(formatted_ts)
            question_texts.append(question_text)
            answers.append(answer)

        if timestamps:
            questions_df = pd.DataFrame({
                'Timestamp': timestamps,
                'Question': question_texts,
                'Answer': answers
            })
            questions_df.sort_values(by='Timestamp', ascending=False, inplace=True)
            st.dataframe(questions_df, use_container_width=True, hide_index=True)
        else:
            st.warning("No questions with answers found.")
    else:
        st.error("Failed to retrieve questions or questionnaire data.")


def ensure_microseconds(ts):
    """ 
    Converts ts to a string if possible and appends .000000 if no decimal fraction is found.
    """
    # 1. If ts is None/NaN, just return it
    if pd.isnull(ts):
        return ts  # This will remain NaN/None

    # 2. If ts is already a datetime (e.g., from earlier parsing), convert it to string
    if isinstance(ts, datetime.datetime):
        ts_str = ts.isoformat()
    else:
        # Otherwise, just turn it into a string
        ts_str = str(ts)

    # 3. If the string already has '.', it presumably has microseconds
    if '.' in ts_str:
        return ts_str

    # 4. Add '.000000' before any +HH:MM, -HH:MM, or trailing 'Z'
    match = re.search(r'([+\-]\d{2}:\d{2}|Z)$', ts_str)
    if match:
        idx = match.start()
        return ts_str[:idx] + '.000000' + ts_str[idx:]
    else:
        # If no offset or 'Z' found, just append .000000
        return ts_str + '.000000'
    

def display_events_data(event_data, participant_data):
    participant_df = pd.DataFrame(participant_data)
    if event_data and participant_data:
        events_df = pd.DataFrame(event_data)
        
         # A) Convert the column to strings with microseconds if missing
        events_df['timestamp'] = events_df['timestamp'].apply(
            lambda x: ensure_microseconds(x) if pd.notnull(x) else x
        )

        # B) Now parse to datetime
        events_df['timestamp'] = pd.to_datetime(events_df['timestamp'], errors='coerce')

        # C) Format for display
        events_df['timestamp'] = events_df['timestamp'].apply(
            lambda x: x.strftime('%Y-%m-%d %H:%M:%S %Z') if pd.notnull(x) else None
        )
        
        # For display, optionally convert to a string without microseconds
    #    events_df['timestamp'] = events_df['timestamp'].apply(lambda x: x.strftime('%Y-%m-%d %H:%M:%S %Z') if pd.notnull(x) else None)

        merged_df = pd.merge(events_df, participant_df[['patientId', 'nickName']], on='patientId', how='left')
        if 'deviceId' in merged_df.columns:
            merged_df.drop(columns=['deviceId'], inplace=True)

        reordered_columns = ['timestamp', 'nickName', 'severity', 'eventType', 'activity', 'origin', 'patientId', 'location']
        merged_df = merged_df[reordered_columns]
        events_df_sorted = merged_df.sort_values(by='timestamp', ascending=False)
        st.dataframe(events_df_sorted, use_container_width=True, hide_index=True)
    else:
        st.error("Failed to fetch data or no data available.")

# ----------------------------
# MAIN DASHBOARD
# ----------------------------
def show_dashboard():
    global status_placeholder
    global participants_placeholder

    # 1. fetch data
    event_data = fetch_events_data()
    participant_data = fetch_participants_data()
    questionnaire_data = fetch_questionnaire_data()
    
    # 2. participants status
    participants_status_df = fetch_participants_status(participant_data, event_data)

    st.subheader("Participants Status")
    status_placeholder = st.empty()
    show_participants_status(participants_status_df)

    st.subheader("Participants Data")
    participants_placeholder = st.empty()
    show_participants_data()

    with st.expander("Add New Participant"):
        add_participant_form(st)

    with st.expander("Update Participant"):
        update_participant_form(st)

    if st.button('Refresh Data', key='refresh_button1'):
        st.cache_data.clear()

    if questionnaire_data:
        questionnaire_df, timetable_df = transform_questionnaire_data(questionnaire_data)
    else:
        questionnaire_df, timetable_df = None, None

    # 3. retrieve participant's data
    st.subheader("Retrieve Participant's Data")
    participant_df = pd.DataFrame(participant_data)
    user_options2 = participant_df['nickName'].tolist()
    selected_user2 = st.selectbox("Select User", user_options2)

    if st.button("Get Participant's Data"):
        try:
            user_status = participants_status_df[participants_status_df['nickName'] == selected_user2]
            if not user_status.empty:
                st.dataframe(user_status, use_container_width=True, hide_index=True)
            else:
                st.warning(f"No status found for user {selected_user2}.")
        except Exception as e:
            st.error(f"Failed to retrieve status for user: {e}")

        try:
            selected_partici = participant_df[participant_df['nickName'] == selected_user2].iloc[0]
            patient_id = selected_partici['patientId']
            user_events = pd.DataFrame(event_data)
                     
            # Step A: Ensure microseconds for any raw string that lacks them
            user_events['timestamp'] = user_events['timestamp'].apply(
                lambda x: ensure_microseconds(x) if pd.notnull(x) else x
            )

            # Step B: Convert to datetime
            user_events['timestamp'] = pd.to_datetime(user_events['timestamp'], errors='coerce')

            # (Optional) Step C: Format for display
            user_events['timestamp'] = user_events['timestamp'].apply(
                lambda x: x.strftime('%Y-%m-%d %H:%M:%S %Z') if pd.notnull(x) else None
            )
         
            user_events = user_events[user_events['patientId'] == patient_id]
            if not user_events.empty:
                user_events_sorted = user_events.sort_values(by='timestamp', ascending=False)
                st.dataframe(user_events_sorted, use_container_width=True, hide_index=True)
            else:
                st.warning(f"No events found for user {selected_user2}.")
        except Exception as e:
            st.error(f"Failed to retrieve events for user: {e}")

        try:
            if questionnaire_df is not None and patient_id:
                show_questions(patient_id, questionnaire_df)
                st.success(f"Questions from user fetched!")
        except Exception as e:
            st.error(f"Failed to get questions from user: {e}")

    # 4. Post Event
    st.subheader("Post Event")
    with st.expander("Add Event"):
        add_event_form(st)

    st.markdown("<hr>", unsafe_allow_html=True)

    if st.button('Refresh Data', key='refresh_button2'):
        st.cache_data.clear()

    # 5. Show All Events
    st.subheader("All Events Data")
    display_events_data(event_data, participant_data)

    # 6. Show Questionnaire
    if questionnaire_data:
        st.subheader("Questionnaire Details")
        st.dataframe(questionnaire_df, hide_index=True)
        st.subheader("Questionnaire Timetable")
        st.dataframe(timetable_df)
    else:
        st.error("Failed to fetch questionnaire data.")

    st.markdown("<hr>", unsafe_allow_html=True)

    # 7. Push Notifications
    st.subheader("Push Notification")
    col1, col2, col3 = st.columns(3, gap="small")

    with col1:
        if participant_data:
            participant_df = pd.DataFrame(participant_data)
            user_options = participant_df['nickName'].tolist()
            selected_user = st.selectbox("Select User for Notification", user_options)
        else:
            st.error("No participant data available.")

    with col2:
        questionnaire_options = ["נא למלא שאלון אירוע", "נא לוודא חיבור שעון", "נא לוודא שעון על היד"]
        selected_questionnaire = st.selectbox("Select Option", questionnaire_options)
        custom_message = st.text_input("Or enter a custom message")

    with col3:
        st.markdown("""
            <style>
            div.stButton > button {
                margin-top: 12px;  
            }
            </style>
        """, unsafe_allow_html=True)

        custom_data = {"Nick": "Mario", "Room": "PortugalVSDenmark"}
        if st.button("Send App Notification"):
            try:
                selected_participant = participant_df[participant_df['nickName'] == selected_user].iloc[0]
                fcm_token = selected_participant['firebaseId']
                title = selected_user
                body = custom_message if custom_message else selected_questionnaire
                response = send_firebase_notification(fcm_token, title, body, data=custom_data)
                st.success(f"Firebase Notification sent! Response: {response}")
            except Exception as e:
                st.error(f"Failed to send Firebase notification: {e}")

    st.markdown("<hr>", unsafe_allow_html=True)


if __name__ == "__main__":
    show_dashboard()
