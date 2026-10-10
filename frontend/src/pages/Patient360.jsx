import { useEffect, useState } from "react";
import { useNavigate, useParams } from "react-router-dom";
import { api, errMsg } from "../lib/api";
import { Button } from "../components/ui/button";
import { Card, CardContent } from "../components/ui/card";
import { Sparkles, Pill, FileText, Search } from "lucide-react";
import { Input } from "../components/ui/input";
import { toast } from "sonner";

export default function Patient360() {
  const { patientId } = useParams();
  const nav = useNavigate();
  const [patient, setPatient] = useState(null);
  const [loading, setLoading] = useState(true);
  const [summary, setSummary] = useState("");
  const [summaryBusy, setSummaryBusy] = useState(false);
  const [search, setSearch] = useState("");
  const [results, setResults] = useState([]);

  useEffect(() => {
    (async () => {
      if (!patientId) {
        setLoading(false);
        return;
      }
      try {
        const r = await api.get(`/patients/${patientId}`);
        setPatient(r.data);
      } catch (e) {
        toast.error(errMsg(e));
      } finally {
        setLoading(false);
      }
    })();
  }, [patientId]);

  const askDai = async () => {
    setSummaryBusy(true);
    try {
      const r = await api.post(`/patients/${patientId}/summary`);
      setSummary(r.data.summary);
    } catch (e) {
      toast.error(errMsg(e));
    } finally {
      setSummaryBusy(false);
    }
  };

  const doSearch = async (q) => {
    setSearch(q);
    if (!q.trim()) { setResults([]); return; }
    try {
      const r = await api.get(`/patients?q=${encodeURIComponent(q)}`);
      setResults(r.data);
    } catch {}
  };

  if (loading) return <div className="drd-loading">Loading patient…</div>;

  if (!patient) {
    return (
      <div className="drd-page">
        <Card className="drd-card">
          <CardContent>
            <h2>Patient 360</h2>
            <p className="drd-muted">Find a patient to see their full history.</p>
            <div className="drd-form" style={{ marginTop: 12 }}>
              <div style={{ display: "flex", gap: 8 }}>
                <Search size={18} style={{ alignSelf: "center", color: "var(--drd-ink-2)" }} />
                <Input
                  placeholder="Search by name, email, phone"
                  value={search}
                  onChange={(e) => doSearch(e.target.value)}
                  data-testid="p360-search-input"
                />
              </div>
              <div className="drd-doctor-list">
                {results.map((p) => (
                  <button
                    key={p.id}
                    className="drd-doctor-row"
                    onClick={() => nav(`/patient360/${p.id}`)}
                    data-testid={`p360-result-${p.id}`}
                  >
                    <div className="drd-avatar-circle">{p.name[0]}</div>
                    <div className="drd-doctor-row-info">
                      <strong>{p.name}</strong>
                      <small className="drd-muted">{p.phone || p.email}</small>
                    </div>
                  </button>
                ))}
              </div>
            </div>
          </CardContent>
        </Card>
      </div>
    );
  }

  const v = patient.vitals || {};
  return (
    <div className="drd-page">
      <div className="drd-p360-grid">
        <div className="drd-p360-left">
          <Card className="drd-card">
            <CardContent>
              <div className="drd-p360-head">
                <div className="drd-avatar-circle lg">{patient.name[0]}</div>
                <div>
                  <h2 data-testid="p360-name">{patient.name}</h2>
                  <small className="drd-muted">
                    {patient.age ? `${patient.age} ` : ""}
                    {patient.gender ? `· ${patient.gender} ` : ""}
                    {patient.blood_type ? `· ${patient.blood_type}` : ""}
                  </small>
                </div>
              </div>
              <div className="drd-p360-meta">
                {patient.phone && <div><small>Phone:</small> {patient.phone}</div>}
                {patient.visits?.[0] && (
                  <div>
                    <small>Last visit:</small>{" "}
                    {new Date(patient.visits[0].date).toLocaleDateString("en-US", { day: "2-digit", month: "short", year: "numeric" })}
                  </div>
                )}
                {patient.allergies?.length > 0 && (
                  <div>
                    <small>Allergies:</small>{" "}
                    <span className="drd-p360-allergy" data-testid="p360-allergies">
                      {patient.allergies.join(", ")}
                    </span>
                  </div>
                )}
              </div>
              <div className="drd-p360-tags">
                {patient.conditions?.map((c, i) => (
                  <span key={i} className="drd-chip-amber">{c}</span>
                ))}
              </div>
            </CardContent>
          </Card>

          <Card className="drd-card">
            <CardContent>
              <div className="drd-section-head">
                <h3>Vitals (last visit)</h3>
                <Button
                  variant="outline"
                  size="sm"
                  className="drd-btn-mint-outline"
                  onClick={askDai}
                  disabled={summaryBusy}
                  data-testid="p360-ask-dai"
                >
                  <Sparkles size={14} /> {summaryBusy ? "Thinking…" : "Ask Dai"}
                </Button>
              </div>
              <div className="drd-vitals-grid">
                <Vital label="BP" value={v.bp || "—"} testid="vital-bp" />
                <Vital label="Weight" value={v.weight || "—"} testid="vital-weight" />
                <Vital label="Temp" value={v.temp || "—"} testid="vital-temp" />
                <Vital label="Pulse" value={v.pulse || "—"} testid="vital-pulse" />
              </div>
              {summary && (
                <div className="drd-p360-summary" data-testid="p360-summary">
                  <strong>
                    <Sparkles size={14} /> Dai summary
                  </strong>
                  <pre>{summary}</pre>
                </div>
              )}
            </CardContent>
          </Card>

          <Button className="drd-btn-primary drd-p360-cta" data-testid="p360-start-consult" onClick={() => nav("/doctor")}>
            Start consultation
          </Button>
        </div>

        <Card className="drd-card">
          <CardContent>
            <div className="drd-section-head">
              <h3>Visit history</h3>
              <Button
                variant="outline"
                size="sm"
                className="drd-btn-mint-outline"
                onClick={askDai}
                disabled={summaryBusy}
                data-testid="p360-summarize"
              >
                <Sparkles size={14} /> Summarize with Dai
              </Button>
            </div>

            {patient.visits?.length === 0 && (
              <p className="drd-muted">No past visits recorded.</p>
            )}

            <div className="drd-timeline">
              {patient.visits.map((visit) => (
                <div key={visit.id} className="drd-timeline-item" data-testid={`visit-${visit.id}`}>
                  <span className="drd-timeline-dot" />
                  <div className="drd-timeline-body">
                    <div className="drd-timeline-head">
                      <div>
                        <strong>{visit.condition}</strong>
                        <small className="drd-muted">{visit.doctor_name}</small>
                      </div>
                      <small className="drd-muted">
                        {new Date(visit.date).toLocaleDateString("en-US", { day: "2-digit", month: "short", year: "numeric" })}
                      </small>
                    </div>
                    {visit.medications?.length > 0 && (
                      <div className="drd-timeline-row">
                        <Pill size={14} className="drd-icon-amber" />
                        {visit.medications.join(" · ")}
                      </div>
                    )}
                    {visit.notes && (
                      <div className="drd-timeline-row">
                        <FileText size={14} />
                        {visit.notes}
                      </div>
                    )}
                  </div>
                </div>
              ))}
            </div>
          </CardContent>
        </Card>
      </div>
    </div>
  );
}

function Vital({ label, value, testid }) {
  return (
    <div className="drd-vital">
      <small>{label}</small>
      <strong data-testid={testid}>{value}</strong>
    </div>
  );
}
