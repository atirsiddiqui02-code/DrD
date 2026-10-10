import { useEffect, useState, useCallback } from "react";
import { useNavigate } from "react-router-dom";
import { api, errMsg } from "../lib/api";
import { Button } from "../components/ui/button";
import { Card, CardContent } from "../components/ui/card";
import {
  Dialog, DialogContent, DialogHeader, DialogTitle, DialogFooter,
} from "../components/ui/dialog";
import { Input } from "../components/ui/input";
import { Label } from "../components/ui/label";
import { Textarea } from "../components/ui/textarea";
import { Sparkles, UserPlus, Plus, ChevronRight, Search } from "lucide-react";
import { toast } from "sonner";

const STATUS_LABEL = {
  booked: "booked",
  waiting: "waiting",
  called: "in-consult",
  done: "completed",
  cancelled: "cancelled",
};
const STATUS_CLASS = {
  booked: "amber",
  waiting: "amber",
  called: "blue",
  done: "mint",
  cancelled: "muted",
};

export default function ReceptionDashboard() {
  const nav = useNavigate();
  const [data, setData] = useState(null);
  const [walkIn, setWalkIn] = useState(null); // doctor object or null
  const [form, setForm] = useState({ name: "", phone: "", reason: "" });
  const [patientSearch, setPatientSearch] = useState(false);
  const [patientResults, setPatientResults] = useState([]);
  const [query, setQuery] = useState("");

  const load = useCallback(async () => {
    try {
      const r = await api.get("/reception/dashboard");
      setData(r.data);
    } catch (e) {
      toast.error(errMsg(e));
    }
  }, []);

  useEffect(() => {
    load();
    const t = setInterval(load, 7000);
    return () => clearInterval(t);
  }, [load]);

  const submitWalkIn = async () => {
    if (!walkIn || !form.name.trim() || !form.reason.trim()) {
      toast.error("Please fill name and reason");
      return;
    }
    try {
      await api.post("/reception/walk-in", {
        doctor_id: walkIn.doctor_id,
        patient_name: form.name.trim(),
        phone: form.phone.trim(),
        reason: form.reason.trim(),
      });
      toast.success(`Added ${form.name} to ${walkIn.name}'s queue`);
      setWalkIn(null);
      setForm({ name: "", phone: "", reason: "" });
      load();
    } catch (e) {
      toast.error(errMsg(e));
    }
  };

  const searchPatients = async (q) => {
    setQuery(q);
    if (!q.trim()) { setPatientResults([]); return; }
    try {
      const r = await api.get(`/patients?q=${encodeURIComponent(q)}`);
      setPatientResults(r.data);
    } catch {}
  };

  const callNext = async (doctorId, rows) => {
    const next = rows.find((r) => r.status === "waiting");
    if (!next) { toast.info("No waiting patients"); return; }
    try {
      await api.post(`/doctors/${doctorId}/next`, { appointment_id: next.id });
      toast.success(`Called ${next.patient_name}`);
      load();
    } catch (e) {
      toast.error(errMsg(e));
    }
  };

  if (!data) return <div className="drd-loading">Loading reception…</div>;

  const dateStr = new Date(data.date).toLocaleDateString("en-US", { weekday: "short", day: "2-digit", month: "short" });

  return (
    <div className="drd-page">
      <section className="drd-reception-head">
        <div>
          <h1 className="drd-rec-title">Today · {dateStr}</h1>
          <p className="drd-muted">Dr.D Partner Clinic · Reception view</p>
        </div>
        <div className="drd-rec-actions">
          <Button
            variant="outline"
            onClick={() => setPatientSearch(true)}
            data-testid="rec-patient-360"
          >
            <Search size={14} /> Patient 360
          </Button>
          <Button
            variant="outline"
            onClick={() => data.doctors[0] && setWalkIn(data.doctors[0])}
            data-testid="rec-walk-in"
          >
            <UserPlus size={14} /> Walk-in
          </Button>
          <Button
            className="drd-btn-primary"
            onClick={() => nav("/book")}
            data-testid="rec-book"
          >
            <Plus size={14} /> Book
          </Button>
        </div>
      </section>

      <div className="drd-rec-stats">
        <StatCard label="Booked today" value={data.totals.booked + data.totals.checked_in + data.totals.in_consult + data.totals.completed} tone="ink" testid="stat-booked" />
        <StatCard label="Checked in" value={data.totals.checked_in} tone="amber" testid="stat-checked" />
        <StatCard label="In consult" value={data.totals.in_consult} tone="blue" testid="stat-inconsult" />
        <StatCard label="Completed" value={data.totals.completed} tone="mint" testid="stat-completed" />
      </div>

      <div className="drd-rec-grid">
        {data.doctors.map((d) => (
          <Card key={d.doctor_id} className="drd-card drd-rec-col">
            <CardContent>
              <div className="drd-rec-col-head">
                <div>
                  <strong>{d.name}</strong>
                  <small className="drd-muted">{d.specialty}</small>
                </div>
                <span className="drd-rec-delay-chip">
                  {d.delay_minutes > 0 ? `Delay +${d.delay_minutes}m` : "On time"}
                </span>
              </div>
              <div className="drd-rec-rows">
                {d.rows.length === 0 ? (
                  <p className="drd-muted">No one in queue yet.</p>
                ) : (
                  d.rows.map((row) => (
                    <div key={row.id} className="drd-rec-row" data-testid={`rec-row-${row.id}`}>
                      <span className="drd-rec-pos">{String(row.position).padStart(2, "0")}</span>
                      <button
                        className="drd-rec-name"
                        onClick={() => nav(`/patient360/${row.patient_id}`)}
                        data-testid={`rec-open-patient-${row.patient_id}`}
                      >
                        {row.patient_name}
                      </button>
                      <span className={`drd-rec-pill drd-rec-pill-${STATUS_CLASS[row.status] || "muted"}`}>
                        {STATUS_LABEL[row.status] || row.status}
                      </span>
                    </div>
                  ))
                )}
              </div>
              <Button
                className="drd-btn-primary drd-rec-call"
                onClick={() => callNext(d.doctor_id, d.rows)}
                data-testid={`rec-call-next-${d.doctor_id}`}
              >
                Call next <ChevronRight size={14} />
              </Button>
              <Button
                variant="outline"
                size="sm"
                className="drd-rec-walk-mini"
                onClick={() => setWalkIn(d)}
                data-testid={`rec-walkin-${d.doctor_id}`}
              >
                <UserPlus size={12} /> Walk-in to {d.name.split(" ").slice(-1)[0]}
              </Button>
            </CardContent>
          </Card>
        ))}
      </div>

      {/* Walk-in dialog */}
      <Dialog open={!!walkIn} onOpenChange={(v) => !v && setWalkIn(null)}>
        <DialogContent data-testid="walkin-dialog">
          <DialogHeader>
            <DialogTitle>Walk-in — {walkIn?.name}</DialogTitle>
          </DialogHeader>
          <div className="drd-form">
            <div>
              <Label>Patient name</Label>
              <Input
                value={form.name}
                onChange={(e) => setForm({ ...form, name: e.target.value })}
                data-testid="walkin-name"
              />
            </div>
            <div>
              <Label>Phone (optional)</Label>
              <Input
                value={form.phone}
                onChange={(e) => setForm({ ...form, phone: e.target.value })}
                data-testid="walkin-phone"
              />
            </div>
            <div>
              <Label>Reason for visit</Label>
              <Textarea
                rows={3}
                value={form.reason}
                onChange={(e) => setForm({ ...form, reason: e.target.value })}
                data-testid="walkin-reason"
              />
            </div>
          </div>
          <DialogFooter>
            <Button variant="outline" onClick={() => setWalkIn(null)}>Cancel</Button>
            <Button
              className="drd-btn-primary"
              onClick={submitWalkIn}
              data-testid="walkin-submit"
            >
              Add to queue
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>

      {/* Patient search */}
      <Dialog open={patientSearch} onOpenChange={setPatientSearch}>
        <DialogContent data-testid="patient-search-dialog">
          <DialogHeader>
            <DialogTitle>Find a patient</DialogTitle>
          </DialogHeader>
          <Input
            placeholder="Search by name, email or phone"
            value={query}
            onChange={(e) => searchPatients(e.target.value)}
            data-testid="patient-search-input"
          />
          <div className="drd-doctor-list" style={{ maxHeight: 320, overflowY: "auto" }}>
            {patientResults.map((p) => (
              <button
                key={p.id}
                className="drd-doctor-row"
                onClick={() => { setPatientSearch(false); nav(`/patient360/${p.id}`); }}
                data-testid={`search-result-${p.id}`}
              >
                <div className="drd-avatar-circle">{p.name[0]}</div>
                <div className="drd-doctor-row-info">
                  <strong>{p.name}</strong>
                  <small className="drd-muted">{p.phone || p.email}</small>
                </div>
                <ChevronRight size={14} className="drd-chevron" />
              </button>
            ))}
            {query && patientResults.length === 0 && (
              <p className="drd-muted">No matches.</p>
            )}
          </div>
        </DialogContent>
      </Dialog>
    </div>
  );
}

function StatCard({ label, value, tone, testid }) {
  return (
    <Card className="drd-card drd-stat-card drd-stat-wide">
      <CardContent>
        <small>{label}</small>
        <strong className={`drd-stat-tone-${tone}`} data-testid={testid}>{value}</strong>
      </CardContent>
    </Card>
  );
}
