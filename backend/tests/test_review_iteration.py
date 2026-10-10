import os
import requests

BASE_URL = os.environ.get("REACT_APP_BACKEND_URL", "https://queue-dr-d.preview.emergentagent.com").rstrip("/")

def login(email, password):
    s = requests.Session()
    r = s.post(f"{BASE_URL}/api/auth/login", json={"email": email, "password": password}, timeout=20)
    assert r.status_code == 200, r.text
    return s, r.json()

def test_patient_auth_and_discovery():
    s, user = login("patient@drd.demo", "Patient123!")
    assert user["role"] == "patient"
    assert "access_token" in s.cookies
    assert s.get(f"{BASE_URL}/api/auth/me").json()["email"] == "patient@drd.demo"
    doctors = s.get(f"{BASE_URL}/api/doctors").json()
    assert doctors and any(d["is_open"] for d in doctors)

def test_doctor_controls_and_settings():
    s, user = login("doctor@drd.demo", "Doctor123!")
    assert user["role"] == "doctor"
    r = s.patch(f"{BASE_URL}/api/doctors/{user['id']}/settings", json={"is_open": True, "consult_minutes": 20, "daily_cap": 20})
    assert r.status_code == 200 and r.json()["consult_minutes"] == 20
    q = s.get(f"{BASE_URL}/api/doctors/{user['id']}/queue")
    assert q.status_code == 200 and isinstance(q.json(), list)

def test_patient_booking_private_fields_and_cancel():
    s, _ = login("patient@drd.demo", "Patient123!")
    doctors = [d for d in s.get(f"{BASE_URL}/api/doctors").json() if d["is_open"]]
    assert doctors
    r = s.post(f"{BASE_URL}/api/appointments", json={"doctor_id": doctors[0]["id"], "reason": "TEST_review symptom"}, timeout=60)
    assert r.status_code == 200, r.text
    data = r.json()
    assert data["position"] >= 1 and isinstance(data["eta_minutes"], int)
    assert data["brief"]
    assert "_id" not in data and "password_hash" not in data
    mine = s.get(f"{BASE_URL}/api/appointments/mine").json()
    appt = next(x for x in mine if x["id"] == data["id"])
    assert appt["patient_id"] == data["patient_id"] and "_id" not in appt
    cancel = s.post(f"{BASE_URL}/api/appointments/{data['id']}/cancel")
    assert cancel.status_code == 200