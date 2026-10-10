import { useEffect, useRef, useState } from "react";
import { Sparkles, X, Send } from "lucide-react";
import { API } from "../lib/api";

export default function DaiBubble() {
  const [open, setOpen] = useState(false);
  const [message, setMessage] = useState("");
  const [items, setItems] = useState([
    { from: "dai", text: "Hi, I'm Dai. Ask me about your queue, timings, or which specialty to see." },
  ]);
  const [busy, setBusy] = useState(false);
  const scroller = useRef(null);

  useEffect(() => {
    if (scroller.current) scroller.current.scrollTop = scroller.current.scrollHeight;
  }, [items, open]);

  const send = async () => {
    const text = message.trim();
    if (!text || busy) return;
    setMessage("");
    setItems((x) => [...x, { from: "user", text }, { from: "dai", text: "" }]);
    setBusy(true);
    try {
      const r = await fetch(`${API}/dai/chat`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        credentials: "include",
        body: JSON.stringify({ message: text }),
      });
      if (!r.ok) throw new Error("dai");
      const reader = r.body.getReader();
      const decoder = new TextDecoder();
      let answer = "";
      while (true) {
        const { done, value } = await reader.read();
        if (done) break;
        for (const line of decoder.decode(value).split("\n")) {
          if (line.startsWith("data:")) {
            try {
              const d = JSON.parse(line.slice(5));
              answer += d.text;
              setItems((x) => {
                const a = [...x];
                a[a.length - 1] = { from: "dai", text: answer };
                return a;
              });
            } catch {}
          }
        }
      }
    } catch {
      setItems((x) => {
        const a = [...x];
        a[a.length - 1] = { from: "dai", text: "Sign in to chat with Dai." };
        return a;
      });
    } finally {
      setBusy(false);
    }
  };

  return (
    <>
      <button
        className="drd-dai-fab"
        onClick={() => setOpen((v) => !v)}
        data-testid="dai-bubble-button"
        aria-label="Chat with Dai"
      >
        {open ? <X size={22} /> : <Sparkles size={22} />}
      </button>
      {open && (
        <div className="drd-dai-panel" data-testid="dai-panel">
          <div className="drd-dai-header">
            <span className="drd-dai-header-dot" />
            <strong>Chat with Dai</strong>
            <button
              className="drd-dai-close"
              onClick={() => setOpen(false)}
              aria-label="Close Dai"
            >
              <X size={16} />
            </button>
          </div>
          <div className="drd-dai-body" ref={scroller}>
            {items.map((m, i) => (
              <div key={i} className={`drd-dai-msg drd-dai-msg-${m.from}`}>
                {m.text || (m.from === "dai" ? "…" : "")}
              </div>
            ))}
          </div>
          <div className="drd-dai-input">
            <input
              placeholder="Ask about your appointment…"
              value={message}
              onChange={(e) => setMessage(e.target.value)}
              onKeyDown={(e) => e.key === "Enter" && send()}
              data-testid="dai-input"
            />
            <button onClick={send} data-testid="dai-send" disabled={busy}>
              <Send size={16} />
            </button>
          </div>
        </div>
      )}
    </>
  );
}
