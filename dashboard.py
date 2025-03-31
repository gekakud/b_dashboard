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
from forms import (
    update_participant_form,
    add_participant_form,
    add_event_form
)


from data_processing import (
    transform_questionnaire_data,
    calculate_percentage_of_nan_questions_last_x_hrs,
    calculate_percentage_of_nan_questions,
    calculate_displayed_questions,
    calculate_num_events,
    calculate_time_since_last_connection,
    compute_valid_answers_count    
)

import datetime
import pytz

from api import (
    fetch_participants, 
    fetch_questionnaire_data, 
    fetch_events_data,
    update_participant_to_db,
    get_questions, 
    add_participant_to_db, 
    post_event_to_db
)

# ----------------------------
# GLOBALS
# ----------------------------
status_placeholder = None
participants_placeholder = None

# Set a global timezone for the entire app
israel_tz = pytz.timezone('Asia/Jerusalem')
UTC_tz = pytz.timezone('Etc/GMT')

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
            entry['Empatica Wearing Status'] = entry.pop('empaticaWearingStatus', entry.get('Empatica Wearing Status',''))
        return participant_data
    else:
        return None
    
'''ET  התווסף שדה חדש בשם : empaticaWearingStatus
הערכים שלו הם : NONE, True,False 
השדה נותן אינדיקציה האם השעון נלבש כראוי על היד. '''
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
        empatica_last_update = empatica_last_update.tz_localize(UTC_tz)
    if pd.notnull(empatica_last_update):
        time_diff = current_time - empatica_last_update
        if time_diff.total_seconds() > threshold_hours * 3600:
            return ['background-color: yellow'] * len(row)
    return [''] * len(row)


def parse_time_since_str(val: str) -> float:
    """
    Convert '8 days, 14.5 Hrs' or '3.2 Hrs' into a float of total hours.
    Return None if 'N/A' or cannot parse.
    """
    if val == "N/A":
        return None
    
    val = val.lower().strip()
    if "days" in val:
        # e.g. "8 days, 14.5 hrs"
        # 1) remove ' hrs'
        val = val.replace(' hrs', '').replace(' hr', '')
        # 2) split by 'days,'
        parts = val.split('days')
        if len(parts) == 2:
            days_str = parts[0].strip()           # "8"
            hours_str = parts[1].replace(',', '') # "14.5"
            try:
                d = float(days_str)
                h = float(hours_str)
                return d * 24 + h
            except ValueError:
                return None
    else:
        # e.g. "3.2 hrs"
        val = val.replace(' hrs', '').replace(' hr', '')
        try:
            return float(val)
        except ValueError:
            return None
    
    return None  # fallback if we couldn't parse


def highlight_old_updates_cell(val):
    """Highlight if the time-since‐update string is more than threshold_hours."""
    threshold_hours = 10
    
    total_hours = parse_time_since_str(val)
    if total_hours is not None and total_hours > threshold_hours:
        return 'background-color: yellow;'
    return ''


def format_timestamp_without_subseconds(timestamp):
    """
    Convert a timestamp to ISO8601 (no microseconds).
    """
    if pd.notnull(timestamp):
        return pd.to_datetime(timestamp).strftime('%Y-%m-%dT%H:%M:%S')
    else:
        return "N/A"

def format_timestamp_without_subseconds_IST(timestamp_str):
    """
    Parse timestamp_str as UTC, then convert and format in Israel time.
    """
    if pd.notnull(timestamp_str):
        # 1) Parse as datetime
        dt_utc = pd.to_datetime(timestamp_str, utc=True, errors='coerce')
        
        # 2) Convert from UTC to Israel local time
        dt_israel = dt_utc.tz_convert(israel_tz)
        
        # 3) Format
        return dt_israel.strftime('%Y-%m-%d %H:%M:%S')
    else:
        return "N/A"

def show_participants_data():
    global participants_placeholder
    participant_data = fetch_participants()
    event_data = fetch_events_data()

    if participant_data:
        participant_df = pd.DataFrame(participant_data)

        # Format columns
        participant_df['created_at'] = participant_df['created_at'].apply(format_timestamp_without_subseconds_IST)
        participant_df['trial_starting_date'] = participant_df['trial_starting_date'].apply(format_timestamp_without_subseconds_IST)
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


def format_time_since_update(hours):
    if pd.isna(hours):
        return "N/A"
    if hours < 24:
        return f"{hours:.1f} Hrs"
    else:
        days = int(hours // 24)
        remaining_hours = hours % 24
        return f"{days} days, {remaining_hours:.1f} Hrs"


def displayed_questions_numbers(timetable_df, start_date, end_date):
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
                    question_time = pd.to_datetime(question_time_str, errors='coerce').tz_localize(israel_tz)
                    # Now skip if outside the actual [start_date, end_date] range
                    if question_time < start_date:
                        continue
                    if question_time > end_date:
                        continue
                    question_list = question_set.split(', ')
                    total_questions_displayed += len(question_list)

    return total_questions_displayed


# ----------------------------
# FETCH & SHOW PARTICIPANTS STATUS
# ----------------------------
def fetch_participants_status(participant_data, event_data):
    """
    Builds a DataFrame of participants' status, including:
      - Time since last Empatica update
      - Empatica Wearing Status
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
        #participant_df['empatica_last_update'] = participant_df['empatica_last_update'].apply(
        #    lambda x: x.tz_localize(israel_tz) if pd.notnull(x) and x.tzinfo is None else x
        #)        
        participant_df['empatica_last_update'] = participant_df['empatica_last_update'].apply(
            lambda x: x.tz_localize(UTC_tz) if pd.notnull(x) and x.tzinfo is None else x
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
                hours_since_start = (current_time - patient_start_trial).total_seconds() / 3600.0
                hours_to_calc = min(36, hours_since_start)

                perc_36_hrs = calculate_percentage_of_nan_questions_last_x_hrs(questions_data, timetable_df, current_time, hrs=hours_to_calc)

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
        column_order = [
            'nickName',
            'Time Since Empatica Update',
            'Empatica Wearing Status',
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

def highlight_if_above(val, threshold):
    """
    Return a highlight style if val > threshold, else no styling.
    """
    if pd.notnull(val) and val > threshold:
        return 'background-color: yellow;'
    return ''

def highlight_if_below(val, threshold):
    """
    Return a highlight style if val > threshold, else no styling.
    """
    if pd.notnull(val) and float(val) < threshold:
        return 'background-color: yellow;'
    return ''

def show_participants_status(participants_status_df):
    if participants_status_df is not None:
        styled_df = (
            participants_status_df.style
            # 1) Still highlight Time Since Empatica Update as before
            .applymap(highlight_old_updates_cell, subset=['Time Since Empatica Update'])
            
            # 2) Highlight "NaN ans last 36 hours (%)" if > 70
            .applymap(lambda x: highlight_if_above(x, 70), 
                      subset=["NaN ans last 36 hours (%)"])

            # 3) Highlight "NaN ans total (%)" if > 50
            .applymap(lambda x: highlight_if_above(x, 50), 
                      subset=["NaN ans total (%)"])

            # 4) Highlight "Events last 7 days" if > 7
            .applymap(lambda x: highlight_if_above(x, 7), 
                      subset=["Events last 7 days"])

            # 4) Highlight "Events last 7 days" if > 7
            .applymap(lambda x: highlight_if_below(x, 75), 
                      subset=["Empatica Wearing Status"])
            
            # 6) Finally format certain columns as integers (if desired)
            .format({
                "NaN ans last 36 hours (%)": "{:.0f}",
                "NaN ans total (%)": "{:.0f}",
                "Events last 7 days": "{:.0f}",
                "Events total": "{:.0f}",
            })
        )
        status_placeholder.dataframe(styled_df, use_container_width=True, hide_index=True)
    else:
        st.error("Failed to fetch participants status data.")
# ----------------------------
# SHOW QUESTIONS + EVENTS
# ----------------------------
def show_questions(patient_id, questionnaire_df):
    questions_data = get_questions(patient_id)
    if questions_data and questionnaire_df is not None:
        timestamps = []
        question_nums = []
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
                formatted_ts = parsed_ts.strftime('%Y-%m-%d %H:%M:%S %Z')
            else:
                formatted_ts = "Invalid or missing"

            timestamps.append(formatted_ts)
            question_nums.append(question_num)
            question_texts.append(question_text)
            answers.append(answer)

        if timestamps:
            questions_df = pd.DataFrame({
                'Timestamp': timestamps,
                'Num': question_nums,
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
    
def update_participant_data_status_display():
    participant_data = fetch_participants_data()
    show_participants_data()
    event_data = fetch_events_data()
    participants_status_df = fetch_participants_status(participant_data, event_data)
    show_participants_status(participants_status_df)


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
        
        # Convert trial start column to datetime
        participant_df['trial_starting_date'] = pd.to_datetime(participant_df['trial_starting_date'], errors='coerce')

        # Localize trial start if naive
        participant_df['trial_starting_date'] = participant_df['trial_starting_date'].apply(
            lambda x: israel_tz.localize(x) if pd.notnull(x) and x.tzinfo is None else x
        )

        # Merge trial start into merged_df
        merged_df = pd.merge(
            merged_df,
            participant_df[['patientId', 'trial_starting_date']],
            on='patientId',
            how='left'
        )

        # Convert events_df timestamp to datetime again just in case (safe step)
        merged_df['timestamp'] = pd.to_datetime(merged_df['timestamp'], errors='coerce')

        # Localize if needed
        merged_df['timestamp'] = merged_df['timestamp'].apply(
            lambda x: israel_tz.localize(x) if pd.notnull(x) and x.tzinfo is None else x
        )

        # Keep only events after trial start
        merged_df = merged_df[
            (pd.notnull(merged_df['trial_starting_date'])) &
            (merged_df['timestamp'] >= merged_df['trial_starting_date'])
        ]

        
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
        if add_participant_form(st) == True:
            update_participant_data_status_display()

    with st.expander("Update Participant"):
        # If the button was pressed, we updated the displayed data
        if update_participant_form(st) == True:
            update_participant_data_status_display()


    if st.button('Refresh Data', key='refresh_button1'):
        st.cache_data.clear()

    if questionnaire_data:
        questionnaire_df, timetable_df = transform_questionnaire_data(questionnaire_data)
    else:
        questionnaire_df, timetable_df = None, None

    # 3. retrieve specific participant's data
    st.subheader("Retrieve Participant's Data")
    participant_df = pd.DataFrame(participant_data)
    user_options2 = participant_df['nickName'].tolist()
    selected_user2 = st.selectbox("Select User", user_options2)

    if st.button("Get Participant's Data"):
        # Retrieving and showing Patient's status line
        try:
            user_status = participants_status_df[participants_status_df['nickName'] == selected_user2]
            if not user_status.empty:
                st.dataframe(user_status, use_container_width=True, hide_index=True)
            else:
                st.warning(f"No status found for user {selected_user2}.")
        except Exception as e:
            st.error(f"Failed to retrieve status for user: {e}")
        
        # Retrieving and showing Patient's events (both from application and from assistant)
        try:
            selected_partici = participant_df[participant_df['nickName'] == selected_user2].iloc[0]
            patient_id = selected_partici['patientId']
            # user_events = pd.DataFrame(event_data)
                     
            # #Ensure microseconds for any raw string that lacks them
            # user_events['timestamp'] = user_events['timestamp'].apply(
            #     lambda x: ensure_microseconds(x) if pd.notnull(x) else x
            # )
            # user_events['timestamp'] = pd.to_datetime(user_events['timestamp'], errors='coerce')

            # # Format for display
            # user_events['timestamp'] = user_events['timestamp'].apply(
            #     lambda x: x.strftime('%Y-%m-%d %H:%M:%S %Z') if pd.notnull(x) else None
            # )
         
            user_events = pd.DataFrame(event_data)

            # Ensure microseconds
            user_events['timestamp'] = user_events['timestamp'].apply(
                lambda x: ensure_microseconds(x) if pd.notnull(x) else x
            )
            user_events['timestamp'] = pd.to_datetime(user_events['timestamp'], errors='coerce')

            # Localize to Israel timezone if naive
            user_events['timestamp'] = user_events['timestamp'].apply(
                lambda x: israel_tz.localize(x) if pd.notnull(x) and x.tzinfo is None else x
            )

            # Filter by patient ID
            user_events = user_events[user_events['patientId'] == patient_id]

            # Trial start parsing
            trial_start_str = selected_partici.get('trial_starting_date', None)
            trial_start = pd.to_datetime(trial_start_str, errors='coerce')
            if pd.notnull(trial_start) and trial_start.tzinfo is None:
                trial_start = israel_tz.localize(trial_start)

            # Filter by trial start
            user_events = user_events[user_events['timestamp'] >= trial_start]

            # Format for display
            user_events['timestamp'] = user_events['timestamp'].apply(
                lambda x: x.strftime('%Y-%m-%d %H:%M:%S %Z') if pd.notnull(x) else None
            )


            if not user_events.empty:
                user_events_sorted = user_events.sort_values(by='timestamp', ascending=False)
                st.dataframe(user_events_sorted, use_container_width=True, hide_index=True)
            else:
                st.warning(f"No events found for user {selected_user2}.")
        except Exception as e:
            st.error(f"Failed to retrieve events for user: {e}")
            
        # Retrieving and showing Patient's scheduled questionnaire answers
        try:
            if questionnaire_df is not None and patient_id:
                show_questions(patient_id, questionnaire_df)
                st.success(f"Questions from user fetched!")
        except Exception as e:
            st.error(f"Failed to get questions from user: {e}")

    # 4. Post Event
    st.subheader("Post Event")
    with st.expander("Add Event"):
        add_event_form(st, participant_data)

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
