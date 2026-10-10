from dotenv import load_dotenv
from pathlib import Path
load_dotenv(Path(__file__).parent / ".env")

import os, uuid, json, logging, bcrypt, jwt, httpx
from datetime import datetime, timezone, timedelta
from typing import Optional
from bson import ObjectId
from pymongo import ReturnDocument
from fastapi import FastAPI, APIRouter, HTTPException, Request, Response, WebSocket, WebSocketDisconnect, Depends
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import StreamingResponse
from motor.motor_asyncio import AsyncIOMotorClient
from pydantic import BaseModel, Field
from emergentintegrations.llm.chat import LlmChat, UserMessage, TextDelta, StreamDone

ROOT = Path(__file__).parent
client = AsyncIOMotorClient(os.environ["MONGO_URL"])
db = client[os.environ["DB_NAME"]]
app = FastAPI(title="Dr.D API")
api = APIRouter(prefix="/api")
JWT_SECRET = os.environ["JWT_SECRET"]
ALGORITHM = "HS256"
connections = {}
failed_logins = {}
logger = logging.getLogger("drd")

def now(): return datetime.now(timezone.utc)
def today(): return now().date().isoformat()
def public_user(user):
    return {
        "id": str(user.get("_id") or user.get("id")),
        "name": user["name"],
        "email": user["email"],
        "role": user["role"],
        "approved": user.get("approved", True),
        "specialty": user.get("specialty"),
        "picture": user.get("picture"),
    }

def hash_password(value): return bcrypt.hashpw(value.encode(), bcrypt.gensalt()).decode()
def verify_password(value, hashed): return bcrypt.checkpw(value.encode(), hashed.encode())
def jwt_token(user): return jwt.encode({"sub": str(user["_id"]), "exp": now()+timedelta(days=7)}, JWT_SECRET, algorithm=ALGORITHM)

def set_auth_cookie(response: Response, key: str, value: str, max_age: int = 604800):
    response.set_cookie(key=key, value=value, httponly=True, secure=True, samesite="none", max_age=max_age, path="/")

async def resolve_user(request: Request):
    # 1. Try Google session token
    session_token = request.cookies.get("session_token")
    if session_token:
        sess = await db.user_sessions.find_one({"session_token": session_token}, {"_id": 0})
        if sess:
            expires_at = sess["expires_at"]
            if isinstance(expires_at, str):
                expires_at = datetime.fromisoformat(expires_at)
            if expires_at.tzinfo is None:
                expires_at = expires_at.replace(tzinfo=timezone.utc)
            if expires_at > now():
                user = await db.users.find_one({"_id": ObjectId(sess["user_id"])})
                if user:
                    return user
    # 2. JWT (email/password)
    raw = request.cookies.get("access_token") or request.headers.get("Authorization", "").replace("Bearer ", "")
    if not raw:
        return None
    try:
        payload = jwt.decode(raw, JWT_SECRET, algorithms=[ALGORITHM])
    except jwt.InvalidTokenError:
        return None
    return await db.users.find_one({"_id": ObjectId(payload["sub"])})

async def current_user(request: Request):
    user = await resolve_user(request)
    if not user:
        raise HTTPException(401, "Please sign in to continue")
    if user.get("role") == "doctor" and not user.get("approved", False):
        raise HTTPException(403, "Doctor account is awaiting admin approval")
    return user

# ----- Models -----
class Register(BaseModel):
    name: str; email: str; password: str; role: str = "patient"; specialty: Optional[str] = None
class WalkIn(BaseModel):
    doctor_id: str; patient_name: str; phone: Optional[str] = ""; reason: str
class Visit(BaseModel):
    condition: str; medications: Optional[list] = []; notes: Optional[str] = ""
class Login(BaseModel): email: str; password: str
class Booking(BaseModel): doctor_id: str; reason: str
class DoctorSettings(BaseModel): is_open: bool; consult_minutes: int = Field(15, ge=5, le=120); daily_cap: Optional[int] = Field(None, ge=1)
class QueueAction(BaseModel): appointment_id: str
class AssistantRequest(BaseModel): message: str
class Review(BaseModel): rating: int = Field(..., ge=1, le=5); comment: Optional[str] = ""
class Delay(BaseModel): minutes: int = Field(..., ge=0, le=240)
class SessionExchange(BaseModel): session_id: str

# ----- AI -----
async def generate_brief(reason: str):
    chat = LlmChat(
        api_key=os.environ["EMERGENT_LLM_KEY"],
        session_id=f"brief-{uuid.uuid4()}",
        system_message="You are Dai, a clinical intake assistant. Convert the patient's reason into a concise structured pre-visit brief. Never diagnose, prescribe, or give medical advice. Return plain text with Symptoms, Duration, Context, and Suggested focus.",
    ).with_model("gemini", "gemini-3-flash-preview")
    text = ""
    async for event in chat.stream_message(UserMessage(text=reason)):
        if isinstance(event, TextDelta): text += event.content
        if isinstance(event, StreamDone): break
    return text

# ----- Root -----
@api.get("/")
async def root(): return {"message": "Dr.D is ready"}

# ----- Email/Password Auth -----
@api.post("/auth/register")
async def register(data: Register, response: Response):
    email = data.email.lower().strip()
    if await db.users.find_one({"email": email}):
        raise HTTPException(409, "An account with that email already exists")
    role = data.role if data.role in ("patient", "doctor", "reception") else "patient"
    user = {
        "name": data.name, "email": email,
        "password_hash": hash_password(data.password), "role": role,
        "approved": role == "patient",
        "specialty": data.specialty or "General Practice",
        "is_open": False, "consult_minutes": 15, "daily_cap": None,
        "created_at": now().isoformat(),
    }
    result = await db.users.insert_one(user); user["_id"] = result.inserted_id
    set_auth_cookie(response, "access_token", jwt_token(user))
    return public_user(user)

@api.post("/auth/login")
async def login(data: Login, response: Response):
    email = data.email.lower().strip()
    attempt = failed_logins.get(email)
    if attempt and attempt["until"] > now().timestamp():
        raise HTTPException(429, "Too many attempts. Please try again in 15 minutes")
    user = await db.users.find_one({"email": email})
    if not user or not user.get("password_hash") or not verify_password(data.password, user["password_hash"]):
        count = (attempt or {"count": 0})["count"] + 1
        failed_logins[email] = {"count": count, "until": now().timestamp()+900 if count >= 5 else 0}
        raise HTTPException(401, "Email or password is incorrect")
    failed_logins.pop(email, None)
    if user.get("role") == "doctor" and not user.get("approved", False):
        raise HTTPException(403, "Doctor account is awaiting admin approval")
    set_auth_cookie(response, "access_token", jwt_token(user))
    return public_user(user)

@api.post("/auth/logout")
async def logout(request: Request, response: Response):
    session_token = request.cookies.get("session_token")
    if session_token:
        await db.user_sessions.delete_one({"session_token": session_token})
    response.delete_cookie("access_token", path="/")
    response.delete_cookie("session_token", path="/")
    return {"ok": True}

@api.get("/auth/me")
async def me(user=Depends(current_user)): return public_user(user)

# ----- Google OAuth (Emergent) -----
@api.post("/auth/session")
async def exchange_session(data: SessionExchange, response: Response):
    # REMINDER: DO NOT HARDCODE THE URL, OR ADD ANY FALLBACKS OR REDIRECT URLS, THIS BREAKS THE AUTH
    async with httpx.AsyncClient(timeout=10) as http:
        resp = await http.get(
            "https://demobackend.emergentagent.com/auth/v1/env/oauth/session-data",
            headers={"X-Session-ID": data.session_id},
        )
    if resp.status_code != 200:
        raise HTTPException(401, "Unable to verify Google session")
    payload = resp.json()
    email = (payload.get("email") or "").lower().strip()
    name = payload.get("name") or email.split("@")[0]
    picture = payload.get("picture")
    session_token = payload.get("session_token")
    if not email or not session_token:
        raise HTTPException(401, "Invalid session payload")
    user = await db.users.find_one({"email": email})
    if not user:
        user = {
            "name": name, "email": email, "password_hash": None,
            "role": "patient", "approved": True, "picture": picture,
            "specialty": None, "is_open": False, "consult_minutes": 15,
            "daily_cap": None, "created_at": now().isoformat(),
        }
        result = await db.users.insert_one(user); user["_id"] = result.inserted_id
    else:
        await db.users.update_one({"_id": user["_id"]}, {"$set": {"picture": picture, "name": user.get("name") or name}})
    await db.user_sessions.insert_one({
        "session_token": session_token,
        "user_id": str(user["_id"]),
        "expires_at": now() + timedelta(days=7),
        "created_at": now(),
    })
    set_auth_cookie(response, "session_token", session_token)
    return public_user(user)

# ----- Doctors -----
async def doctor_rating(doctor_id: str):
    agg = await db.reviews.aggregate([
        {"$match": {"doctor_id": doctor_id}},
        {"$group": {"_id": None, "avg": {"$avg": "$rating"}, "count": {"$sum": 1}}},
    ]).to_list(1)
    if not agg: return {"avg": None, "count": 0}
    return {"avg": round(agg[0]["avg"], 1), "count": agg[0]["count"]}

async def doctor_card(d, include_rating=True):
    doctor_id = str(d["_id"])
    day = today()
    queue_count = await db.appointments.count_documents({"doctor_id": doctor_id, "day": day, "status": {"$in": ["waiting", "called"]}})
    now_serving = await db.appointments.find_one(
        {"doctor_id": doctor_id, "day": day, "status": "called"},
        {"_id": 0, "position": 1},
    )
    card = {
        "id": doctor_id,
        "name": d["name"],
        "specialty": d.get("specialty", "General Practice"),
        "is_open": d.get("is_open", False),
        "consult_minutes": d.get("consult_minutes", 15),
        "daily_cap": d.get("daily_cap"),
        "queue_count": queue_count,
        "now_serving": now_serving["position"] if now_serving else None,
        "delay_minutes": d.get("delay_minutes", 0),
        "bio": d.get("bio") or "Family practice physician focused on calm, patient-first care.",
        "kyc_verified": d.get("kyc_verified", True),
        "picture": d.get("picture"),
    }
    if include_rating:
        card["rating"] = await doctor_rating(doctor_id)
    return card

@api.get("/doctors")
async def doctors(q: str = ""):
    query = {"role": "doctor", "approved": True}
    if q:
        query["$or"] = [{"name": {"$regex": q, "$options": "i"}}, {"specialty": {"$regex": q, "$options": "i"}}]
    users = await db.users.find(query, {"password_hash": 0}).to_list(100)
    return [await doctor_card(d) for d in users]

@api.get("/doctors/{doctor_id}")
async def doctor_detail(doctor_id: str):
    d = await db.users.find_one({"_id": ObjectId(doctor_id), "role": "doctor", "approved": True})
    if not d: raise HTTPException(404, "Doctor not found")
    recent = await db.reviews.find({"doctor_id": doctor_id}, {"_id": 0}).sort("created_at", -1).limit(5).to_list(5)
    card = await doctor_card(d)
    card["reviews"] = recent
    return card

# ----- Queue core -----
async def queue_snapshot(doctor_id: str):
    items = await db.appointments.find(
        {"doctor_id": doctor_id, "day": today(), "status": {"$in": ["waiting", "called"]}},
        {"_id": 0},
    ).sort("position", 1).to_list(100)
    return items

async def public_queue(doctor_id: str):
    doc = await db.users.find_one({"_id": ObjectId(doctor_id)})
    if not doc: raise HTTPException(404, "Doctor not found")
    items = await queue_snapshot(doctor_id)
    anonymized = [{"position": i["position"], "status": i["status"]} for i in items]
    now_serving = next((i["position"] for i in items if i["status"] == "called"), None)
    return {
        "doctor_id": doctor_id,
        "doctor_name": doc["name"],
        "consult_minutes": doc.get("consult_minutes", 15),
        "delay_minutes": doc.get("delay_minutes", 0),
        "now_serving": now_serving,
        "queue": anonymized,
    }

@api.get("/doctors/{doctor_id}/public-queue")
async def public_queue_route(doctor_id: str):
    return await public_queue(doctor_id)

async def broadcast(doctor_id: str):
    payload = json.dumps({"doctor_id": doctor_id, "queue": await queue_snapshot(doctor_id), "public": await public_queue(doctor_id)})
    dead = []
    for ws, socket_doctor_id in list(connections.items()):
        if socket_doctor_id != doctor_id: continue
        try: await ws.send_text(payload)
        except Exception: dead.append(ws)
    for ws in dead: connections.pop(ws, None)

# ----- Appointments -----
@api.post("/appointments")
async def book(data: Booking, user=Depends(current_user)):
    if user["role"] != "patient": raise HTTPException(403, "Only patients can book appointments")
    doctor = await db.users.find_one({"_id": ObjectId(data.doctor_id), "role": "doctor", "approved": True})
    if not doctor or not doctor.get("is_open"):
        raise HTTPException(400, "This doctor's queue is not open")
    day = today()
    active = await db.appointments.count_documents({"doctor_id": data.doctor_id, "day": day, "status": {"$in": ["waiting", "called"]}})
    if doctor.get("daily_cap") and active >= doctor["daily_cap"]:
        raise HTTPException(400, "Today's queue is full")
    existing = await db.appointments.find_one({"patient_id": str(user["_id"]), "day": day, "status": {"$in": ["waiting", "called"]}}, {"_id": 0})
    if existing:
        raise HTTPException(400, "You already have an active appointment today")
    position = active + 1
    brief_text = "Dai brief will be prepared before the consultation."
    try: brief_text = await generate_brief(data.reason)
    except Exception as exc: logger.warning("Dai brief unavailable: %s", exc)
    appt = {
        "id": str(uuid.uuid4()),
        "doctor_id": data.doctor_id,
        "doctor_name": doctor["name"],
        "patient_id": str(user["_id"]),
        "patient_name": user["name"],
        "reason": data.reason,
        "brief": brief_text,
        "position": position,
        "status": "waiting",
        "day": day,
        "pushbacks": 0,
        "created_at": now().isoformat(),
    }
    await db.appointments.insert_one(appt)
    await broadcast(data.doctor_id)
    return {**{k: v for k, v in appt.items() if k != "_id"}, "eta_minutes": (position-1)*doctor.get("consult_minutes", 15)}

@api.get("/appointments/mine")
async def mine(user=Depends(current_user)):
    docs = await db.appointments.find(
        {"patient_id": str(user["_id"]), "day": today()},
        {"_id": 0},
    ).sort("created_at", -1).to_list(20)
    for item in docs:
        doctor = await db.users.find_one({"_id": ObjectId(item["doctor_id"])})
        ahead = await db.appointments.count_documents({
            "doctor_id": item["doctor_id"],
            "day": item["day"],
            "status": {"$in": ["waiting", "called"]},
            "position": {"$lt": item["position"]},
        })
        now_serving = await db.appointments.find_one(
            {"doctor_id": item["doctor_id"], "day": item["day"], "status": "called"},
            {"_id": 0, "position": 1},
        )
        consult = (doctor or {}).get("consult_minutes", 15)
        delay = (doctor or {}).get("delay_minutes", 0)
        item.update({
            "doctor_name": (doctor or {}).get("name", "Doctor"),
            "doctor_specialty": (doctor or {}).get("specialty", "General Practice"),
            "ahead": ahead,
            "eta_min": ahead * consult + delay,
            "eta_max": ahead * consult + delay + consult,
            "consult_minutes": consult,
            "delay_minutes": delay,
            "now_serving": now_serving["position"] if now_serving else None,
        })
    return docs

@api.post("/appointments/{appointment_id}/cancel")
async def cancel_appointment(appointment_id: str, user=Depends(current_user)):
    appt = await db.appointments.find_one({"id": appointment_id, "patient_id": str(user["_id"]), "status": {"$in": ["waiting", "called"]}}, {"_id": 0})
    if not appt: raise HTTPException(404, "Appointment is already complete or cancelled")
    await db.appointments.update_one({"id": appointment_id}, {"$set": {"status": "cancelled", "cancel_reason": "Cancelled by patient"}})
    await db.appointments.update_many(
        {"doctor_id": appt["doctor_id"], "day": appt["day"], "status": {"$in": ["waiting", "called"]}, "position": {"$gt": appt["position"]}},
        {"$inc": {"position": -1}},
    )
    await broadcast(appt["doctor_id"])
    return {"ok": True}

@api.post("/appointments/{appointment_id}/reschedule")
async def reschedule_appointment(appointment_id: str, user=Depends(current_user)):
    old = await db.appointments.find_one({"id": appointment_id, "patient_id": str(user["_id"]), "status": {"$in": ["waiting", "called"]}}, {"_id": 0})
    if not old: raise HTTPException(404, "Appointment is no longer active")
    doctor = await db.users.find_one({"_id": ObjectId(old["doctor_id"])})
    await db.appointments.update_one({"id": appointment_id}, {"$set": {"status": "cancelled", "cancel_reason": "Rescheduled by patient"}})
    await db.appointments.update_many(
        {"doctor_id": old["doctor_id"], "day": old["day"], "status": {"$in": ["waiting", "called"]}, "position": {"$gt": old["position"]}},
        {"$inc": {"position": -1}},
    )
    active = await db.appointments.count_documents({"doctor_id": old["doctor_id"], "day": old["day"], "status": {"$in": ["waiting", "called"]}})
    position = active + 1
    new = {**old, "id": str(uuid.uuid4()), "position": position, "status": "waiting", "created_at": now().isoformat(), "pushbacks": 0}
    await db.appointments.insert_one(new)
    await broadcast(old["doctor_id"])
    consult = (doctor or {}).get("consult_minutes", 15)
    return {"id": new["id"], "position": position, "eta_min": (position-1)*consult, "eta_max": position*consult}

# ----- Doctor queue control -----
@api.get("/doctors/{doctor_id}/queue")
async def doctor_queue(doctor_id: str, user=Depends(current_user)):
    if user["role"] != "doctor" or str(user["_id"]) != doctor_id:
        raise HTTPException(403, "Doctor access only")
    return await queue_snapshot(doctor_id)

@api.patch("/doctors/{doctor_id}/settings")
async def settings(doctor_id: str, data: DoctorSettings, user=Depends(current_user)):
    if user["role"] != "doctor" or str(user["_id"]) != doctor_id:
        raise HTTPException(403, "Doctor access only")
    await db.users.update_one({"_id": user["_id"]}, {"$set": data.model_dump()})
    await broadcast(doctor_id)
    return {**data.model_dump(), "id": doctor_id}

@api.post("/doctors/{doctor_id}/delay")
async def set_delay(doctor_id: str, data: Delay, user=Depends(current_user)):
    if user["role"] != "doctor" or str(user["_id"]) != doctor_id:
        raise HTTPException(403, "Doctor access only")
    await db.users.update_one({"_id": user["_id"]}, {"$set": {"delay_minutes": data.minutes}})
    await broadcast(doctor_id)
    return {"ok": True, "delay_minutes": data.minutes}

@api.post("/doctors/{doctor_id}/next")
async def next_patient(doctor_id: str, data: QueueAction, user=Depends(current_user)):
    if user["role"] != "doctor" or str(user["_id"]) != doctor_id:
        raise HTTPException(403, "Doctor access only")
    await db.appointments.update_many({"doctor_id": doctor_id, "status": "called"}, {"$set": {"status": "done"}})
    appt = await db.appointments.find_one_and_update(
        {"id": data.appointment_id, "doctor_id": doctor_id, "status": "waiting"},
        {"$set": {"status": "called"}},
        projection={"_id": 0},
        return_document=ReturnDocument.AFTER,
    )
    if not appt: raise HTTPException(404, "That patient is no longer waiting")
    await broadcast(doctor_id)
    return appt

@api.post("/doctors/{doctor_id}/no-show")
async def no_show(doctor_id: str, data: QueueAction, user=Depends(current_user)):
    if user["role"] != "doctor" or str(user["_id"]) != doctor_id:
        raise HTTPException(403, "Doctor access only")
    appt = await db.appointments.find_one({"id": data.appointment_id, "doctor_id": doctor_id, "status": {"$in": ["waiting", "called"]}}, {"_id": 0})
    if not appt: raise HTTPException(404, "Appointment not found")
    if appt.get("pushbacks", 0) >= 2:
        await db.appointments.update_one(
            {"id": appt["id"]},
            {"$set": {"status": "cancelled", "cancel_reason": "Exceeded no-show limit"}},
        )
        await db.appointments.update_many(
            {"doctor_id": doctor_id, "day": appt["day"], "status": {"$in": ["waiting", "called"]}, "position": {"$gt": appt["position"]}},
            {"$inc": {"position": -1}},
        )
    else:
        maxpos = await db.appointments.count_documents({"doctor_id": doctor_id, "day": appt["day"], "status": {"$in": ["waiting", "called"]}})
        target = min(appt["position"] + 10, maxpos)
        if target > appt["position"]:
            await db.appointments.update_many(
                {"doctor_id": doctor_id, "day": appt["day"], "status": {"$in": ["waiting", "called"]}, "position": {"$gt": appt["position"], "$lte": target}},
                {"$inc": {"position": -1}},
            )
        await db.appointments.update_one(
            {"id": appt["id"]},
            {"$set": {"status": "waiting", "position": target, "pushbacks": appt.get("pushbacks", 0) + 1}},
        )
    await broadcast(doctor_id)
    return {"ok": True}

@api.post("/doctors/{doctor_id}/done")
async def mark_done(doctor_id: str, data: QueueAction, user=Depends(current_user)):
    if user["role"] != "doctor" or str(user["_id"]) != doctor_id:
        raise HTTPException(403, "Doctor access only")
    appt = await db.appointments.find_one({"id": data.appointment_id, "doctor_id": doctor_id}, {"_id": 0})
    if not appt: raise HTTPException(404, "Appointment not found")
    await db.appointments.update_one({"id": appt["id"]}, {"$set": {"status": "done"}})
    if appt["status"] in ("waiting", "called"):
        await db.appointments.update_many(
            {"doctor_id": doctor_id, "day": appt["day"], "status": {"$in": ["waiting", "called"]}, "position": {"$gt": appt["position"]}},
            {"$inc": {"position": -1}},
        )
    # Create visit history record
    await db.visits.insert_one({
        "id": str(uuid.uuid4()),
        "appointment_id": appt["id"],
        "patient_id": appt["patient_id"],
        "patient_name": appt["patient_name"],
        "doctor_id": doctor_id,
        "doctor_name": user.get("name"),
        "condition": appt.get("reason", "Consultation"),
        "brief": appt.get("brief"),
        "medications": [],
        "notes": "",
        "date": now().isoformat(),
    })
    await broadcast(doctor_id)
    return {"ok": True}

# ----- Reception -----
async def require_reception(user):
    if user["role"] not in ("reception", "admin"):
        raise HTTPException(403, "Reception access only")

@api.get("/reception/dashboard")
async def reception_dashboard(user=Depends(current_user)):
    await require_reception(user)
    day = today()
    doctors = await db.users.find({"role": "doctor", "approved": True}, {"password_hash": 0}).to_list(100)
    totals = {"booked": 0, "checked_in": 0, "in_consult": 0, "completed": 0}
    columns = []
    for d in doctors:
        doc_id = str(d["_id"])
        appts = await db.appointments.find({"doctor_id": doc_id, "day": day}, {"_id": 0}).sort("position", 1).to_list(200)
        rows = []
        for a in appts:
            status = a["status"]
            if status == "booked": totals["booked"] += 1
            elif status == "waiting": totals["checked_in"] += 1
            elif status == "called": totals["in_consult"] += 1
            elif status == "done": totals["completed"] += 1
            rows.append({
                "id": a["id"], "position": a["position"], "patient_id": a["patient_id"],
                "patient_name": a["patient_name"], "reason": a.get("reason", ""),
                "status": status, "pushbacks": a.get("pushbacks", 0),
            })
        columns.append({
            "doctor_id": doc_id, "name": d["name"],
            "specialty": d.get("specialty"),
            "delay_minutes": d.get("delay_minutes", 0),
            "is_open": d.get("is_open", False),
            "consult_minutes": d.get("consult_minutes", 15),
            "rows": rows,
        })
    return {"date": day, "totals": totals, "doctors": columns}

@api.post("/reception/walk-in")
async def reception_walk_in(data: WalkIn, user=Depends(current_user)):
    await require_reception(user)
    doctor = await db.users.find_one({"_id": ObjectId(data.doctor_id), "role": "doctor", "approved": True})
    if not doctor or not doctor.get("is_open"):
        raise HTTPException(400, "This doctor's queue is not open")
    day = today()
    active = await db.appointments.count_documents({"doctor_id": data.doctor_id, "day": day, "status": {"$in": ["waiting", "called", "booked"]}})
    if doctor.get("daily_cap") and active >= doctor["daily_cap"]:
        raise HTTPException(400, "Today's queue is full")
    phone = (data.phone or "").strip()
    patient = None
    if phone:
        patient = await db.users.find_one({"phone": phone, "role": "patient"})
    if not patient:
        patient = {
            "name": data.patient_name, "email": f"walkin+{uuid.uuid4().hex[:8]}@drd.local",
            "password_hash": None, "role": "patient", "approved": True,
            "phone": phone, "walk_in": True, "created_at": now().isoformat(),
        }
        r = await db.users.insert_one(patient); patient["_id"] = r.inserted_id
    position = active + 1
    brief_text = ""
    try: brief_text = await generate_brief(data.reason)
    except Exception as exc: logger.warning("Dai brief unavailable: %s", exc)
    appt = {
        "id": str(uuid.uuid4()), "doctor_id": data.doctor_id,
        "doctor_name": doctor["name"],
        "patient_id": str(patient["_id"]), "patient_name": patient["name"],
        "reason": data.reason, "brief": brief_text, "position": position,
        "status": "waiting", "day": day, "pushbacks": 0,
        "created_at": now().isoformat(), "walk_in": True,
    }
    await db.appointments.insert_one(appt)
    await broadcast(data.doctor_id)
    return {k: v for k, v in appt.items() if k != "_id"}

@api.post("/reception/check-in/{appointment_id}")
async def reception_check_in(appointment_id: str, user=Depends(current_user)):
    await require_reception(user)
    appt = await db.appointments.find_one({"id": appointment_id}, {"_id": 0})
    if not appt: raise HTTPException(404, "Appointment not found")
    if appt["status"] != "booked":
        raise HTTPException(400, "Only booked appointments can be checked in")
    day = today()
    active = await db.appointments.count_documents({"doctor_id": appt["doctor_id"], "day": day, "status": {"$in": ["waiting", "called"]}})
    await db.appointments.update_one({"id": appointment_id}, {"$set": {"status": "waiting", "position": active + 1}})
    await broadcast(appt["doctor_id"])
    return {"ok": True}

# ----- Patient 360 -----
@api.get("/patients")
async def list_patients(q: str = "", user=Depends(current_user)):
    if user["role"] not in ("doctor", "reception", "admin"):
        raise HTTPException(403, "Not allowed")
    query = {"role": "patient"}
    if q: query["$or"] = [{"name": {"$regex": q, "$options": "i"}}, {"phone": {"$regex": q, "$options": "i"}}, {"email": {"$regex": q, "$options": "i"}}]
    users = await db.users.find(query, {"password_hash": 0}).limit(50).to_list(50)
    return [{
        "id": str(u["_id"]), "name": u["name"], "phone": u.get("phone", ""),
        "email": u.get("email", ""), "age": u.get("age"), "gender": u.get("gender"),
    } for u in users]

@api.get("/patients/{patient_id}")
async def patient_360(patient_id: str, user=Depends(current_user)):
    if user["role"] not in ("doctor", "reception", "admin") and str(user["_id"]) != patient_id:
        raise HTTPException(403, "Not allowed")
    p = await db.users.find_one({"_id": ObjectId(patient_id)}, {"password_hash": 0})
    if not p: raise HTTPException(404, "Patient not found")
    visits = await db.visits.find({"patient_id": patient_id}, {"_id": 0}).sort("date", -1).limit(30).to_list(30)
    last_vitals = next((v.get("vitals") for v in visits if v.get("vitals")), p.get("vitals"))
    return {
        "id": patient_id,
        "name": p["name"], "phone": p.get("phone", ""),
        "email": p.get("email"), "age": p.get("age"), "gender": p.get("gender"),
        "blood_type": p.get("blood_type"), "allergies": p.get("allergies", []),
        "conditions": p.get("conditions", []),
        "vitals": last_vitals or {},
        "visits": visits,
    }

@api.post("/patients/{patient_id}/summary")
async def patient_summary(patient_id: str, user=Depends(current_user)):
    if user["role"] not in ("doctor", "reception", "admin"):
        raise HTTPException(403, "Not allowed")
    p = await db.users.find_one({"_id": ObjectId(patient_id)})
    if not p: raise HTTPException(404, "Patient not found")
    visits = await db.visits.find({"patient_id": patient_id}, {"_id": 0}).sort("date", -1).limit(10).to_list(10)
    context = f"Patient: {p['name']}. Age: {p.get('age', 'n/a')}. Gender: {p.get('gender', 'n/a')}. "
    context += f"Allergies: {', '.join(p.get('allergies', [])) or 'none'}. "
    context += f"Conditions: {', '.join(p.get('conditions', [])) or 'none'}.\n\n"
    context += "Visits:\n"
    for v in visits[:5]:
        context += f"- {v.get('date','')[:10]} · {v.get('doctor_name','')} · {v.get('condition','')} · {v.get('notes','')}\n"
    try:
        chat = LlmChat(
            api_key=os.environ["EMERGENT_LLM_KEY"],
            session_id=f"p360-{patient_id}",
            system_message="You are Dai, a clinical overview assistant. Summarize the patient's history into a brief, structured, non-diagnostic overview for a clinician: Overview, Chronic conditions, Allergies, Recent trend, Suggested follow-up (logistics only). Do not provide diagnosis or prescriptions.",
        ).with_model("gemini", "gemini-3-flash-preview")
        text = ""
        async for event in chat.stream_message(UserMessage(text=context)):
            if isinstance(event, TextDelta): text += event.content
            if isinstance(event, StreamDone): break
        return {"summary": text}
    except Exception as e:
        logger.warning("Dai summary unavailable: %s", e)
        return {"summary": "Dai summary is temporarily unavailable."}

@api.post("/visits")
async def create_visit(appointment_id: str, data: Visit, user=Depends(current_user)):
    if user["role"] != "doctor": raise HTTPException(403, "Doctor only")
    appt = await db.appointments.find_one({"id": appointment_id, "doctor_id": str(user["_id"])}, {"_id": 0})
    if not appt: raise HTTPException(404, "Appointment not found")
    v = {
        "id": str(uuid.uuid4()),
        "appointment_id": appointment_id,
        "patient_id": appt["patient_id"],
        "patient_name": appt["patient_name"],
        "doctor_id": str(user["_id"]),
        "doctor_name": user["name"],
        "condition": data.condition,
        "medications": data.medications or [],
        "notes": data.notes or "",
        "date": now().isoformat(),
    }
    await db.visits.insert_one(v)
    return {"ok": True, "id": v["id"]}

# ----- Reviews -----
@api.post("/doctors/{doctor_id}/review")
async def submit_review(doctor_id: str, data: Review, user=Depends(current_user)):
    if user["role"] != "patient": raise HTTPException(403, "Only patients can leave reviews")
    done_appt = await db.appointments.find_one({"doctor_id": doctor_id, "patient_id": str(user["_id"]), "status": "done"})
    if not done_appt: raise HTTPException(400, "You can only review after a completed consultation")
    await db.reviews.insert_one({
        "id": str(uuid.uuid4()),
        "doctor_id": doctor_id,
        "patient_id": str(user["_id"]),
        "patient_name": user["name"],
        "rating": data.rating,
        "comment": (data.comment or "").strip()[:400],
        "created_at": now().isoformat(),
    })
    return {"ok": True, "rating": await doctor_rating(doctor_id)}

@api.get("/doctors/{doctor_id}/reviews")
async def list_reviews(doctor_id: str):
    reviews = await db.reviews.find({"doctor_id": doctor_id}, {"_id": 0}).sort("created_at", -1).limit(20).to_list(20)
    return {"reviews": reviews, "summary": await doctor_rating(doctor_id)}

# ----- Dai -----
@api.post("/dai/brief")
async def brief(data: dict, user=Depends(current_user)):
    return {"brief": await generate_brief(data.get("reason", ""))}

@api.post("/dai/chat")
async def dai_chat(data: AssistantRequest, user=Depends(current_user)):
    async def stream():
        chat = LlmChat(
            api_key=os.environ["EMERGENT_LLM_KEY"],
            session_id=f"dai-{user['_id']}",
            system_message="You are Dai for Dr.D. Answer only appointment logistics, queue position/ETA, rescheduling guidance, timings, and triage to a doctor specialty. Do not diagnose or give medical advice. If asked medical questions, say you can help find the right specialty but cannot advise medically.",
        ).with_model("gemini", "gemini-3-flash-preview")
        async for event in chat.stream_message(UserMessage(text=data.message)):
            if isinstance(event, TextDelta): yield f"data: {json.dumps({'text': event.content})}\n\n"
            if isinstance(event, StreamDone): break
    return StreamingResponse(stream(), media_type="text/event-stream", headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"})

# ----- WebSocket (public — anonymized) -----
@app.websocket("/api/ws/queue/{doctor_id}")
async def queue_ws(ws: WebSocket, doctor_id: str):
    try:
        # Verify doctor exists
        doc = await db.users.find_one({"_id": ObjectId(doctor_id), "role": "doctor"})
        if not doc:
            await ws.close(code=1008); return
    except Exception:
        await ws.close(code=1008); return
    await ws.accept(); connections[ws] = doctor_id
    try:
        # send initial
        await ws.send_text(json.dumps({"doctor_id": doctor_id, "public": await public_queue(doctor_id)}))
        while True:
            await ws.receive_text()
    except WebSocketDisconnect:
        connections.pop(ws, None)
    except Exception:
        connections.pop(ws, None)

app.include_router(api)

allowed_origins = [o.strip() for o in os.environ.get("CORS_ORIGINS", os.environ.get("FRONTEND_URL", "")).split(",") if o.strip()] or ["*"]
app.add_middleware(
    CORSMiddleware,
    allow_origins=allowed_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

@app.on_event("startup")
async def startup():
    await db.users.create_index("email", unique=True)
    await db.user_sessions.create_index("session_token", unique=True)
    await db.appointments.create_index([("doctor_id", 1), ("day", 1), ("status", 1)])
    admin_email = os.environ["ADMIN_EMAIL"]; admin_pw = os.environ["ADMIN_PASSWORD"]
    if not await db.users.find_one({"email": admin_email}):
        await db.users.insert_one({
            "name": "Dr.D Admin", "email": admin_email,
            "password_hash": hash_password(admin_pw),
            "role": "admin", "approved": True,
        })
    if not await db.users.find_one({"email": "doctor@drd.demo"}):
        await db.users.insert_one({
            "name": "Dr. Maya Chen", "email": "doctor@drd.demo",
            "password_hash": hash_password("Doctor123!"),
            "role": "doctor", "approved": True,
            "specialty": "Family Medicine", "is_open": True,
            "consult_minutes": 15, "daily_cap": 20,
            "bio": "Family practice physician focused on calm, patient-first care. 12 years of experience helping families with everyday wellness.",
            "kyc_verified": True, "delay_minutes": 0,
        })
    if not await db.users.find_one({"email": "doctor2@drd.demo"}):
        await db.users.insert_one({
            "name": "Dr. Raj Mehta", "email": "doctor2@drd.demo",
            "password_hash": hash_password("Doctor123!"),
            "role": "doctor", "approved": True,
            "specialty": "Cardiology", "is_open": True,
            "consult_minutes": 12, "daily_cap": 15,
            "bio": "Cardiologist with 12 years of experience treating hypertension, arrhythmia, and preventive cardiac care.",
            "kyc_verified": True, "delay_minutes": 0,
        })
    for extra in [
        ("Dr. Meera Shah", "doctor3@drd.demo", "Dermatology", 10, "Dermatologist with a focus on eczema, acne, and skin wellness."),
        ("Dr. Kunal Verma", "doctor4@drd.demo", "Pediatrics", 15, "Pediatrician — gentle, child-first consultations for little humans."),
    ]:
        if not await db.users.find_one({"email": extra[1]}):
            await db.users.insert_one({
                "name": extra[0], "email": extra[1],
                "password_hash": hash_password("Doctor123!"),
                "role": "doctor", "approved": True,
                "specialty": extra[2], "is_open": True,
                "consult_minutes": extra[3], "daily_cap": 20,
                "bio": extra[4], "kyc_verified": True, "delay_minutes": 0,
            })
    if not await db.users.find_one({"email": "reception@drd.demo"}):
        await db.users.insert_one({
            "name": "Priya at Reception", "email": "reception@drd.demo",
            "password_hash": hash_password("Reception123!"),
            "role": "reception", "approved": True,
        })
    if not await db.users.find_one({"email": "patient@drd.demo"}):
        patient_doc = {
            "name": "Emily Parker", "email": "patient@drd.demo",
            "password_hash": hash_password("Patient123!"),
            "role": "patient", "approved": True,
            "phone": "+91 91111 11111", "age": 32, "gender": "Female",
            "blood_type": "O+", "allergies": ["Penicillin"],
            "conditions": ["Hypertension", "Non-smoker"],
            "vitals": {"bp": "128/84", "weight": "74 kg", "temp": "98.4 °F", "pulse": "78 bpm"},
        }
        await db.users.insert_one(patient_doc)
        # Seed sample visit history
        p = await db.users.find_one({"email": "patient@drd.demo"})
        d2 = await db.users.find_one({"email": "doctor2@drd.demo"})
        d3 = await db.users.find_one({"email": "doctor3@drd.demo"})
        if p and d2 and d3:
            samples = [
                {"doctor": d2, "condition": "Hypertension follow-up", "meds": ["Amlodipine 5mg · 30 days"], "notes": "BP improved. Continue same dose.", "date": "2026-09-12T10:00:00+00:00"},
                {"doctor": d3, "condition": "Contact dermatitis", "meds": ["Hydrocortisone cream"], "notes": "Avoid detergent contact.", "date": "2026-08-02T11:30:00+00:00"},
                {"doctor": d2, "condition": "Viral fever", "meds": ["Paracetamol 500mg · 3 days"], "notes": "Advised rest and fluids.", "date": "2026-06-15T09:15:00+00:00"},
            ]
            for s in samples:
                await db.visits.insert_one({
                    "id": str(uuid.uuid4()),
                    "patient_id": str(p["_id"]),
                    "patient_name": p["name"],
                    "doctor_id": str(s["doctor"]["_id"]),
                    "doctor_name": s["doctor"]["name"],
                    "condition": s["condition"],
                    "medications": s["meds"],
                    "notes": s["notes"],
                    "vitals": {"bp": "128/84", "weight": "74 kg", "temp": "98.4 °F", "pulse": "78 bpm"},
                    "date": s["date"],
                })

@app.on_event("shutdown")
async def shutdown(): client.close()
