import requests
from private_config import BASE_URL

def fetch_participants():
    """Fetches participant data from the API."""
    url = f"{BASE_URL}/participants/"
    response = requests.get(url)
    if response.ok:
        return response.json()
    else:
        return None

def update_participant_to_db(patientId, updates):
    """Updates participant data on the API."""
    url = f"{BASE_URL}/participants/"
    headers = {'Content-Type': 'application/json'}
    response = requests.patch(url, json=updates, headers=headers)
    return response

def get_questions(patient_id):
    url = f"{BASE_URL}/questions?patientId={patient_id}"
    response = requests.get(url)
    if response.status_code == 200:
        return response.json()
    else:
  #      st.error("Failed to retrieve questions.")
        return None
    
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

# Add other API functions here similarly
