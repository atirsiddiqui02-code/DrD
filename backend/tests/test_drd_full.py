"""Full Dr.D backend test suite covering auth, doctors, queue, Dai, reviews, WS."""
import os, json, time, uuid
import pytest, requests, websocket

BASE = os.environ.get("REACT_APP_BACKEND_URL", "https://queue-dr-d.preview.emergentagent.com").rstrip("/")
WS_BASE = BASE.replace("https://", "wss://").replace("http://", "ws://")

PATIENT = ("patient@drd.demo", "Patient123!")
DOCTOR = ("doctor@drd.demo", "Doctor123!")
DOCTOR2 = ("doctor2@drd.demo", "Doctor123!")


def _session(creds=None):
    s = requests.Session()
    if creds:
        r = s.post(f"{BASE}/api/auth/login", json={"email": creds[0], "password": creds[1]})
        assert r.status_code == 200, f"Login {creds[0]} failed: {r.status_code} {r.text}"
    return s


@pytest.fixture(scope="module")
def patient_sess():
    return _session(PATIENT)


@pytest.fixture(scope="module")
def doctor_sess():
    return _session(DOCTOR)


@pytest.fixture(scope="module")
def doctor_id(doctor_sess):
    return doctor_sess.get(f"{BASE}/api/auth/me").json()["id"]


@pytest.fixture(scope="module")
def patient_id(patient_sess):
    return patient_sess.get(f"{BASE}/api/auth/me").json()["id"]


# --- Auth ---
class TestAuth:
    def test_login_patient(self, patient_sess):
        me = patient_sess.get(f"{BASE}/api/auth/me").json()
        assert me["role"] == "patient"
        assert me["email"] == PATIENT[0]

    def test_login_doctor(self, doctor_sess):
        me = doctor_sess.get(f"{BASE}/api/auth/me").json()
        assert me["role"] == "doctor"

    def test_login_bad(self):
        r = requests.post(f"{BASE}/api/auth/login", json={"email": PATIENT[0], "password": "wrong"})
        assert r.status_code == 401

    def test_me_unauth(self):
        r = requests.get(f"{BASE}/api/auth/me")
        assert r.status_code == 401


# --- Doctors ---
class TestDoctors:
    def test_list(self):
        r = requests.get(f"{BASE}/api/doctors")
        assert r.status_code == 200
        data = r.json()
        names = [d["name"] for d in data]
        assert "Dr. Maya Chen" in names
        assert "Dr. Raj Mehta" in names
        for d in data:
            assert "rating" in d and isinstance(d["rating"], dict)
            assert d["kyc_verified"] is True
            assert "is_open" in d and "consult_minutes" in d
            assert "queue_count" in d and "now_serving" in d


# --- Clean state & book ---
def _reset(doctor_sess, doctor_id, patient_sess):
    """Clean active appts for patient by cancellation."""
    appts = patient_sess.get(f"{BASE}/api/appointments/mine").json()
    for a in appts:
        if a.get("status") in ("waiting", "called"):
            patient_sess.post(f"{BASE}/api/appointments/{a['id']}/cancel")


class TestBookingFlow:
    def test_book(self, patient_sess, doctor_sess, doctor_id):
        _reset(doctor_sess, doctor_id, patient_sess)
        r = patient_sess.post(f"{BASE}/api/appointments", json={"doctor_id": doctor_id, "reason": "mild cough and fever for 3 days"})
        assert r.status_code == 200, r.text
        appt = r.json()
        assert "id" in appt and "position" in appt and "eta_minutes" in appt
        assert isinstance(appt.get("brief"), str) and len(appt["brief"]) > 0

    def test_duplicate_active_blocked(self, patient_sess, doctor_id):
        r = patient_sess.post(f"{BASE}/api/appointments", json={"doctor_id": doctor_id, "reason": "again"})
        assert r.status_code == 400

    def test_mine(self, patient_sess):
        r = patient_sess.get(f"{BASE}/api/appointments/mine")
        assert r.status_code == 200
        docs = r.json()
        assert any(a.get("status") in ("waiting", "called") for a in docs)
        a = docs[0]
        for k in ("ahead", "eta_min", "eta_max", "now_serving", "delay_minutes"):
            assert k in a

    def test_public_queue(self, doctor_id):
        r = requests.get(f"{BASE}/api/doctors/{doctor_id}/public-queue")
        assert r.status_code == 200
        pq = r.json()
        assert "queue" in pq and "now_serving" in pq
        for item in pq["queue"]:
            assert "patient_name" not in item
            assert "position" in item and "status" in item


# --- Doctor queue control ---
class TestDoctorControl:
    def test_delay(self, doctor_sess, patient_sess, doctor_id):
        r = doctor_sess.post(f"{BASE}/api/doctors/{doctor_id}/delay", json={"minutes": 15})
        assert r.status_code == 200
        time.sleep(0.3)
        mine = patient_sess.get(f"{BASE}/api/appointments/mine").json()
        active = [a for a in mine if a.get("status") in ("waiting", "called")]
        assert active and active[0]["delay_minutes"] == 15
        pq = requests.get(f"{BASE}/api/doctors/{doctor_id}/public-queue").json()
        assert pq["delay_minutes"] == 15
        # reset
        doctor_sess.post(f"{BASE}/api/doctors/{doctor_id}/delay", json={"minutes": 0})

    def test_next_and_done(self, doctor_sess, patient_sess, doctor_id):
        mine = patient_sess.get(f"{BASE}/api/appointments/mine").json()
        active = [a for a in mine if a.get("status") in ("waiting", "called")]
        appt_id = active[0]["id"]
        r = doctor_sess.post(f"{BASE}/api/doctors/{doctor_id}/next", json={"appointment_id": appt_id})
        assert r.status_code == 200, r.text
        body = r.json()
        assert body["status"] == "called"
        assert "_id" not in body
        # Review should still fail (status=called, not done)
        rev_fail = patient_sess.post(f"{BASE}/api/doctors/{doctor_id}/review", json={"rating": 5, "comment": "x"})
        assert rev_fail.status_code == 400
        # done
        r2 = doctor_sess.post(f"{BASE}/api/doctors/{doctor_id}/done", json={"appointment_id": appt_id})
        assert r2.status_code == 200
        # review succeeds
        rev_ok = patient_sess.post(f"{BASE}/api/doctors/{doctor_id}/review", json={"rating": 5, "comment": "great"})
        assert rev_ok.status_code == 200
        rating = rev_ok.json()["rating"]
        assert rating["count"] >= 1 and rating["avg"] is not None
        detail = requests.get(f"{BASE}/api/doctors/{doctor_id}").json()
        assert detail["rating"]["count"] >= 1


# --- Cancel / Reschedule compaction ---
class TestCompactionAndNoShow:
    def test_cancel_compacts(self, patient_sess, doctor_sess, doctor_id):
        _reset(doctor_sess, doctor_id, patient_sess)
        # patient1 books via session; create second patient via register
        p2 = requests.Session()
        email = f"TEST_{uuid.uuid4().hex[:8]}@drd.demo"
        r = p2.post(f"{BASE}/api/auth/register", json={"name": "Test P2", "email": email, "password": "Password123!", "role": "patient"})
        assert r.status_code == 200
        a1 = patient_sess.post(f"{BASE}/api/appointments", json={"doctor_id": doctor_id, "reason": "flu"}).json()
        a2 = p2.post(f"{BASE}/api/appointments", json={"doctor_id": doctor_id, "reason": "headache"}).json()
        assert a2["position"] > a1["position"]
        before = a2["position"]
        patient_sess.post(f"{BASE}/api/appointments/{a1['id']}/cancel")
        mine2 = p2.get(f"{BASE}/api/appointments/mine").json()
        active = [x for x in mine2 if x["status"] in ("waiting", "called") and x["id"] == a2["id"]]
        assert active and active[0]["position"] == before - 1

    def test_reschedule(self, patient_sess, doctor_sess, doctor_id):
        _reset(doctor_sess, doctor_id, patient_sess)
        a = patient_sess.post(f"{BASE}/api/appointments", json={"doctor_id": doctor_id, "reason": "cough"}).json()
        r = patient_sess.post(f"{BASE}/api/appointments/{a['id']}/reschedule")
        assert r.status_code == 200, r.text
        body = r.json()
        assert body["id"] != a["id"]
        _reset(doctor_sess, doctor_id, patient_sess)

    def test_no_show_pushback_and_cancel(self, patient_sess, doctor_sess, doctor_id):
        _reset(doctor_sess, doctor_id, patient_sess)
        a = patient_sess.post(f"{BASE}/api/appointments", json={"doctor_id": doctor_id, "reason": "test"}).json()
        # 1st pushback
        r1 = doctor_sess.post(f"{BASE}/api/doctors/{doctor_id}/no-show", json={"appointment_id": a["id"]})
        assert r1.status_code == 200
        # 2nd pushback
        r2 = doctor_sess.post(f"{BASE}/api/doctors/{doctor_id}/no-show", json={"appointment_id": a["id"]})
        assert r2.status_code == 200
        # 3rd => cancels
        r3 = doctor_sess.post(f"{BASE}/api/doctors/{doctor_id}/no-show", json={"appointment_id": a["id"]})
        assert r3.status_code == 200
        mine = patient_sess.get(f"{BASE}/api/appointments/mine").json()
        matched = [x for x in mine if x["id"] == a["id"]]
        assert matched and matched[0]["status"] == "cancelled"


# --- Dai ---
class TestDai:
    def test_brief(self, patient_sess):
        r = patient_sess.post(f"{BASE}/api/dai/brief", json={"reason": "severe headache 2 days with nausea"})
        assert r.status_code == 200
        assert isinstance(r.json().get("brief"), str) and len(r.json()["brief"]) > 10

    def test_chat_stream(self, patient_sess):
        # streaming SSE
        with patient_sess.post(f"{BASE}/api/dai/chat", json={"message": "What is my eta?"}, stream=True, timeout=30) as r:
            assert r.status_code == 200
            got = False
            for line in r.iter_lines(decode_unicode=True):
                if line and line.startswith("data:"):
                    got = True
                    break
            assert got


# --- Websocket ---
class TestWebSocket:
    def test_ws(self, doctor_id):
        url = f"{WS_BASE}/api/ws/queue/{doctor_id}"
        ws = websocket.create_connection(url, timeout=10)
        msg = ws.recv()
        data = json.loads(msg)
        assert data["doctor_id"] == doctor_id
        assert "public" in data
        # No patient_name leaked
        for item in data["public"]["queue"]:
            assert "patient_name" not in item
        ws.close()
