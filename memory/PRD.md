# Dr.D — Product Requirements & Status

## Original Problem
Free, queue-based doctor appointment booking platform. Patients hold a live position in a doctor's daily queue instead of rigid time slots. Dai (AI, Gemini 3 Flash) briefs the doctor and answers patient logistics queries.

## Users
- **Patient** — browse doctors, join live queue, track position + ETA, cancel/reschedule, review doctor after visit, chat with Dai.
- **Doctor** — set availability, set avg consult time + daily cap, see ordered patient list with Dai briefs, tap Next, mark Done / No-show, broadcast delays.
- **Reception** — single desk view of all doctors' queues today, call next per column, add walk-in patients, open any patient's 360.
- Any clinic staff (doctor/reception) — Patient 360 view with vitals, allergies, chronic conditions, visit timeline, and a Dai-summarized overview.

## Decisions locked
- One dynamic queue per doctor per day; doctor-set avg consult drives ETA.
- Patients see own position + ETA + anonymized queue markers (no PII of others).
- No-show: +10 positions (or to end); auto-cancel after 2 pushbacks.
- Doctor manually advances via Next. Delay chip (0/5/10/15/30 min) broadcasts.
- Alerts v1: in-app toasts + browser notifications (Resend email deferred).
- Doctor approval boolean enforced; admin UI deferred.
- Auth: email+password AND Emergent-managed Google OAuth.

## Tech
- Frontend: React (CRA/craco) + shadcn UI + sonner + react-router-dom.
- Backend: FastAPI + motor async MongoDB + bcrypt + JWT + httpx.
- AI: Gemini 3 Flash via emergentintegrations (EMERGENT_LLM_KEY).
- Real-time: FastAPI WebSockets (anonymized public queue + doctor-scoped).

## Implemented (2026-10)
- Email+password + Google OAuth session exchange, 5-strike lockout.
- Doctor Next bug fixed (Mongo projection kwargs).
- Doctor directory with ratings, KYC badge, now_serving, delay.
- Patient book → Dai Gemini brief + duplicate-active guard.
- Patient /mine: ahead, eta_min, eta_max, delay-aware, now_serving.
- Cancel + reschedule with position compaction.
- Doctor queue, Next, Done, No-show (10-pushback, 2-strike cancel), delay broadcast.
- Done also creates visit history record.
- Reviews after done appointment with aggregated avg.
- Public anonymized queue + WebSocket live push.
- Reception dashboard: 4-stat row + per-doctor columns + delay chip + Call next + Walk-in modal + Patient 360 search.
- Patient 360: profile card (age/gender/blood/allergies/conditions), vitals grid, visit timeline, Ask Dai / Summarize with Dai (Gemini), Start consultation CTA.
- Modular frontend: TopNav (role-aware), LoginPage, PatientHome, PatientBook, PatientQueue (token hero + delay banner + anonymized list), DoctorHome (queue + Dai brief dialog + delay chips), DoctorSettings, ReceptionDashboard, Patient360, DaiBubble (SSE chat).

## Open / future
- **P1** Admin approval UI + invite codes + doctor KYC capture.
- **P1** Role selector on Google OAuth (currently always patient).
- **P2** Resend email alerts (booking / 15-min / you're-next).
- **P2** Split server.py into routers (auth/appointments/reception/p360/dai).
- **P2** Rate-limit WebSocket & auth; distributed brute-force store.
- **P3** Doctor-created visits with structured medications picker.

## Credentials
See /app/memory/test_credentials.md

## Test reports
- /app/test_reports/iteration_1.json (initial regression)
- /app/test_reports/iteration_2.json (reception + patient360 — 23/23 backend, 11/11 frontend)
