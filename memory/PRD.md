# Dr.D — Product Requirements & Status

## Original Problem
Free, queue-based doctor appointment booking platform. Patients hold a live position in a doctor's daily queue instead of rigid time slots. Dai (AI, Gemini 3 Flash) briefs the doctor on each patient and answers patient logistics queries.

## Core users
- Patient — browse/search doctors, join live queue, track position + ETA, cancel/reschedule, review doctor after visit.
- Doctor — set availability (open/close), set avg consult time + daily cap, see ordered patient list w/ Dai briefs, tap Next, mark Done or No-show, broadcast delays.

## Decisions locked
- One dynamic queue per doctor per day.
- Doctor-set average consult time drives ETA.
- Patients see own position + ETA + anonymized queue markers (no PII of other patients).
- No-show pushback: +10 positions, or to end; auto-cancel after 2 pushbacks.
- Doctor manually advances via Next.
- Alerts: in-app toasts + browser notifications (Resend email deferred).
- Doctor approval: boolean enforced on login + endpoints (admin-approval UI deferred).
- Auth: email+password AND Emergent-managed Google OAuth.

## Tech stack
- Frontend: React (CRA/craco) + shadcn UI + sonner + react-router.
- Backend: FastAPI + motor async MongoDB + bcrypt + JWT + httpx (Emergent OAuth).
- AI: Gemini 3 Flash via emergentintegrations (EMERGENT_LLM_KEY).
- Real-time: FastAPI WebSockets (anonymized public queue broadcast).

## Implemented (2026-10)
- Email+password auth w/ roles, JWT cookie, admin + doctor + patient seeding.
- Emergent Google OAuth flow (/auth/session exchange, session_token cookie).
- Doctor directory with ratings, KYC badge, now_serving, delay.
- Booking endpoint with Dai Gemini brief, duplicate-active check.
- Patient /mine endpoint w/ ahead count, ETA range, delay-aware.
- Cancel + reschedule with position compaction.
- Doctor queue, Next, Done, No-show (10-pos pushback, 2-strike cancel), delay broadcast.
- Reviews (POST /doctors/{id}/review after done appointment).
- Public anonymized queue + WebSocket live push.
- Modular frontend: TopNav, LoginPage (email/pw + Google), PatientHome (hero + upcoming + doctor list + side panel), PatientBook (summary + reason), PatientQueue (token hero + anonymized queue + delay banner), DoctorHome (queue + Dai brief dialog + delay chips), DoctorSettings, DaiBubble (streaming chat).

## Open / future
- P1 Admin approval UI + invite codes + doctor KYC capture.
- P2 Resend email alerts (booking/15-min/you're-next).
- P2 Google OAuth role assignment for doctors (currently always patient).
- P2 Rate-limit WebSocket & auth; refine Dai prompt grounding.

## Credentials
See /app/memory/test_credentials.md
