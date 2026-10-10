import { useEffect, useState } from "react";
import { api, errMsg } from "../lib/api";
import { useAuth } from "../lib/auth";
import { Button } from "../components/ui/button";
import { Card, CardContent } from "../components/ui/card";
import { Input } from "../components/ui/input";
import { Label } from "../components/ui/label";
import { Switch } from "../components/ui/switch";
import { toast } from "sonner";

export default function DoctorSettings() {
  const { user } = useAuth();
  const [isOpen, setIsOpen] = useState(false);
  const [minutes, setMinutes] = useState(15);
  const [cap, setCap] = useState(20);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    (async () => {
      try {
        const r = await api.get("/doctors");
        const me = r.data.find((d) => d.id === user?.id);
        if (me) {
          setIsOpen(me.is_open);
          setMinutes(me.consult_minutes);
          setCap(me.daily_cap || 20);
        }
      } finally {
        setLoading(false);
      }
    })();
  }, [user?.id]);

  const save = async () => {
    try {
      await api.patch(`/doctors/${user.id}/settings`, {
        is_open: isOpen,
        consult_minutes: Number(minutes),
        daily_cap: Number(cap),
      });
      toast.success("Settings saved");
    } catch (e) {
      toast.error(errMsg(e));
    }
  };

  if (loading) return <div className="drd-loading">Loading…</div>;

  return (
    <div className="drd-page">
      <div className="drd-settings-wrap">
        <Card className="drd-card">
          <CardContent>
            <h2>Availability</h2>
            <p className="drd-muted">Patients can only join when your queue is open.</p>

            <div className="drd-setting-row">
              <div>
                <strong>Queue open today</strong>
                <small className="drd-muted">Patients can book while this is on.</small>
              </div>
              <Switch
                checked={isOpen}
                onCheckedChange={setIsOpen}
                data-testid="toggle-open"
              />
            </div>

            <div className="drd-setting-row">
              <div>
                <Label htmlFor="minutes">Average consult time (min)</Label>
                <small className="drd-muted">Used for every patient's ETA.</small>
              </div>
              <Input
                id="minutes"
                type="number"
                min={5}
                max={120}
                value={minutes}
                onChange={(e) => setMinutes(e.target.value)}
                className="drd-setting-input"
                data-testid="consult-minutes-input"
              />
            </div>

            <div className="drd-setting-row">
              <div>
                <Label htmlFor="cap">Daily patient cap</Label>
                <small className="drd-muted">Max patients that can join today.</small>
              </div>
              <Input
                id="cap"
                type="number"
                min={1}
                value={cap}
                onChange={(e) => setCap(e.target.value)}
                className="drd-setting-input"
                data-testid="daily-cap-input"
              />
            </div>

            <Button onClick={save} className="drd-btn-primary" data-testid="save-settings">
              Save availability
            </Button>
          </CardContent>
        </Card>
      </div>
    </div>
  );
}
