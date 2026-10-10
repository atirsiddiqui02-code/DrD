import { useEffect, useState, useCallback, useRef } from "react";
import { api, API, errMsg } from "../lib/api";
import { useAuth } from "../lib/auth";
import { Button } from "../components/ui/button";
import { Card, CardContent } from "../components/ui/card";
import {
  Dialog, DialogContent, DialogHeader, DialogTitle, DialogFooter,
} from "../components/ui/dialog";
import { Sparkles, Users, Clock, UserX, CheckCircle2, ChevronRight } from "lucide-react";
import { toast } from "sonner";

export default function DoctorHome() {
  const { user } = useAuth();
  const [queue, setQueue] = useState([]);
  const [brief, setBrief] = useState(null);
  const [delay, setDelay] = useState(0);
  const socketRef = useRef(null);

  const load = useCallback(async () => {
    if (!user?.id) return;
    try {
      const r = await api.get(`/doctors/${user.id}/queue`);
      setQueue(r.data);
      const me = await api.get("/auth/me");
      // delay comes from public queue
      const pub = await api.get(`/doctors/${user.id}/public-queue`);
      setDelay(pub.data.delay_minutes || 0);
    } catch {}
  }, [user?.id]);

  useEffect(() => { load(); }, [load]);

  useEffect(() => {
    if (!user?.id) return;
    const url = `${API.replace(/^http/, "ws")}/ws/queue/${user.id}`;
    const socket = new WebSocket(url);
    socket.onmessage = () => load();
    socketRef.current = socket;
    return () => socket.close();
  }, [user?.id, load]);

  const act = async (type, id) => {
    try {
      await api.post(`/doctors/${user.id}/${type}`, { appointment_id: id });
      await load();
      toast.success(
        type === "next" ? "Called in next patient" :
        type === "no-show" ? "Patient moved back" :
        "Patient marked done"
      );
    } catch (e) {
      toast.error(errMsg(e));
    }
  };

  const saveDelay = async (minutes) => {
    try {
      await api.post(`/doctors/${user.id}/delay`, { minutes });
      setDelay(minutes);
      toast.success(minutes ? `Delay set to ${minutes} min` : "Delay cleared");
    } catch (e) {
      toast.error(errMsg(e));
    }
  };

  const currentCalled = queue.find((q) => q.status === "called");
  const waiting = queue.filter((q) => q.status === "waiting");
  const nextUp = waiting[0];

  return (
    <div className="drd-page">
      <section className="drd-doctor-hero">
        <div>
          <h1 className="drd-hero-title">Hello Dr. {user?.name?.split(" ").slice(-1)[0]} <span className="drd-wave">👋</span></h1>
          <p className="drd-hero-sub">Your queue, in your rhythm.</p>
        </div>
        <div className="drd-doctor-hero-stats">
          <div><strong>{queue.length}</strong><small>In queue</small></div>
          <div><strong>{currentCalled ? "1" : "0"}</strong><small>In consultation</small></div>
          <div><strong>{delay}</strong><small>Delay (min)</small></div>
        </div>
      </section>

      <div className="drd-grid-2">
        <div className="drd-col-main">
          <Card className="drd-card">
            <CardContent>
              <div className="drd-section-head">
                <h2>Today's queue</h2>
                <span className="drd-chip-mint-small">
                  <Sparkles size={10} /> Live
                </span>
              </div>
              {queue.length === 0 ? (
                <p className="drd-muted">No patients yet. Enjoy the breathing room.</p>
              ) : (
                <div className="drd-doctor-queue">
                  {queue.map((p) => (
                    <div
                      key={p.id}
                      className={`drd-doctor-row ${p.status === "called" ? "serving" : ""}`}
                      data-testid={`patient-row-${p.id}`}
                    >
                      <span className="drd-doctor-row-num">#{p.position}</span>
                      <div className="drd-doctor-row-info">
                        <strong>{p.patient_name}</strong>
                        <small className="drd-muted">
                          {p.status === "called" ? "In consultation" : "Waiting"}
                          {" · "}{p.pushbacks || 0}/2 no-shows
                        </small>
                      </div>
                      <div className="drd-doctor-row-actions">
                        <Button
                          variant="outline"
                          size="sm"
                          onClick={() => setBrief(p)}
                          data-testid={`brief-${p.id}`}
                        >
                          <Sparkles size={13} /> Brief
                        </Button>
                        {p.status === "waiting" && p.id === nextUp?.id && (
                          <Button
                            size="sm"
                            className="drd-btn-primary"
                            onClick={() => act("next", p.id)}
                            data-testid={`next-${p.id}`}
                          >
                            Next <ChevronRight size={14} />
                          </Button>
                        )}
                        {p.status === "called" && (
                          <>
                            <Button
                              size="sm"
                              variant="outline"
                              className="drd-btn-mint-outline"
                              onClick={() => act("done", p.id)}
                              data-testid={`done-${p.id}`}
                            >
                              <CheckCircle2 size={13} /> Done
                            </Button>
                            <Button
                              size="sm"
                              variant="ghost"
                              className="drd-btn-ghost-red"
                              onClick={() => act("no-show", p.id)}
                              data-testid={`no-show-${p.id}`}
                            >
                              <UserX size={13} /> No-show
                            </Button>
                          </>
                        )}
                        {p.status === "waiting" && p.id !== nextUp?.id && (
                          <Button
                            size="sm"
                            variant="ghost"
                            className="drd-btn-ghost-red"
                            onClick={() => act("no-show", p.id)}
                            data-testid={`no-show-${p.id}`}
                          >
                            No-show
                          </Button>
                        )}
                      </div>
                    </div>
                  ))}
                </div>
              )}
            </CardContent>
          </Card>
        </div>

        <aside className="drd-col-side">
          <Card className="drd-card">
            <CardContent>
              <strong>Running late?</strong>
              <p className="drd-muted">Let patients know. Their ETAs will update instantly.</p>
              <div className="drd-delay-row">
                {[0, 5, 10, 15, 30].map((m) => (
                  <button
                    key={m}
                    onClick={() => saveDelay(m)}
                    className={m === delay ? "drd-delay-chip active" : "drd-delay-chip"}
                    data-testid={`delay-${m}`}
                  >
                    {m === 0 ? "On time" : `+${m}m`}
                  </button>
                ))}
              </div>
            </CardContent>
          </Card>

          <Card className="drd-card drd-card-mint">
            <CardContent>
              <div className="drd-mint-head">
                <Sparkles size={16} /> Dai for doctors
              </div>
              <p className="drd-muted">
                Every patient note becomes a focused Dai brief — tap any patient to review.
              </p>
              {nextUp && (
                <div className="drd-dai-next">
                  <small>NEXT UP</small>
                  <strong>{nextUp.patient_name}</strong>
                </div>
              )}
            </CardContent>
          </Card>
        </aside>
      </div>

      <Dialog open={!!brief} onOpenChange={(v) => !v && setBrief(null)}>
        <DialogContent data-testid="brief-dialog">
          <DialogHeader>
            <DialogTitle>Dai brief — {brief?.patient_name}</DialogTitle>
          </DialogHeader>
          <div className="drd-brief-body">
            <p><strong>Reason for visit</strong></p>
            <p className="drd-muted">{brief?.reason}</p>
            <p><strong>Structured summary</strong></p>
            <pre className="drd-brief-text">{brief?.brief || "Dai is preparing a summary."}</pre>
          </div>
          <DialogFooter>
            <Button onClick={() => setBrief(null)} className="drd-btn-primary">
              Got it
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>
    </div>
  );
}
