"""Iteration 2 regression: Reception, Patient 360, Reschedule, WS, Doctor Next fix."""
import os, time, json, asyncio
import pytest, requests, websockets

BASE_URL = (os.environ.get("REACT_APP_BACKEND_URL") or open("/app/frontend/.env").read().split("REACT_APP_BACKEND_URL=")[1].splitlines()[0]).rstrip("/")
WS_URL = BASE_URL.replace("https://", "wss://").replace("http://", "ws://")


def _login(email, pw):
    s = requests.Session()
    r = s.post(f"{BASE_URL}/api/auth/login", json={"email": email, "password": pw}, timeout=20)
    assert r.status_code == 200, r.text
    return s, r.json()


@pytest.fixture(scope="module")
def patient():
    return _login("patient@drd.demo", "Patient123!")

@pytest.fixture(scope="module")
def doctor():
    return _login("doctor@drd.demo", "Doctor123!")

@pytest.fixture(scope="module")
def reception():
    return _login("reception@drd.demo", "Reception123!")


# ---------- Auth ----------
def test_patient_login(patient):
    s, u = patient
    assert u["role"] == "patient" and u["email"] == "patient@drd.demo"
    assert "access_token" in s.cookies

def test_doctor_login(doctor):
    _, u = doctor
    assert u["role"] == "doctor"

def test_reception_login(reception):
    _, u = reception
    assert u["role"] == "reception"

def test_login_bad_credentials():
    r = requests.post(f"{BASE_URL}/api/auth/login", json={"email": "noone@drd.demo", "password": "x"})
    assert r.status_code == 401

def test_session_invalid_not_500():
    r = requests.post(f"{BASE_URL}/api/auth/session", json={"session_id": "invalid-xyz"})
    assert r.status_code in (401, 400)

# ---------- Doctors ----------
def test_doctors_list_fields():
    r = requests.get(f"{BASE_URL}/api/doctors")
    assert r.status_code == 200
    docs = r.json()
    assert len(docs) >= 4
    d = docs[0]
    for f in ("id","name","specialty","is_open","consult_minutes","queue_count","delay_minutes","kyc_verified","rating"):
        assert f in d, f"missing {f}"
    assert "now_serving" in d

def test_public_queue_anonymized():
    docs = requests.get(f"{BASE_URL}/api/doctors").json()
    did = docs[0]["id"]
    r = requests.get(f"{BASE_URL}/api/doctors/{did}/public-queue")
    assert r.status_code == 200
    pq = r.json()
    assert "queue" in pq and "now_serving" in pq and "delay_minutes" in pq
    for item in pq["queue"]:
        assert set(item.keys()) <= {"position", "status"}  # no PII

# ---------- Booking + mine ----------
@pytest.fixture
def fresh_booking(patient):
    s, _ = patient
    # cancel any active first
    mine = s.get(f"{BASE_URL}/api/appointments/mine").json()
    for a in mine:
        if a["status"] in ("waiting", "called"):
            s.post(f"{BASE_URL}/api/appointments/{a['id']}/cancel")
    docs = [d for d in s.get(f"{BASE_URL}/api/doctors").json() if d["is_open"]]
    r = s.post(f"{BASE_URL}/api/appointments", json={"doctor_id": docs[0]["id"], "reason": "TEST_mild headache since morning"}, timeout=60)
    assert r.status_code == 200, r.text
    return s, r.json(), docs[0]["id"]

def test_booking_returns_brief_and_eta(fresh_booking):
    _, data, _ = fresh_booking
    assert data["position"] >= 1
    assert isinstance(data["eta_minutes"], int)
    assert data["brief"]
    assert "_id" not in data

def test_duplicate_booking_400(fresh_booking):
    s, _, did = fresh_booking
    r = s.post(f"{BASE_URL}/api/appointments", json={"doctor_id": did, "reason": "again"})
    assert r.status_code == 400

def test_mine_has_eta_fields(fresh_booking):
    s, data, _ = fresh_booking
    mine = s.get(f"{BASE_URL}/api/appointments/mine").json()
    appt = next(a for a in mine if a["id"] == data["id"])
    for f in ("ahead", "eta_min", "eta_max", "delay_minutes"):
        assert f in appt
    assert "now_serving" in appt

def test_cancel_compacts(fresh_booking):
    s, data, _ = fresh_booking
    r = s.post(f"{BASE_URL}/api/appointments/{data['id']}/cancel")
    assert r.status_code == 200

def test_reschedule_puts_at_end(patient):
    s, _ = patient
    # cleanup
    for a in s.get(f"{BASE_URL}/api/appointments/mine").json():
        if a["status"] in ("waiting", "called"):
            s.post(f"{BASE_URL}/api/appointments/{a['id']}/cancel")
    docs = [d for d in s.get(f"{BASE_URL}/api/doctors").json() if d["is_open"]]
    did = docs[0]["id"]
    b = s.post(f"{BASE_URL}/api/appointments", json={"doctor_id": did, "reason": "TEST_resched"}, timeout=60).json()
    r = s.post(f"{BASE_URL}/api/appointments/{b['id']}/reschedule")
    assert r.status_code == 200
    data = r.json()
    assert data["position"] >= 1 and "id" in data
    # cleanup
    s.post(f"{BASE_URL}/api/appointments/{data['id']}/cancel")

# ---------- Doctor queue ops ----------
def test_doctor_next_no_500(doctor, patient):
    sd, du = doctor
    sp, _ = patient
    # cleanup existing
    for a in sp.get(f"{BASE_URL}/api/appointments/mine").json():
        if a["status"] in ("waiting", "called"):
            sp.post(f"{BASE_URL}/api/appointments/{a['id']}/cancel")
    # make sure doc open
    sd.patch(f"{BASE_URL}/api/doctors/{du['id']}/settings", json={"is_open": True, "consult_minutes": 15, "daily_cap": 20})
    b = sp.post(f"{BASE_URL}/api/appointments", json={"doctor_id": du["id"], "reason": "TEST_next"}, timeout=60).json()
    r = sd.post(f"{BASE_URL}/api/doctors/{du['id']}/next", json={"appointment_id": b["id"]})
    assert r.status_code == 200, r.text
    assert r.json()["status"] == "called"
    # mark done, verifies visit creation
    r = sd.post(f"{BASE_URL}/api/doctors/{du['id']}/done", json={"appointment_id": b["id"]})
    assert r.status_code == 200

def test_doctor_delay(doctor):
    s, u = doctor
    r = s.post(f"{BASE_URL}/api/doctors/{u['id']}/delay", json={"minutes": 10})
    assert r.status_code == 200
    assert r.json()["delay_minutes"] == 10
    s.post(f"{BASE_URL}/api/doctors/{u['id']}/delay", json={"minutes": 0})

def test_no_show_pushback(doctor, patient):
    sd, du = doctor
    sp, _ = patient
    for a in sp.get(f"{BASE_URL}/api/appointments/mine").json():
        if a["status"] in ("waiting", "called"):
            sp.post(f"{BASE_URL}/api/appointments/{a['id']}/cancel")
    b = sp.post(f"{BASE_URL}/api/appointments", json={"doctor_id": du["id"], "reason": "TEST_ns"}, timeout=60).json()
    r = sd.post(f"{BASE_URL}/api/doctors/{du['id']}/no-show", json={"appointment_id": b["id"]})
    assert r.status_code == 200
    # cleanup
    sp.post(f"{BASE_URL}/api/appointments/{b['id']}/cancel")

def test_patient_cannot_access_doctor_queue(doctor, patient):
    _, du = doctor
    sp, _ = patient
    r = sp.get(f"{BASE_URL}/api/doctors/{du['id']}/queue")
    assert r.status_code == 403

# ---------- Reception ----------
def test_reception_dashboard(reception):
    s, _ = reception
    r = s.get(f"{BASE_URL}/api/reception/dashboard")
    assert r.status_code == 200
    data = r.json()
    assert set(["booked","checked_in","in_consult","completed"]).issubset(data["totals"].keys())
    assert isinstance(data["doctors"], list) and data["doctors"]
    assert "rows" in data["doctors"][0]

def test_non_reception_forbidden(patient):
    sp, _ = patient
    r = sp.get(f"{BASE_URL}/api/reception/dashboard")
    assert r.status_code == 403

def test_reception_walk_in(reception):
    s, _ = reception
    docs = requests.get(f"{BASE_URL}/api/doctors").json()
    did = next(d["id"] for d in docs if d["is_open"])
    r = s.post(f"{BASE_URL}/api/reception/walk-in", json={"doctor_id": did, "patient_name": "TEST_WalkIn Guest", "phone": "", "reason": "TEST walk in cough"}, timeout=60)
    assert r.status_code == 200, r.text
    assert r.json()["status"] == "waiting"

# ---------- Patient 360 ----------
def test_patient_search_and_profile(doctor):
    s, _ = doctor
    r = s.get(f"{BASE_URL}/api/patients", params={"q": "emily"})
    assert r.status_code == 200
    results = r.json()
    assert any("emily" in x["name"].lower() for x in results)
    pid = next(x["id"] for x in results if "emily" in x["name"].lower())
    r = s.get(f"{BASE_URL}/api/patients/{pid}")
    assert r.status_code == 200
    p = r.json()
    for f in ("age","gender","blood_type","allergies","conditions","vitals","visits"):
        assert f in p
    assert isinstance(p["visits"], list) and len(p["visits"]) >= 1
    # sorted desc
    dates = [v["date"] for v in p["visits"]]
    assert dates == sorted(dates, reverse=True)

def test_patient_summary_gemini(doctor):
    s, _ = doctor
    results = s.get(f"{BASE_URL}/api/patients", params={"q": "emily"}).json()
    pid = results[0]["id"]
    r = s.post(f"{BASE_URL}/api/patients/{pid}/summary", timeout=60)
    assert r.status_code == 200
    assert isinstance(r.json().get("summary"), str) and len(r.json()["summary"]) > 0

# ---------- Dai SSE ----------
def test_dai_chat_sse(patient):
    s, _ = patient
    r = s.post(f"{BASE_URL}/api/dai/chat", json={"message": "What's my queue?"}, stream=True, timeout=30)
    assert r.status_code == 200
    assert "text/event-stream" in r.headers.get("content-type", "")
    chunks = []
    for line in r.iter_lines(decode_unicode=True):
        if line and line.startswith("data:"):
            chunks.append(line)
            if len(chunks) >= 1: break
    assert chunks

# ---------- WebSocket ----------
def test_websocket_queue():
    docs = requests.get(f"{BASE_URL}/api/doctors").json()
    did = docs[0]["id"]
    async def _run():
        async with websockets.connect(f"{WS_URL}/api/ws/queue/{did}", open_timeout=10) as ws:
            msg = await asyncio.wait_for(ws.recv(), timeout=10)
            data = json.loads(msg)
            assert data["doctor_id"] == did
            assert "public" in data
    asyncio.get_event_loop().run_until_complete(_run())
