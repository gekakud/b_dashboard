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

# Add other API functions here similarly
