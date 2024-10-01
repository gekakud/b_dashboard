import streamlit as st
import pandas as pd
import numpy as np
import requests
from private_config import *
import firebase_admin
from firebase_admin import credentials
from firebase_admin import messaging
from api import fetch_participants, fetch_questionnaire_data, fetch_events_data,update_participant_to_db
from api import get_questions, add_participant_to_db, post_event_to_db
import datetime
import pytz


status_placeholder = None
participants_placeholder = None

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

def fetch_participants_data():
    participant_data = fetch_participants()
    if participant_data:
        for entry in participant_data:
            entry['created_at'] = entry.pop('createdAt', entry.get('created_at', ''))
            entry['updated_at'] = entry.pop('updatedAt', entry.get('updated_at', ''))
            entry['trial_starting_date'] = entry.get('trialStartingDate', '')  # Adding trialStartingDate field
            entry['empatica_status'] = entry.pop('empaticaStatus', entry.get('empatica_status', ''))
            entry['num_of_events_current_date'] = entry.pop('numOfEventsCurrentDate', entry.get('num_of_events_current_date', ''))
            entry['is_active'] = entry.pop('isActive', entry.get('is_active', ''))
        return participant_data
    else:
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

def format_timestamp_without_subseconds(timestamp):
    if pd.notnull(timestamp):
        return pd.to_datetime(timestamp).strftime('%Y-%m-%dT%H:%M:%S')
    else:
        return "N/A"  # Handle missing or invalid timestamps

def show_participants_data():
    global participants_placeholder
    participant_data = fetch_participants()
    event_data = fetch_events_data()


    if participant_data:
        participant_df = pd.DataFrame(participant_data)
        
        # Apply formatting to the created_at column
        participant_df['created_at'] = participant_df['created_at'].apply(format_timestamp_without_subseconds)
        participant_df['trial_starting_date'] = participant_df['trial_starting_date'].apply(format_timestamp_without_subseconds)

        participant_df['Events total'] = calculate_num_events(event_data, participant_df, days=None)

        column_order = [
            'nickName',
            'phone',
            'patientId',
            'empaticaStatus',
            'created_at',
            'trial_starting_date',  # Add the trialStartingDate column
            'empaticaId',
            'firebaseId',
            'Events total',
            'isActive'
        ]
        participant_df = participant_df[column_order]
        participants_placeholder.dataframe(participant_df, use_container_width=True, hide_index=True)
    else:
        st.error("Failed to fetch participants data.")

def show_participants_status(participants_status_df):
    global status_placeholder

    if participants_status_df is not None:
        status_placeholder.dataframe(participants_status_df, use_container_width=True, hide_index=True)
    else:
        st.error("Failed to fetch participants status data.")

def fetch_participants_status(participant_data, event_data):
    if participant_data and event_data:
        participant_df = pd.DataFrame(participant_data)

        # Ensure the empatica_last_update column is in datetime format
        participant_df['empatica_last_update'] = pd.to_datetime(participant_df['empatica_last_update'], errors='coerce')

        # Initialize the columns with default float values
        participant_df['NaN ans last 36 hours (%)'] = 0.0
        participant_df['NaN ans total (%)'] = 0.0
        questionnaire_data = fetch_questionnaire_data()
        questionnaire_df, timetable_df = transform_questionnaire_data(questionnaire_data)

        end_date_36hr = pd.Timestamp.now()
        start_date_36hr = end_date_36hr - pd.Timedelta(hours=36)
        
        # Iterate over each participant to fetch and process their questionnaire data
        for idx, participant in participant_df.iterrows():
            patient_id = participant['patientId']
            questions_data = get_questions(patient_id)
            patient_start_trial_str = participant['trialStartingDate']
            
            # If no date for starting trial - take last 14 days
            if patient_start_trial_str == 'None':
                patient_start_trial = end_date_36hr - pd.Timedelta(days=14)
            else:
                patient_start_trial = pd.to_datetime(patient_start_trial_str)

            # Trial is 14 days
            total_end_date = patient_start_trial + pd.Timedelta(days=14)
            
            # Localize to Israel timezone (Asia/Jerusalem)
            israel_tz = pytz.timezone('Asia/Jerusalem')

            # Ensure both timestamps are timezone-aware with Israel time zone
            total_end_date = total_end_date.tz_convert(israel_tz) if total_end_date.tzinfo else total_end_date.tz_localize(israel_tz)
            end_date_36hr = end_date_36hr.tz_convert(israel_tz) if end_date_36hr.tzinfo else end_date_36hr.tz_localize(israel_tz)


            if total_end_date > end_date_36hr:
                total_end_date = end_date_36hr
        

            if questions_data:
                percentage_last_36_hours = calculate_percentage_of_nan_questions(questions_data, timetable_df,start_date_36hr, end_date_36hr)
                percentage_total = calculate_percentage_of_nan_questions(questions_data, timetable_df, patient_start_trial, total_end_date)

                participant_df.at[idx, 'NaN ans last 36 hours (%)'] = percentage_last_36_hours
                participant_df.at[idx, 'NaN ans total (%)'] = percentage_total

        # Calculate the time since the last update in hours
        participant_df['Time Since Empatica Update'] = participant_df['empatica_last_update'].apply(calculate_time_since_last_connection)

        # Format the time since the last update using the format_time_since_update function
        participant_df['Time Since Empatica Update'] = participant_df['Time Since Empatica Update'].apply(format_time_since_update)

        # Calculate the remaining fields
        participant_df['Events last 7 days'] = calculate_num_events(event_data, participant_df, days=7)
        participant_df['Events total'] = calculate_num_events(event_data, participant_df, days=None)

        column_order = [
            'nickName',
            'Time Since Empatica Update',
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

def calculate_time_since_last_connection(empatica_last_update):
    # Check if empatica_last_update is NaT (Not a Time)
    if pd.isna(empatica_last_update):
        return float('nan')  # Return NaN if the date is not available

    current_time = pd.Timestamp.now()
    time_diff = current_time - empatica_last_update

    return time_diff.total_seconds() / 3600  # Convert time difference to hours

def format_time_since_update(hours):
    if pd.isna(hours):
        return "N/A"
    
    if hours < 24:
        return f"{hours:.1f} Hrs"
    else:
        days = int(hours // 24)
        remaining_hours = hours % 24
        return f"{days} days, {remaining_hours:.1f} Hrs"

def calculate_percentage_of_nan_questions(questions_data, timetable_df, start_date, end_date):
    """
    Calculate the percentage of unanswered (NaN) questions by dividing the number of answered questions 
    by the total number of questions that were displayed in the given date range.

    :param questions_data: DataFrame that contains the answers from the user.
    :param timetable_df: DataFrame that contains the questionnaire timetable with days and times.
    :param start_date: The specific date from which to start counting the questions.
    :param end_date: The specific date until which to count the questions.
    :return: The percentage of unanswered (NaN) questions.
    """
    # Create a DataFrame from the questionnaire data
    df = pd.DataFrame(questions_data)

    # Set the Israel timezone (Asia/Jerusalem)
    israel_tz = pytz.timezone('Asia/Jerusalem')

    # Convert both start_date and end_date to timezone-aware if they are not already
    start_date = pd.to_datetime(start_date).tz_localize(israel_tz) if start_date.tzinfo is None else start_date
    end_date = pd.to_datetime(end_date).tz_localize(israel_tz) if end_date.tzinfo is None else end_date

    # Ensure that the dataframe's 'timestamp' column is timezone-aware too
    df['timestamp'] = pd.to_datetime(df['timestamp'])

    # If 'timestamp' is tz-naive (no timezone), localize it to Israel time
    if df['timestamp'].dt.tz is None:
        df['timestamp'] = df['timestamp'].dt.tz_localize(israel_tz)

    # Filter the questionnaire data to only include answers within the specified date range
    df_filtered = df[(df['timestamp'] >= pd.to_datetime(start_date)) & (df['timestamp'] <= pd.to_datetime(end_date))]

    # Count the number of valid answers (answers in the range of 0-4)
    valid_answers_count = df_filtered['answer'].between(0, 4, inclusive="both").sum()

    # Calculate the total number of questions that were supposed to be displayed within the date range
    total_questions_displayed = calculate_displayed_questions(timetable_df, start_date, end_date)

    # Edge case: If no questions were displayed, return 100% unanswered
    if total_questions_displayed == 0:
        return 100.0

    # Calculate the percentage of unanswered (NaN) questions
    unanswered_percentage = 100.0 * (1 - (valid_answers_count / total_questions_displayed))

    return unanswered_percentage




def calculate_displayed_questions(timetable_df, start_date, end_date):
    """
    Calculate how many questions were scheduled to be displayed to the user from a specific start date until the end date.

    :param timetable_df: DataFrame that contains the questionnaire timetable with days and times.
    :param start_date: The specific date from which to start counting the questions.
    :param end_date: The specific date until which to count the questions.
    :return: The total number of questions displayed to the user from the start date until the end date.
    """
    # Convert the start_date and end_date to datetime if they're not already
    if not isinstance(start_date, pd.Timestamp):
        start_date = pd.to_datetime(start_date)
    if not isinstance(end_date, pd.Timestamp):
        end_date = pd.to_datetime(end_date)
    
    # Set the Israel timezone (Asia/Jerusalem)
    israel_tz = pytz.timezone('Asia/Jerusalem')

    # Make sure both are either timezone-aware with the same timezone, or timezone-naive
    if start_date.tzinfo is None:
        start_date = start_date.tz_localize(israel_tz)
    else:
        start_date = start_date.tz_convert(israel_tz)

    if end_date.tzinfo is None:
        end_date = end_date.tz_localize(israel_tz)
    else:
        end_date = end_date.tz_convert(israel_tz)
    # Ensure that the end_date is not earlier than the start_date
    if end_date < start_date:
        end_date = start_date + pd.Timedelta(hours=36)
    #    raise ValueError("end_date must be after start_date")

    # Initialize a count for displayed questions
    total_questions_displayed = 0

    # Loop over each day between the start date and end date
    date_range = pd.date_range(start=start_date, end=end_date, freq='D')

    for current_day in date_range:
        day_of_week = current_day.strftime('%A')  # Get the day of the week (e.g., 'Monday', 'Tuesday')
        
        # Get the timetable for the specific day of the week
        if day_of_week in timetable_df.columns:
            for time in timetable_df.index:
                question_set = timetable_df.at[time, day_of_week]
                if question_set:
                    # Check if we are on the final day and should stop counting at the end date's time
                    if current_day == end_date.normalize():
                        # Convert the time to a proper timestamp to compare with the end date
                        question_time = pd.to_datetime(f"{current_day.date()} {time}")
                        if question_time > end_date:
                            continue  # Don't count questions scheduled after the end date's time

                    # Split the questions (since they are stored as strings like '1, 2, 3')
                    question_list = question_set.split(', ')
                    total_questions_displayed += len(question_list)

    return total_questions_displayed



"""
Calculate the average number of events per day for each participant.
"""
def calculate_num_events(event_data, participant_df, days=None):
    # Debugging: Check the type of event_data
    print(f"Type of event_data: {type(event_data)}")

    # Ensure event_data is a DataFrame
    if isinstance(event_data, list):
        event_data = pd.DataFrame(event_data)

    # Convert timestamp to datetime
    if 'timestamp' not in event_data.columns:
        raise ValueError("The 'timestamp' column is missing from event_data.")
    event_data['timestamp'] = pd.to_datetime(event_data['timestamp'], errors='coerce')

    # If days is specified, filter events to only include those within the given number of days
    if days is not None:
        cutoff_time = pd.Timestamp.now() - pd.Timedelta(days=days)
        event_data = event_data[event_data['timestamp'] >= cutoff_time]

    # Calculate the number of days between the first and last event for each participant
    grouped = event_data.groupby('patientId')['timestamp'].agg(['min', 'max', 'count'])
    grouped['days'] = (grouped['max'] - grouped['min']).dt.days + 1
    grouped['days'] = grouped['days'].replace(0, 1)

    # Calculate the average daily events
#    grouped['average_daily_events'] = grouped['count'] / grouped['days']
    grouped['average_daily_events'] = grouped['count']

    # Merge this back into the participant DataFrame
    participant_df = participant_df.set_index('patientId').join(grouped[['average_daily_events']]).reset_index()

    # Fill NaN values with 0 for participants with no events in the given period
    participant_df['average_daily_events'].fillna(0, inplace=True)

    return participant_df['average_daily_events']

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

"""
The place where the trial manager can add a participant
"""
def add_participant_form(form_expander):
    with st.form("new_participant_form"):
        nickName = st.text_input("Nickname")
        phone = st.text_input("Phone")
        empaticaId = st.text_input("Empatica ID")
        firebaseId = st.text_input("Firebase ID")
        # Add date and time input fields for trialStartingDate
        trialStartingDate = st.date_input("Trial Starting Date (Date)", key="trialStartingDate_date-Add")
        trialStartingTime = st.time_input("Trial Starting Time", key="trialStartingDate_time-Add")

        submit_button = st.form_submit_button("Submit")

        if submit_button:
            # Combine trialStartingDate and trialStartingTime into a single datetime object
            if trialStartingDate and trialStartingTime:
                trialStartingDateTime = datetime.datetime.combine(trialStartingDate, trialStartingTime)
                trialStartingDateTimeStr = trialStartingDateTime.isoformat()
            else:
                trialStartingDateTimeStr = None

            # Post the participant data to the backend
            response = add_participant_to_db(nickName, phone, empaticaId, firebaseId, trialStartingDateTimeStr)
 
            if response.status_code == 201:
                st.success("Participant added successfully!")
                form_expander.empty()
                #refresh_and_display_participants(placeholder)
                participant_data = fetch_participants_data()
#                show_participants_data(participant_data)
                show_participants_data()
                event_data = fetch_events_data()
                participants_status_df = fetch_participants_status(participant_data, event_data)
                show_participants_status(participants_status_df)
            else:
                st.error(f"Failed to add participant. Status code: {response.status_code}")


def add_event_form(form_expander):
    # Fetch participants data
    participant_data = fetch_participants_data()
    participant_df = pd.DataFrame(participant_data)
    
    with st.form("add_event_form"):
        selected_user = st.selectbox("Select Participant", participant_df['nickName'])
        eventType = st.selectbox("Event Type", ["dissociation", "sadness", "anger", "anxiety", "other" ])   
        activity = st.selectbox("Activity", ["rest", "eating", "exercise", "other"])
        severity = st.slider("Severity", 0, 4, 3)
            # Add date and time input fields for trialStartingDate
        eventDate = st.date_input("Event Date (Date)", key="eventDate_date-Add")
        eventTime = st.time_input("Event Time", key="eventDate_time-Add")

        submit_button = st.form_submit_button("Submit")

        if submit_button:
            # Combine the selected date and time into a full datetime object
            if eventDate and eventTime:
                eventDateTime = datetime.datetime.combine(eventDate, eventTime)
                eventDateTimeStr = eventDateTime.isoformat()
            else:
                eventDateTimeStr = None

            # Show the combined datetime
            st.write(f"Combined Datetime: {eventDateTimeStr}")
            
            # No location data for now
            lat = 0.000
            long = 0.000

            # Get the patientId based on the selected nickname
            selected_participant = participant_df[participant_df['nickName'] == selected_user].iloc[0]
            patientId = selected_participant['patientId']
            deviceId = patientId
            
            location = {
                "lat": lat,
                "long": long
            }
            origin = "assitant"

            # Post the event data to the backend
            response = post_event_to_db(patientId, deviceId, eventDateTimeStr, location, eventType, activity, severity, origin)
            
            if response.status_code == 201:
                st.success("Event posted successfully!")
                form_expander.empty()
            else:
                st.error(f"Failed to post event. Status code: {response.status_code}")


"""
The place where the trial manager can update a specific user's data
"""
def update_participant_form(container):
    with st.form("update_participant_form"):
        patientId = st.text_input("Patient ID", key="patientId")
        nickName = st.text_input("Nickname", key="nickName")
        phone = st.text_input("Phone", key="phone")
        empaticaId = st.text_input("Empatica ID", key="empaticaId")
        firebaseId = st.text_input("Firebase ID", key="firebaseId")
        
                # Add date and time input fields for trialStartingDate
        trialStartingDate = st.date_input("Trial Starting Date (Date)", key="trialStartingDate_date-Update")
        trialStartingTime = st.time_input("Trial Starting Time", key="trialStartingDate_time-Update")

        
#        trialStartingDate = st.date_input("Trial Starting Date", key="trialStartingDate") 
        isActive = st.selectbox("Is Active", [True, False], key="isActive")
        submit_button = st.form_submit_button("Submit Update")

        if submit_button:
                        # Combine trialStartingDate and trialStartingTime into a single datetime object
            if trialStartingDate and trialStartingTime:
                trialStartingDateTime = datetime.datetime.combine(trialStartingDate, trialStartingTime)
                trialStartingDateTimeStr = trialStartingDateTime.isoformat()
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
               # refresh_and_display_participants(placeholder)
                participant_data = fetch_participants_data()
 #               show_participants_data(participant_data)
                show_participants_data()
                event_data = fetch_events_data()
                participants_status_df = fetch_participants_status(participant_data, event_data)
                show_participants_status(participants_status_df)
            else:
                st.error(f"Failed to update participant. Status code: {response.status_code}")

def show_questions(patient_id, questionnaire_df):
    questions_data = get_questions(patient_id)
    if questions_data and questionnaire_df is not None:
        sorted_questions = sorted(questions_data, key=lambda x: x['timestamp'], reverse=True)
        timestamps = []
        question_texts = []
        answers = []
        for question in sorted_questions:
            answer = question.get('answer', None)
            # Only include questions with valid answers (i.e., answers that are not None)
            if answer is not None:
                question_num = question.get('questionNum')
                question_text = questionnaire_df.loc[questionnaire_df['מס שאלה'] == question_num, 'השאלה'].iloc[0]
                timestamp = question.get('timestamp', 'No timestamp provided')
                formatted_timestamp = pd.to_datetime(timestamp).strftime('%Y-%m-%d %H:%M:%S')
                timestamps.append(formatted_timestamp)
                question_texts.append(question_text)
                answers.append(answer)

        # Create a DataFrame only with questions that have valid answers
        if timestamps:
            questions_df = pd.DataFrame({
                'Timestamp': timestamps,
                'Question': question_texts,
                'Answer': answers
            })
            st.dataframe(questions_df, use_container_width=True, hide_index=True)
        else:
            st.warning("No questions with answers found.")
    else:
        st.error("Failed to retrieve questions or questionnaire data.")


"""
Displays the table of events of all participants
"""        
def display_events_data(event_data, participant_data):
    participant_df = pd.DataFrame(participant_data)
    
    if event_data and participant_data:
        events_df = pd.DataFrame(event_data)
        events_df['timestamp'] = pd.to_datetime(events_df['timestamp'].apply(format_timestamp_without_subseconds))
        merged_df = pd.merge(events_df, participant_df[['patientId', 'nickName']], on='patientId', how='left')
        if 'deviceId' in merged_df.columns:
            merged_df.drop(columns=['deviceId'], inplace=True)
                
        reordered_columns = ['timestamp', 'nickName', 'severity', 'eventType', 'activity', 'origin', 'patientId', 'location']
        merged_df = merged_df[reordered_columns]
        events_df_sorted = merged_df.sort_values(by='timestamp', ascending=False)
        st.dataframe(events_df_sorted, use_container_width=True, hide_index=True)
    else:
        st.error("Failed to fetch data or no data available.")

"""
The 'main' function that calculates and displays the dashboard
"""
def show_dashboard():
    global status_placeholder
    global participants_placeholder
 
    # Fetch event, questionnaire and participant data once and reuse it
    event_data = fetch_events_data()
    participant_data = fetch_participants_data()
    participant_df = pd.DataFrame(participant_data)
    questionnaire_data = fetch_questionnaire_data()
    participants_status_df = fetch_participants_status(participant_data, event_data)

    st.subheader("Participants Status")
    status_placeholder = st.empty()
    show_participants_status(participants_status_df)
    
    st.subheader("Participants Data")
    participants_placeholder = st.empty()
#    show_participants_data(participant_data)
    show_participants_data()
    
    with st.expander("Add New Participant"):
        add_participant_form(st)
    
    with st.expander("Update Participant"):
        update_participant_form(st)
    
    if st.button('Refresh Data', key='refresh_button1'):
        st.cache_data.clear()
    
    if questionnaire_data:
        questionnaire_df, timetable_df = transform_questionnaire_data(questionnaire_data)

    # The place where the trial menager/supervisor can look at a specific participant data
    st.subheader("Retrieve Participant's Data")
    user_options2 = participant_df['nickName'].tolist()
    selected_user2 = st.selectbox("Select User for retrieving questions", user_options2)
    
    # Add the "User's Status" button
    if st.button("Get Participant's Data"):
        try:
            user_status = participants_status_df[participants_status_df['nickName'] == selected_user2]
            if not user_status.empty:
                st.dataframe(user_status, use_container_width=True, hide_index=True)
            else:
                st.warning(f"No status found for user {selected_user2}.")
        except Exception as e:
            st.error(f'Failed to retrieve status for user. Error: {str(e)}')
            
        try:
            selected_partici = participant_df[participant_df['nickName'] == selected_user2].iloc[0]
            patient_id = selected_partici['patientId']
            user_events = pd.DataFrame(event_data)
            user_events = user_events[user_events['patientId'] == patient_id]
            if not user_events.empty:
                user_events_sorted = user_events.sort_values(by='timestamp', ascending=False)
                st.dataframe(user_events_sorted, use_container_width=True, hide_index=True)
            else:
                st.warning(f"No events found for user {selected_user2}.")
        
        except Exception as e:
            st.error(f'Failed to retrieve events for user. Error: {str(e)}')
        
        try:
            if patient_id and questionnaire_df is not None:
                show_questions(patient_id, questionnaire_df)
                st.success(f'Questions from user arrived!')
        
        except Exception as e:
            st.error(f'Failed to get questions from user. Error: {str(e)}')


    # Post Event Section
    st.subheader("Post Event")
    with st.expander("Add Event"):
        add_event_form(st)

    st.markdown("<hr>", unsafe_allow_html=True)
    
    if st.button('Refresh Data', key='refresh_button2'):
        st.cache_data.clear()

    st.subheader("All Events Data")
    display_events_data(event_data, participant_data)

    if questionnaire_data:
        st.subheader("Questionnaire Details")
        st.dataframe(questionnaire_df, hide_index=True)
        st.subheader("Questionnaire Timetable")
        st.dataframe(timetable_df)
    else:
        st.error("Failed to fetch questionnaire data or no data available.")

    st.markdown("<hr>", unsafe_allow_html=True)

    st.subheader("Push Notification")
    col1, col2, col3 = st.columns(3, gap="small")

    with col1:
        if participant_data:
            participant_df = pd.DataFrame(participant_data)
            user_options = participant_df['nickName'].tolist()
            selected_user = st.selectbox("Select User for Notification", user_options)
        else:
            st.error("Failed to fetch participants data.")
        
    with col2:
        questionnaire_options = ["נא למלא שאלון אירוע", "נא לוודא חיבור שעון", "נא לוודא שעון על היד"]
        selected_questionnaire = st.selectbox("Select Questionnaire Option", questionnaire_options)
        custom_message = st.text_input("Or enter a custom message")

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
                body = custom_message if custom_message else selected_questionnaire
                response = send_firebase_notification(fcm_token, title, body, data=custom_data)
                st.success(f'Firebase Notification sent! Response: {response}')
            except Exception as e:
                st.error(f'Failed to send Firebase notification. Error: {str(e)}')
  
    st.markdown("<hr>", unsafe_allow_html=True)

if __name__ == "__main__":
    show_dashboard()