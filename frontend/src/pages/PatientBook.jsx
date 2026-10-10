import { useEffect, useState } from "react";
import { useNavigate, useParams } from "react-router-dom";
import { api, errMsg } from "../lib/api";
import { Button } from "../components/ui/button";
import { Card, CardContent } from "../components/ui/card";
import { Textarea } from "../components/ui/textarea";
import { Star, CheckCircle2, Clock, MapPin, Sparkles, Users } from "lucide-react";
import { toast } from "sonner";

export default function PatientBook() {
  const { doctorId } = useParams();
  const nav = useNavigate();
  const [doctors, setDoctors] = useState([]);
  const [selected, setSelected] = useState(null);
  const [reason, setReason] = useState("");
  const [busy, setBusy] = useState(false);

  useEffect(() => {
    (async () => {
      const r = await api.get("/doctors");
      setDoctors(r.data);
      if (doctorId) {
        try {
          const d = await api.get(`/doctors/${doctorId}`);
          setSelected(d.data);
        } catch {}
      } else if (r.data.length > 0) {
        setSelected(r.data[0]);
      }
    })();
  }, [doctorId]);

  const confirm = async () => {
    if (!selected || !reason.trim()) {
      toast.error("Please share a brief reason for your visit.");
      return;
    }
    setBusy(true);
    try {
      await api.post("/appointments", { doctor_id: selected.id, reason: reason.trim() });
      toast.success("You're in the queue!");
      nav("/queue");
    } catch (e) {
      toast.error(errMsg(e));
    } finally {
      setBusy(false);
    }
  };

  if (!selected) return <div className="drd-loading">Loading…</div>;

  return (
    <div className="drd-page">
      <div className="drd-book-grid">
        <Card className="drd-card">
          <CardContent>
            <div className="drd-book-head">
              <div className="drd-avatar-circle lg">{selected.name[0]}</div>
              <div>
                <h2 data-testid="book-doctor-name">{selected.name}</h2>
                <p className="drd-muted">
                  {selected.specialty}
                </p>
                <div className="drd-book-badges">
                  {selected.rating?.avg && (
                    <span className="drd-chip-amber">
                      <Star size={12} fill="#f59e0b" /> {selected.rating.avg} ({selected.rating.count})
                    </span>
                  )}
                  {selected.kyc_verified && (
                    <span className="drd-chip-mint">
                      <CheckCircle2 size={12} /> KYC Verified
                    </span>
                  )}
                </div>
              </div>
            </div>

            <div className="drd-book-stats">
              <div className="drd-stat">
                <small>Fee</small>
                <strong>Free</strong>
              </div>
              <div className="drd-stat">
                <small>Avg consult</small>
                <strong>{selected.consult_minutes} min</strong>
              </div>
              <div className="drd-stat drd-stat-mint">
                <small>In queue now</small>
                <strong>{selected.queue_count}</strong>
              </div>
            </div>

            <p className="drd-book-bio">{selected.bio}</p>

            <div className="drd-doctor-list">
              {doctors.filter((d) => d.id !== selected.id).slice(0, 3).map((d) => (
                <button
                  key={d.id}
                  className="drd-doctor-row"
                  onClick={() => setSelected(d)}
                  data-testid={`book-switch-${d.id}`}
                >
                  <div className="drd-avatar-circle">{d.name[0]}</div>
                  <div className="drd-doctor-row-info">
                    <strong>{d.name}</strong>
                    <small className="drd-muted">{d.specialty}</small>
                  </div>
                  <span className={d.is_open ? "drd-pill-open" : "drd-pill-closed"}>
                    {d.is_open ? "Open" : "Closed"}
                  </span>
                </button>
              ))}
            </div>
          </CardContent>
        </Card>

        <aside>
          <Card className="drd-card">
            <CardContent>
              <h3>Booking summary</h3>
              <div className="drd-summary-row">
                <span className="drd-muted">Doctor</span>
                <strong>{selected.name}</strong>
              </div>
              <div className="drd-summary-row">
                <span className="drd-muted">Specialty</span>
                <strong>{selected.specialty}</strong>
              </div>
              <div className="drd-summary-row">
                <span className="drd-muted">Position today</span>
                <strong>#{selected.queue_count + 1}</strong>
              </div>
              <div className="drd-summary-row">
                <span className="drd-muted">Est. wait</span>
                <strong>~{selected.queue_count * selected.consult_minutes} min</strong>
              </div>

              <div className="drd-book-reason">
                <label htmlFor="reason">Reason for visit</label>
                <Textarea
                  id="reason"
                  value={reason}
                  onChange={(e) => setReason(e.target.value)}
                  placeholder="A few words help Dai prepare your doctor…"
                  rows={4}
                  data-testid="book-reason-input"
                />
              </div>

              <Button
                onClick={confirm}
                disabled={busy || !selected.is_open}
                className="drd-btn-primary"
                data-testid="confirm-booking-button"
              >
                {!selected.is_open ? "Queue closed" : busy ? "Joining…" : "Confirm booking"}
              </Button>
              <p className="drd-muted drd-booking-note">
                <Sparkles size={12} /> Dr.D is free. No payment required.
              </p>
            </CardContent>
          </Card>
        </aside>
      </div>
    </div>
  );
}
