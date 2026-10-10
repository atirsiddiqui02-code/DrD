from dotenv import load_dotenv
from pathlib import Path
load_dotenv(Path(__file__).parent / ".env")

import os, uuid, json, asyncio, logging, bcrypt, jwt
from datetime import datetime, timezone, timedelta
from typing import Optional
from fastapi import FastAPI, APIRouter, HTTPException, Request, WebSocket, WebSocketDisconnect, Depends
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
def public_user(user):
    return {"id": str(user.get("_id", user.get("id"))), "name": user["name"], "email": user["email"], "role": user["role"], "approved": user.get("approved", True)}
def hash_password(value): return bcrypt.hashpw(value.encode(), bcrypt.gensalt()).decode()
def verify_password(value, hashed): return bcrypt.checkpw(value.encode(), hashed.encode())
def token(user): return jwt.encode({"sub": str(user["_id"]), "exp": now()+timedelta(days=7)}, JWT_SECRET, algorithm=ALGORITHM)

async def current_user(request: Request):
    raw = request.cookies.get("access_token") or request.headers.get("Authorization", "").replace("Bearer ", "")
    if not raw: raise HTTPException(401, "Please sign in to continue")
    try: payload = jwt.decode(raw, JWT_SECRET, algorithms=[ALGORITHM])
    except jwt.InvalidTokenError: raise HTTPException(401, "Your session has expired")
    user = await db.users.find_one({"_id": __import__("bson").ObjectId(payload["sub"])})
    if not user: raise HTTPException(401, "User not found")
    if user.get("role")=="doctor" and not user.get("approved", False): raise HTTPException(403, "Doctor account is awaiting admin approval")
    return user

class Register(BaseModel):
    name: str; email: str; password: str; role: str = "patient"; specialty: Optional[str] = None
class Login(BaseModel): email: str; password: str
class Booking(BaseModel): doctor_id: str; reason: str
class DoctorSettings(BaseModel): is_open: bool; consult_minutes: int = Field(15, ge=5, le=120); daily_cap: Optional[int] = Field(None, ge=1)
class QueueAction(BaseModel): appointment_id: str
class AssistantRequest(BaseModel): message: str

async def generate_brief(reason):
    chat=LlmChat(api_key=os.environ["EMERGENT_LLM_KEY"],session_id=f"brief-{uuid.uuid4()}",system_message="You are Dai, a clinical intake assistant. Convert the patient's reason into a concise structured pre-visit brief. Never diagnose, prescribe, or give medical advice. Return plain text with Symptoms, Duration, Context, and Suggested focus.").with_model("gemini","gemini-3-flash-preview")
    text=""
    async for event in chat.stream_message(UserMessage(text=reason)):
        if isinstance(event,TextDelta): text+=event.content
        if isinstance(event,StreamDone): break
    return text

@api.get("/")
async def root(): return {"message": "Dr.D is ready"}

@api.post("/auth/register")
async def register(data: Register, response: __import__("fastapi").Response):
    email=data.email.lower().strip()
    if await db.users.find_one({"email": email}): raise HTTPException(409, "An account with that email already exists")
    role = data.role if data.role in ("patient", "doctor") else "patient"
    user={"name":data.name,"email":email,"password_hash":hash_password(data.password),"role":role,"approved":role=="patient","specialty":data.specialty or "General Practice","is_open":False,"consult_minutes":15,"daily_cap":None,"created_at":now().isoformat()}
    result=await db.users.insert_one(user); user["_id"]=result.inserted_id
    response.set_cookie("access_token", token(user), httponly=True, samesite="lax", max_age=604800)
    return public_user(user)

@api.post("/auth/login")
async def login(data: Login, response: __import__("fastapi").Response):
    email=data.email.lower().strip(); attempt=failed_logins.get(email)
    if attempt and attempt["until"]>now().timestamp(): raise HTTPException(429,"Too many attempts. Please try again in 15 minutes")
    user=await db.users.find_one({"email":email})
    if not user or not verify_password(data.password,user["password_hash"]):
        count=(attempt or {"count":0})["count"]+1
        failed_logins[email]={"count":count,"until":now().timestamp()+900 if count>=5 else 0}
        raise HTTPException(401,"Email or password is incorrect")
    failed_logins.pop(email,None)
    if user.get("role")=="doctor" and not user.get("approved", False): raise HTTPException(403,"Doctor account is awaiting admin approval")
    response.set_cookie("access_token", token(user), httponly=True, samesite="lax", max_age=604800)
    return public_user(user)

@api.post("/auth/logout")
async def logout(response: __import__("fastapi").Response): response.delete_cookie("access_token"); return {"ok":True}

@api.get("/auth/me")
async def me(user=Depends(current_user)): return public_user(user)

@api.get("/doctors")
async def doctors(q: str = ""):
    query={"role":"doctor","approved":True}
    if q: query["$or"]=[{"name":{"$regex":q,"$options":"i"}},{"specialty":{"$regex":q,"$options":"i"}}]
    users=await db.users.find(query,{"password_hash":0,"_id":1}).to_list(100)
    result=[]
    for d in users:
        day=now().date().isoformat(); count=await db.appointments.count_documents({"doctor_id":str(d["_id"]),"day":day,"status":{"$in":["waiting","called"]}})
        result.append({"id":str(d["_id"]),"name":d["name"],"specialty":d.get("specialty","General Practice"),"is_open":d.get("is_open",False),"consult_minutes":d.get("consult_minutes",15),"daily_cap":d.get("daily_cap"),"queue_count":count})
    return result

async def queue_snapshot(doctor_id):
    items=await db.appointments.find({"doctor_id":doctor_id,"day":now().date().isoformat(),"status":{"$in":["waiting","called"]}},{"_id":0}).sort("position",1).to_list(100)
    return items
async def broadcast(doctor_id):
    payload=json.dumps({"doctor_id":doctor_id,"queue":await queue_snapshot(doctor_id)})
    dead=[]
    for ws, socket_doctor_id in list(connections.items()):
        if socket_doctor_id != doctor_id: continue
        try: await ws.send_text(payload)
        except Exception: dead.append(ws)
    for ws in dead: connections.pop(ws, None)

@api.post("/appointments")
async def book(data: Booking, user=Depends(current_user)):
    if user["role"]!="patient": raise HTTPException(403,"Only patients can book appointments")
    doctor=await db.users.find_one({"_id":__import__("bson").ObjectId(data.doctor_id),"role":"doctor","approved":True})
    if not doctor or not doctor.get("is_open"): raise HTTPException(400,"This doctor's queue is not open")
    day=now().date().isoformat(); active=await db.appointments.count_documents({"doctor_id":data.doctor_id,"day":day,"status":{"$in":["waiting","called"]}})
    if doctor.get("daily_cap") and active >= doctor["daily_cap"]: raise HTTPException(400,"Today's queue is full")
    position=active+1; brief_text="Dai brief will be prepared before the consultation."
    try: brief_text=await generate_brief(data.reason)
    except Exception as exc: logger.warning("Dai brief unavailable: %s", exc)
    appt={"id":str(uuid.uuid4()),"doctor_id":data.doctor_id,"patient_id":str(user["_id"]),"patient_name":user["name"],"reason":data.reason,"brief":brief_text,"position":position,"status":"waiting","day":day,"pushbacks":0,"created_at":now().isoformat()}
    await db.appointments.insert_one(appt)
    return {"id":appt["id"],"doctor_id":appt["doctor_id"],"patient_id":appt["patient_id"],"patient_name":appt["patient_name"],"reason":appt["reason"],"brief":appt["brief"],"position":appt["position"],"status":appt["status"],"day":appt["day"],"pushbacks":appt["pushbacks"],"created_at":appt["created_at"],"eta_minutes":(position-1)*doctor.get("consult_minutes",15)}

@api.get("/appointments/mine")
async def mine(user=Depends(current_user)):
    docs=await db.appointments.find({"patient_id":str(user["_id"]),"day":now().date().isoformat()},{"_id":0}).sort("created_at",-1).to_list(20)
    for item in docs:
        doctor=await db.users.find_one({"_id":__import__("bson").ObjectId(item["doctor_id"])})
        ahead=await db.appointments.count_documents({"doctor_id":item["doctor_id"],"day":item["day"],"status":{"$in":["waiting","called"]},"position":{"$lt":item["position"]}})
        item.update({"doctor_name":doctor["name"] if doctor else "Doctor","eta_minutes":ahead*(doctor or {}).get("consult_minutes",15)})
    return docs

@api.post("/appointments/{appointment_id}/cancel")
async def cancel_appointment(appointment_id: str, user=Depends(current_user)):
    result=await db.appointments.update_one({"id":appointment_id,"patient_id":str(user["_id"]),"status":{"$in":["waiting","called"]}},{"$set":{"status":"cancelled","cancel_reason":"Cancelled by patient"}})
    if not result.modified_count: raise HTTPException(404,"Appointment is already complete or cancelled")
    return {"ok":True}

@api.post("/appointments/{appointment_id}/reschedule")
async def reschedule_appointment(appointment_id: str, user=Depends(current_user)):
    old=await db.appointments.find_one({"id":appointment_id,"patient_id":str(user["_id"]),"status":{"$in":["waiting","called"]}})
    if not old: raise HTTPException(404,"Appointment is no longer active")
    doctor=await db.users.find_one({"_id":__import__("bson").ObjectId(old["doctor_id"])})
    active=await db.appointments.count_documents({"doctor_id":old["doctor_id"],"day":old["day"],"status":{"$in":["waiting","called"]}})
    await db.appointments.update_one({"id":appointment_id},{"$set":{"status":"cancelled","cancel_reason":"Rescheduled by patient"}})
    new={**old,"id":str(uuid.uuid4()),"position":active,"status":"waiting","created_at":now().isoformat()}
    new.pop("_id",None); await db.appointments.insert_one(new); await broadcast(old["doctor_id"])
    return {"id":new["id"],"position":new["position"],"eta_minutes":max(0,(new["position"]-1)*doctor.get("consult_minutes",15))}

@api.get("/doctors/{doctor_id}/queue")
async def doctor_queue(doctor_id: str, user=Depends(current_user)):
    if user["role"]!="doctor" or str(user["_id"])!=doctor_id: raise HTTPException(403,"Doctor access only")
    return await queue_snapshot(doctor_id)

@api.patch("/doctors/{doctor_id}/settings")
async def settings(doctor_id: str, data: DoctorSettings, user=Depends(current_user)):
    if user["role"]!="doctor" or str(user["_id"])!=doctor_id: raise HTTPException(403,"Doctor access only")
    await db.users.update_one({"_id":user["_id"]},{"$set":data.model_dump()}); return {**data.model_dump(),"id":doctor_id}

@api.post("/doctors/{doctor_id}/next")
async def next_patient(doctor_id: str, data: QueueAction, user=Depends(current_user)):
    if user["role"]!="doctor" or str(user["_id"])!=doctor_id: raise HTTPException(403,"Doctor access only")
    await db.appointments.update_many({"doctor_id":doctor_id,"status":"called"},{"$set":{"status":"done"}})
    appt=await db.appointments.find_one_and_update({"id":data.appointment_id,"doctor_id":doctor_id,"status":"waiting"},{"$set":{"status":"called"}},{"return_document":__import__("pymongo").ReturnDocument.AFTER,"projection":{"_id":0}})
    if not appt: raise HTTPException(404,"That patient is no longer waiting")
    safe={"id":appt["id"],"doctor_id":appt["doctor_id"],"patient_id":appt["patient_id"],"patient_name":appt["patient_name"],"reason":appt["reason"],"brief":appt.get("brief"),"position":appt["position"],"status":appt["status"],"day":appt["day"],"pushbacks":appt.get("pushbacks",0),"created_at":appt["created_at"]}
    await broadcast(doctor_id); return safe

@api.post("/doctors/{doctor_id}/no-show")
async def no_show(doctor_id: str, data: QueueAction, user=Depends(current_user)):
    if user["role"]!="doctor" or str(user["_id"])!=doctor_id: raise HTTPException(403,"Doctor access only")
    appt=await db.appointments.find_one({"id":data.appointment_id,"doctor_id":doctor_id,"status":{"$in":["waiting","called"]}})
    if not appt: raise HTTPException(404,"Appointment not found")
    if appt.get("pushbacks",0)>=2: await db.appointments.update_one({"id":appt["id"]},{"$set":{"status":"cancelled","cancel_reason":"Exceeded no-show limit"}})
    else:
        maxpos=await db.appointments.count_documents({"doctor_id":doctor_id,"day":appt["day"],"status":{"$in":["waiting","called"]}})
        target=min(appt["position"]+10,maxpos)
        if target>appt["position"]:
            await db.appointments.update_many({"doctor_id":doctor_id,"day":appt["day"],"status":{"$in":["waiting","called"]},"position":{"$gt":appt["position"],"$lte":target}},{"$inc":{"position":-1}})
        await db.appointments.update_one({"id":appt["id"]},{"$set":{"status":"waiting","position":target,"pushbacks":appt.get("pushbacks",0)+1}})
    await broadcast(doctor_id); return {"ok":True}

@api.get("/ws-token")
async def ws_token(user=Depends(current_user)): return {"doctor_id":str(user["_id"])}

@api.post("/dai/brief")
async def brief(data: dict, user=Depends(current_user)):
    return {"brief":await generate_brief(data.get("reason",""))}

@api.post("/dai/chat")
async def dai_chat(data: AssistantRequest, user=Depends(current_user)):
    async def stream():
        chat=LlmChat(api_key=os.environ["EMERGENT_LLM_KEY"],session_id=f"dai-{user['_id']}",system_message="You are Dai for Dr.D. Answer only appointment logistics, queue position/ETA, rescheduling guidance, timings, and triage to a doctor specialty. Do not diagnose or give medical advice. If asked medical questions, say you can help find the right specialty but cannot advise medically.").with_model("gemini","gemini-3-flash-preview")
        async for event in chat.stream_message(UserMessage(text=data.message)):
            if isinstance(event,TextDelta): yield f"data: {json.dumps({'text':event.content})}\n\n"
            if isinstance(event,StreamDone): break
    return StreamingResponse(stream(),media_type="text/event-stream",headers={"Cache-Control":"no-cache","X-Accel-Buffering":"no"})

@app.websocket("/api/ws/queue/{doctor_id}")
async def queue_ws(ws: WebSocket, doctor_id: str):
    raw=ws.cookies.get("access_token")
    if not raw:
        await ws.close(code=1008); return
    try:
        payload=jwt.decode(raw,JWT_SECRET,algorithms=[ALGORITHM])
        socket_user=await db.users.find_one({"_id":__import__("bson").ObjectId(payload["sub"])})
        if not socket_user or (socket_user.get("role")=="doctor" and (str(socket_user["_id"])!=doctor_id or not socket_user.get("approved",False))):
            await ws.close(code=1008); return
        if socket_user.get("role")=="patient" and not await db.appointments.find_one({"doctor_id":doctor_id,"patient_id":str(socket_user["_id"]),"status":{"$in":["waiting","called"]}}):
            await ws.close(code=1008); return
    except Exception:
        await ws.close(code=1008); return
    await ws.accept(); connections[ws]=doctor_id
    try:
        while True: await ws.receive_text()
    except WebSocketDisconnect: connections.pop(ws, None)

app.include_router(api)
app.add_middleware(CORSMiddleware,allow_origins=[os.environ.get("FRONTEND_URL","http://localhost:3000")],allow_credentials=True,allow_methods=["*"],allow_headers=["*"])

@app.on_event("startup")
async def startup():
    await db.users.create_index("email",unique=True)
    admin_email=os.environ["ADMIN_EMAIL"]; admin_pw=os.environ["ADMIN_PASSWORD"]
    admin=await db.users.find_one({"email":admin_email})
    if not admin: await db.users.insert_one({"name":"Dr.D Admin","email":admin_email,"password_hash":hash_password(admin_pw),"role":"admin","approved":True})
    if not await db.users.find_one({"email":"doctor@drd.demo"}):
        await db.users.insert_one({"name":"Dr. Maya Chen","email":"doctor@drd.demo","password_hash":hash_password("Doctor123!"),"role":"doctor","approved":True,"specialty":"Family Medicine","is_open":True,"consult_minutes":15,"daily_cap":20})
    if not await db.users.find_one({"email":"patient@drd.demo"}): await db.users.insert_one({"name":"Jordan Lee","email":"patient@drd.demo","password_hash":hash_password("Patient123!"),"role":"patient","approved":True})

@app.on_event("shutdown")
async def shutdown(): client.close()