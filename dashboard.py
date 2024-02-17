#  Int
# אינדקס
# string
# מזהה משתתף
# string
# כינוי / שם ???


# bool
# אמפטיקה
# int
# אירועים

# int
# מילוי שאלונים
# int
# מצב בטריה אמפטיקה
# Int
# מצב בטריה סלולרי
# Datetime
# קשר אחרון
# string
# מלווה


import random
from datetime import date

import numpy as np
import pandas as pd
import streamlit as st

st.set_page_config("Profiles", "👤")


@st.cache_data
def get_profile_dataset(number_of_items: int = 100, seed: int = 0) -> pd.DataFrame:
    new_data = []

    def calculate_age(born):
        today = date.today()
        return (
            today.year - born.year - ((today.month, today.day) < (born.month, born.day))
        )

    from faker import Faker

    fake = Faker()
    random.seed(seed)
    Faker.seed(seed)

    for i in range(number_of_items):
        profile = fake.profile()
        new_data.append(
            {
                "name": profile["name"],
                "nickname": profile["username"],
                "gender": random.choice(["male", "female", "other", None]),
                "id": profile["ssn"],
                "emp_connected": random.choice([True, False]),
                "events_24h": np.random.randint(0, 15),
                "battery_status": round(random.uniform(0, 100), 2),

                "daily_activity": np.random.randint(0, 2, 24),
            }
        )

    profile_df = pd.DataFrame(new_data)
    profile_df["gender"] = profile_df["gender"].astype("category")
    return profile_df


column_configuration = {
    "name": st.column_config.TextColumn(
        "User Name", help="The name of the user", max_chars=100
    ),
    "nickname": st.column_config.TextColumn(
        "User Nickname", help="The nickname of the user", max_chars=100
    ),
    "gender": st.column_config.SelectboxColumn(
        "Gender", options=["male", "female", "other"]
    ),
    "id": st.column_config.TextColumn(
        "User ID", help="The id of the user", max_chars=20
    ),
    "emp_connected": st.column_config.CheckboxColumn("Empatica connected?", help="Is the user active?"),
    "events_24h": st.column_config.NumberColumn(
            "Events (24h)",
            min_value=0,
            max_value=100,
            format="%d events",
            help="The user's events for last 24 hours",
    ),
    "battery_status": st.column_config.ProgressColumn(
        "Battery", min_value=0, max_value=100, format="%d"
    ),


    "daily_activity": st.column_config.BarChartColumn(
        "Activity (daily)",
        help="The user's activity in the last 25 days",
        width="medium",
        y_min=0,
        y_max=1,
    ),
    
}

data = get_profile_dataset()

# Display the dataframe and allow the user to stretch the dataframe
st.checkbox("Use container width", value=False, key="use_container_width")


st.data_editor(
    data,
    column_config=column_configuration,
    use_container_width=st.session_state.use_container_width,
    hide_index=True,
    num_rows="fixed",
)
