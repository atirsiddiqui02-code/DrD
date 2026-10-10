import { useEffect, useRef, useState, useCallback } from "react";
import { useNavigate } from "react-router-dom";
import { api, API, errMsg } from "../lib/api";
import { Button } from "../components/ui/button";
import { Card, CardContent } from "../components/ui/card";
import { Clock, AlertTriangle, CheckCircle2, Sparkles } from "lucide-react";
import { toast } from "sonner";

export default function PatientQueue() {
  const nav = useNavigate();
  const [mine, setMine] = useState([]);
  const [publicQ, setPublicQ] = useState(null);
  const notified = useRef({ fifteen: false, next: false });

  const load = useCallback(async () => {
    try {
      const { data } = await api.get("/appointments/mine");
      setMine(data);
      const active = data.find((x) => ["waiting", "called"].includes(x.status));
      if (active) {
        const pub = await api.get(`/doctors/${active.doctor_id}/public-queue`);
        setPublicQ(pub.data);
      } else {
        setPublicQ(null);
      }
    } catch {}
  }, []);

  useEffect(() => {
    load();
    if ("Notification" in window && Notification.permission === "default") {
      Notification.requestPermission();
    }
  }, [load]);

  const active = mine.find((x) => ["waiting", "called"].includes(x.status));
  const doctorId = active?.doctor_id;

  useEffect(() => {
    if (!doctorId) return;
    const url = `${API.replace(/^http/, "ws")}/ws/queue/${doctorId}`;
    const socket = new WebSocket(url);
    socket.onmessage = () => load();
    return () => socket.close();
  }, [doctorId, load]);

  useEffect(() => {
    if (!active) return;
    if (
      "Notification" in window &&
      Notification.permission === "granted"
    ) {
      if (active.status === "called" && !notified.current.next) {
        notified.current.next = true;
        new Notification("You're next!", { body: `${active.doctor_name} is calling you in.` });
      } else if (active.eta_min <= 15 && active.status === "waiting" && !notified.current.fifteen) {
        notified.current.fifteen = true;
        new Notification("Head over soon", {
          body: `You're #${active.position} in ${active.doctor_name}'s queue. Please arrive in ~15 min.`,
        });
      }
    }
  }, [active?.status, active?.eta_min, active?.position, active?.doctor_name, active]);

  if (!active) {
    return (
      <div className="drd-page">
        <Card className="drd-card">
          <CardContent className="drd-empty">
            <h2>No active queue</h2>
            <p className="drd-muted">You're not in a queue right now.</p>
            <Button
              onClick={() => nav("/book")}
              className="drd-btn-primary"
              data-testid="goto-book-button"
            >
              Book a doctor
            </Button>
          </CardContent>
        </Card>
      </div>
    );
  }

  const nowServing = publicQ?.now_serving ?? active.now_serving;
  const delay = publicQ?.delay_minutes ?? active.delay_minutes ?? 0;

  return (
    <div className="drd-page drd-queue-page">
      {/* Token hero */}
      <section className="drd-token-hero" data-testid="token-hero">
        <small>Your token</small>
        <strong className="drd-token-number" data-testid="token-number">
          {active.position}
        </strong>
        <span className="drd-token-doctor">{active.doctor_name}</span>
        <div className="drd-token-serving" data-testid="token-serving">
          Now serving #{nowServing ?? "—"}
        </div>
      </section>

      {/* Stat row */}
      <div className="drd-queue-stats">
        <Card className="drd-card drd-stat-card">
          <CardContent>
            <small>Ahead of you</small>
            <strong data-testid="stat-ahead">{active.ahead}</strong>
          </CardContent>
        </Card>
        <Card className="drd-card drd-stat-card">
          <CardContent>
            <small>Est. wait</small>
            <strong data-testid="stat-eta">
              {active.eta_min}–{active.eta_max}
            </strong>
            <span className="drd-muted">minutes</span>
          </CardContent>
        </Card>
        <Card className="drd-card drd-stat-card">
          <CardContent>
            <small>Status</small>
            <strong className="drd-stat-status" data-testid="stat-status">
              {active.status === "called" ? "Your turn" : "Waiting"}
            </strong>
          </CardContent>
        </Card>
      </div>

      {delay > 0 && (
        <div className="drd-delay-banner" data-testid="delay-banner">
          <AlertTriangle size={16} /> Doctor is running{" "}
          <strong>{delay} minutes late</strong>. Your ETA has been updated.
        </div>
      )}

      {/* Anonymized queue list */}
      <Card className="drd-card">
        <CardContent>
          <div className="drd-section-head">
            <h3>Queue</h3>
            <span className="drd-chip-mint-small">
              <Sparkles size={10} /> Live
            </span>
          </div>
          <div className="drd-queue-list" data-testid="queue-list">
            {(publicQ?.queue || []).map((item) => {
              const isMe = item.position === active.position;
              const isServing = item.status === "called";
              return (
                <div
                  key={item.position}
                  className={`drd-queue-item ${isMe ? "me" : ""} ${isServing ? "serving" : ""}`}
                  data-testid={`queue-item-${item.position}`}
                >
                  <span className="drd-queue-num">{item.position}</span>
                  <span className="drd-queue-label">
                    {isMe ? "You" : isServing ? "In consultation" : "Waiting"}
                  </span>
                  {isServing && <span className="drd-queue-now">Now</span>}
                  {isMe && !isServing && (
                    <span className="drd-queue-soon">
                      {active.eta_min <= 15 ? "Your turn soon" : "Waiting"}
                    </span>
                  )}
                </div>
              );
            })}
          </div>
        </CardContent>
      </Card>

      <div className="drd-queue-actions">
        <Button
          variant="outline"
          onClick={async () => {
            try {
              const { data } = await api.post(`/appointments/${active.id}/reschedule`);
              toast.success(`Rescheduled — new position #${data.position}`);
              load();
            } catch (e) {
              toast.error(errMsg(e));
            }
          }}
          data-testid="queue-reschedule"
        >
          Reschedule
        </Button>
        <Button
          variant="ghost"
          className="drd-btn-ghost-red"
          onClick={async () => {
            try {
              await api.post(`/appointments/${active.id}/cancel`);
              toast.success("Appointment cancelled");
              nav("/");
            } catch (e) {
              toast.error(errMsg(e));
            }
          }}
          data-testid="queue-cancel"
        >
          Cancel appointment
        </Button>
      </div>
    </div>
  );
}
