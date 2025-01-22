import pandas as pd
import datetime
import pytz

# Set a global timezone for the entire app
israel_tz = pytz.timezone('Asia/Jerusalem')


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
    1) Get unique question numbers displayed in [current_time - hrs, current_time).
    2) Get unique question numbers answered by user in that same window.
    3) Percentage of displayed questions that do NOT appear in the answered set.

    Assumes `current_time` is tz-aware in 'Asia/Jerusalem' 
    and that 'timestamp' in questions_data can be parsed as well.
    """

    # ----------------------------------------------------------------
    # STEP 0: Ensure current_time is tz-aware
    # ----------------------------------------------------------------
    if current_time.tzinfo is None:
        # If you want everything in 'Asia/Jerusalem', localize it
        current_time = israel_tz.localize(current_time)

    # build start_time
    start_time = current_time - pd.Timedelta(hours=hrs)

    # ----------------------------------------------------------------
    # STEP A: Gather displayed questions in [start_time, current_time)
    # ----------------------------------------------------------------
    displayed_set = set()

    # If you want to keep times tz-aware, ensure .normalize() doesn't drop tz
    # We'll do it manually:
    start_day = start_time.replace(hour=0, minute=0, second=0, microsecond=0)
    current_day = current_time.replace(hour=0, minute=0, second=0, microsecond=0)
    date_range = pd.date_range(
        start=start_day,
        end=current_day,
        freq='D'
    )

    for day_dt in date_range:
        # localize this day_dt to 'Asia/Jerusalem' if it's naive
        if day_dt.tzinfo is None:
            day_dt = day_dt.tz_localize(israel_tz)

        for hour in timetable_df.index:  # e.g. "10:00", "14:00", ...
            slot_time_str = f"{day_dt.strftime('%Y-%m-%d')} {hour}"
            slot_time = pd.to_datetime(slot_time_str, errors='coerce')

            if pd.notnull(slot_time) and slot_time.tzinfo is None:
                slot_time = slot_time.tz_localize(israel_tz)

            # Now compare slot_time with [start_time, current_time)
            if slot_time is None or pd.isna(slot_time):
                continue

            if not (start_time <= slot_time < current_time):
                continue

            # Check which questions are displayed at (hour, day_of_week)
            day_of_week = slot_time.strftime('%A')
            if day_of_week not in timetable_df.columns:
                continue

            question_set_str = timetable_df.at[hour, day_of_week]
            if not question_set_str:
                continue

            # e.g. "5, 7, 12"
            question_nums = [q.strip() for q in question_set_str.split(',')]
            for qnum in question_nums:
                displayed_set.add(qnum)

    displayed_count = len(displayed_set)
    if displayed_count == 0:
        # No questions displayed -> 0% unanswered
        return 0.0

    # ----------------------------------------------------------------
    # STEP B: Gather answered questions in the past X hours
    # ----------------------------------------------------------------
    # Convert questions_data to DataFrame if it's a list
    if isinstance(questions_data, list):
        questions_data = pd.DataFrame(questions_data)

    if 'timestamp' not in questions_data.columns or 'questionNum' not in questions_data.columns:
        raise ValueError("questions_data is missing 'timestamp' or 'questionNum' columns")

    # Convert question timestamps
    questions_data['timestamp'] = pd.to_datetime(questions_data['timestamp'], errors='coerce')

    # If some rows are naive and you want them also in 'Asia/Jerusalem', do:
    def localize_if_naive(dt):
        if pd.notnull(dt) and dt.tzinfo is None:
            return dt.tz_localize(israel_tz)
        return dt

    questions_data['timestamp'] = questions_data['timestamp'].apply(localize_if_naive)

    # Filter to [start_time, current_time)
    answered_in_window = questions_data[
        (questions_data['timestamp'] >= start_time) &
        (questions_data['timestamp'] < current_time)
    ].copy()

    # Build a set of questionNums answered in that window
    answered_in_window['questionNum'] = answered_in_window['questionNum'].astype(str)
    answered_set = set(answered_in_window['questionNum'].unique())

    # ----------------------------------------------------------------
    # STEP C: Compute difference
    # ----------------------------------------------------------------
    not_answered = displayed_set - answered_set
    unanswered_count = len(not_answered)

    unanswered_percentage = (unanswered_count / displayed_count) * 100
    return unanswered_percentage

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

def unify_timestamp_str(ts):
    """
    If 'ts' has 'YYYY-MM-DD HH:MM:SS' with no decimal,
    append '.000000' so it becomes 'YYYY-MM-DD HH:MM:SS.ssssss'.
    """
    ts = ts.strip()
    if '.' not in ts:
        # Means there's no microseconds part, so add 6 zeros
        ts += ".000000"
    return ts

def force_uniform_datetime(event_data, tz=None):
    # 1) Convert everything to string & strip
    event_data['timestamp'] = event_data['timestamp'].astype(str).apply(unify_timestamp_str)

    # 2) Parse with a single format that includes microseconds
    event_data['timestamp'] = pd.to_datetime(
        event_data['timestamp'],
        format='%Y-%m-%d %H:%M:%S.%f',
        errors='coerce'
    )

    # 3) (Optional) localize to your tz
    if tz:
        event_data['timestamp'] = event_data['timestamp'].dt.tz_localize(tz)

    return event_data

def calculate_num_events(event_data, participant_df, days=None):
    """
    Returns a Pandas Series with the count of events per participant (patientId).
    If `days` is provided, only counts events more recent than (now - days).
    """
    if isinstance(event_data, list):
        event_data = pd.DataFrame(event_data)

    if 'timestamp' not in event_data.columns:
        raise ValueError("The 'timestamp' column is missing from event_data.")

    
    # 1) Use your helper to unify formats AND localize to Israel time
    event_data = force_uniform_datetime(event_data, tz=israel_tz)
  
    # Optionally filter to last N days
    if days is not None:
        cutoff_time = pd.Timestamp.now(tz=israel_tz) - pd.Timedelta(days=days)
        event_data = event_data[event_data['timestamp'] >= cutoff_time]

    # Count events per patientId
    event_counts = (
        event_data
        .groupby('patientId')
        .size()                  # or .count() if you prefer
        .rename('num_events')
        .reset_index()
    )
    # event_counts now has columns: ['patientId', 'num_events']

    # Merge with participant_df on patientId
    merged = pd.merge(participant_df, event_counts, on='patientId', how='left')
    merged['num_events'] = merged['num_events'].fillna(0)

    # Return the final Series aligned with participant_df rows
    return merged['num_events']

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

def compute_valid_answers_count(questions_data, start_date, end_date):
    """
    Number of valid answers (0-4) in [start_date, end_date], tz-aware.
    """
    df = pd.DataFrame(questions_data)
    if df.empty:
        return 0

    df['timestamp'] = pd.to_datetime(df['timestamp'], errors='coerce')
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