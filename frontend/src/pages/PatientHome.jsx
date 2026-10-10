import { useEffect, useState } from "react";
import { Link, useNavigate } from "react-router-dom";
import { api, errMsg } from "../lib/api";
import { useAuth } from "../lib/auth";
import { Button } from "../components/ui/button";
import { Card, CardContent } from "../components/ui/card";
import { Sparkles, Star, Calendar, MapPin, Clock, ChevronRight, CheckCircle2 } from "lucide-react";
import { toast } from "sonner";

export default function PatientHome() {
  const { user } = useAuth();
  const nav = useNavigate();
  const [doctors, setDoctors] = useState([]);
  const [mine, setMine] = useState([]);
  const [loading, setLoading] = useState(true);

  const load = async () => {
    try {
      const [d, m] = await Promise.all([
        api.get("/doctors"),
        api.get("/appointments/mine"),
      ]);
      setDoctors(d.data);
      setMine(m.data);
    } catch (e) {
      // ignore
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    load();
  }, []);

  const active = mine.find((x) => ["waiting", "called"].includes(x.status));

  const cancel = async (id) => {
    try {
      await api.post(`/appointments/${id}/cancel`);
      toast.success("Appointment cancelled");
      load();
    } catch (e) {
      toast.error(errMsg(e));
    }
  };

  const reschedule = async (id) => {
    try {
      const { data } = await api.post(`/appointments/${id}/reschedule`);
      toast.success(`Rescheduled — new position #${data.position}`);
      load();
    } catch (e) {
      toast.error(errMsg(e));
    }
  };

  if (loading) return <div className="drd-loading" data-testid="patient-home-loading">Loading…</div>;

  return (
    <div className="drd-page">
      {/* Hero */}
      <section className="drd-hero" data-testid="patient-hero">
        <div>
          <h1 className="drd-hero-title">
            Hi, {user?.name?.split(" ")[0] || "there"} <span className="drd-wave">👋</span>
          </h1>
          <p className="drd-hero-sub">Your care, on your time.</p>
        </div>
        <div className="drd-hero-pill" data-testid="dai-ready-pill">
          <Sparkles size={14} /> Dai is ready — tap the bubble
        </div>
      </section>

      <div className="drd-grid-2">
        <div className="drd-col-main">
          {/* Upcoming / Active appointment */}
          {active ? (
            <Card className="drd-card" data-testid="upcoming-card">
              <CardContent className="drd-upcoming">
                <div className="drd-upcoming-head">
                  <h2>Upcoming Appointment</h2>
                  <span className="drd-chip-mint">
                    {active.status === "called" ? "In consultation" : "Confirmed"}
                  </span>
                </div>
                <div className="drd-upcoming-body">
                  <div className="drd-avatar-circle">
                    {active.doctor_name?.[0] || "D"}
                  </div>
                  <div className="drd-upcoming-info">
                    <strong data-testid="upcoming-doctor-name">{active.doctor_name}</strong>
                    <span className="drd-upcoming-spec">
                      <Star size={12} className="drd-icon-amber" /> {active.doctor_specialty || "Doctor"}
                    </span>
                    <small className="drd-muted">
                      Position #{active.position} · Today
                    </small>
                  </div>
                  <div className="drd-upcoming-actions">
                    <Button
                      className="drd-btn-primary"
                      size="sm"
                      onClick={() => nav("/queue")}
                      data-testid="btn-view-queue"
                    >
                      View queue
                    </Button>
                    <Button
                      variant="outline"
                      size="sm"
                      className="drd-btn-mint-outline"
                      onClick={() => reschedule(active.id)}
                      data-testid="btn-reschedule"
                    >
                      Reschedule
                    </Button>
                    <Button
                      variant="ghost"
                      size="sm"
                      className="drd-btn-ghost-red"
                      onClick={() => cancel(active.id)}
                      data-testid="btn-cancel"
                    >
                      Cancel
                    </Button>
                  </div>
                </div>
              </CardContent>
            </Card>
          ) : (
            <Card className="drd-card drd-card-empty" data-testid="no-active-card">
              <CardContent>
                <h2>No active appointment</h2>
                <p className="drd-muted">Pick a doctor below to join today's queue.</p>
              </CardContent>
            </Card>
          )}

          {/* Doctor list */}
          <Card className="drd-card">
            <CardContent>
              <div className="drd-section-head">
                <h2>Book an Appointment</h2>
                <small className="drd-muted">
                  <Calendar size={12} /> Live queue — no fixed slots
                </small>
              </div>
              <div className="drd-doctor-list">
                {doctors.map((d) => (
                  <Link
                    to={`/book/${d.id}`}
                    key={d.id}
                    className="drd-doctor-row"
                    data-testid={`doctor-row-${d.id}`}
                  >
                    <div className="drd-avatar-circle" data-testid={`doctor-avatar-${d.id}`}>
                      {d.name[0]}
                    </div>
                    <div className="drd-doctor-row-info">
                      <strong>{d.name}</strong>
                      <span className="drd-doctor-row-spec">
                        <Star size={12} className="drd-icon-amber" /> {d.specialty}
                        {d.kyc_verified && (
                          <span className="drd-chip-mint-small">
                            <CheckCircle2 size={10} /> KYC
                          </span>
                        )}
                      </span>
                      <small className="drd-muted">
                        <Clock size={11} /> {d.consult_minutes} min · {d.queue_count} in queue
                        {d.rating?.avg && <> · ★ {d.rating.avg}</>}
                      </small>
                    </div>
                    <span className={d.is_open ? "drd-pill-open" : "drd-pill-closed"}>
                      {d.is_open ? "Queue open" : "Closed"}
                    </span>
                    <ChevronRight size={16} className="drd-chevron" />
                  </Link>
                ))}
                {doctors.length === 0 && (
                  <p className="drd-muted">No doctors available right now.</p>
                )}
              </div>
            </CardContent>
          </Card>
        </div>

        <aside className="drd-col-side">
          {/* Position card */}
          {active ? (
            <Card className="drd-card">
              <CardContent>
                <div className="drd-side-head">
                  <span className="drd-side-dot" />
                  <strong>Position in Queue</strong>
                </div>
                <div className="drd-side-row">
                  <div className="drd-avatar-circle sm">{active.doctor_name?.[0]}</div>
                  <div>
                    <strong data-testid="side-position">
                      You are {ordinal(active.position)} in line
                    </strong>
                    <small className="drd-muted">
                      Please arrive 10–15 mins early.
                    </small>
                  </div>
                </div>
                <div className="drd-side-serving" data-testid="side-serving">
                  Now serving #{active.now_serving || "—"}
                  <span className="drd-side-eta">ETA {active.eta_min}–{active.eta_max} min</span>
                </div>
              </CardContent>
            </Card>
          ) : (
            <Card className="drd-card">
              <CardContent>
                <strong>Position in Queue</strong>
                <p className="drd-muted">You're not in a queue yet.</p>
              </CardContent>
            </Card>
          )}

          <RateYourDoctor last={mine.find((x) => x.status === "done")} onDone={load} />

          <Card className="drd-card drd-card-mint">
            <CardContent>
              <div className="drd-mint-head">
                <Sparkles size={16} /> Chat with Dai
              </div>
              <div className="drd-dai-suggestions">
                <button className="drd-dai-sugg" data-testid="dai-sugg-1">
                  When is my doctor available next?
                </button>
                <button className="drd-dai-sugg" data-testid="dai-sugg-2">
                  How many patients are ahead of me?
                </button>
              </div>
            </CardContent>
          </Card>
        </aside>
      </div>
    </div>
  );
}

function ordinal(n) {
  const s = ["th", "st", "nd", "rd"];
  const v = n % 100;
  return `${n}${s[(v - 20) % 10] || s[v] || s[0]}`;
}

function RateYourDoctor({ last, onDone }) {
  const [rating, setRating] = useState(0);
  const [sent, setSent] = useState(false);
  if (!last) {
    return (
      <Card className="drd-card">
        <CardContent>
          <strong>Rate Your Doctor</strong>
          <p className="drd-muted">You'll be able to review after your next consultation.</p>
        </CardContent>
      </Card>
    );
  }
  const submit = async () => {
    if (!rating) return;
    try {
      await api.post(`/doctors/${last.doctor_id}/review`, { rating, comment: "" });
      setSent(true);
      toast.success("Thanks for your rating!");
      onDone?.();
    } catch (e) {
      toast.error(errMsg(e));
    }
  };
  return (
    <Card className="drd-card">
      <CardContent>
        <strong>Rate Your Doctor</strong>
        <div className="drd-stars" data-testid="rate-stars">
          {[1, 2, 3, 4, 5].map((n) => (
            <button
              key={n}
              onClick={() => setRating(n)}
              className={n <= rating ? "on" : ""}
              data-testid={`star-${n}`}
              aria-label={`${n} star`}
            >
              <Star size={20} fill={n <= rating ? "#f59e0b" : "transparent"} />
            </button>
          ))}
        </div>
        <Button
          onClick={submit}
          disabled={!rating || sent}
          className="drd-btn-primary"
          size="sm"
          data-testid="submit-review"
        >
          {sent ? "Thanks!" : "Leave a Review"}
        </Button>
      </CardContent>
    </Card>
  );
}
