// src/components/BootScreen.tsx

import { useEffect, useRef, useState } from "react";
import "./BootScreen.css";

const BOOT_LINES = [
  { ts: "00:00:01", cls: "dim",  text: "BIOS CHECK COMPLETE. RAM: 32768 MB OK." },
  { ts: "00:00:02", cls: "ok",   text: "[OK] KERNEL v4.19.2 LOADED SUCCESSFULLY" },
  { ts: "00:00:03", cls: "dim",  text: "MOUNTING MERCHANT DATABASE... /dev/sda1" },
  { ts: "00:00:04", cls: "ok",   text: "[OK] MERCHANT DB: 1,247 RECORDS INDEXED" },
  { ts: "00:00:05", cls: "dim",  text: "LOADING TRIGGER DEFINITIONS... /etc/triggers.conf" },
  { ts: "00:00:06", cls: "ok",   text: "[OK] TRIGGERS: IPL, RECALL, PLANNING, RESEARCH LOADED" },
  { ts: "00:00:07", cls: "warn", text: "[WARN] CONTEXT LOADER: 5/10 SLOTS FILLED — PARTIAL LOAD" },
  { ts: "00:00:08", cls: "dim",  text: "INITIALISING INTENT CLASSIFICATION ENGINE..." },
  { ts: "00:00:09", cls: "ok",   text: "[OK] INTENT ENGINE: NEGATIVE, AFFIRMATIVE, WAIT, QUESTION" },
  { ts: "00:00:10", cls: "dim",  text: "LOADING XAI RATIONALE LAYER..." },
  { ts: "00:00:11", cls: "ok",   text: "[OK] XAI LAYER ACTIVE — EXPLAINABILITY MODULE v3.1" },
  { ts: "00:00:12", cls: "dim",  text: "ESTABLISHING UPLINK TO MAGICPIN RELAY..." },
  { ts: "00:00:13", cls: "ok",   text: "[OK] UPLINK STABLE — LATENCY: 42MS" },
  { ts: "00:00:14", cls: "dim",  text: "RUNNING ENDPOINT CONTRACT VERIFICATION..." },
  { ts: "00:00:15", cls: "ok",   text: "[OK] 5/5 ENDPOINTS SATISFIED — TARGET EDGE: JUDGE-READY" },
  { ts: "00:00:16", cls: "ok",   text: "ALL SYSTEMS GO. LAUNCHING VERAFORGE XAI CONTROL ROOM." },
];

const DOTS_UNLOCK_AT = [1, 3, 8, 10, 12]; // line indices that unlock each dot

interface Props { onComplete: () => void; }

export default function BootScreen({ onComplete }: Props) {
  const [lines, setLines] = useState<typeof BOOT_LINES>([]);
  const [pct, setPct] = useState(0);
  const [dots, setDots] = useState([false, false, false, false, false]);
  const [granted, setGranted] = useState(false);
  const logRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    let i = 0;
    let timerId: ReturnType<typeof setTimeout>;

    function step() {
      if (i >= BOOT_LINES.length) { 
        timerId = setTimeout(() => setGranted(true), 400); 
        return; 
      }
      
      const line = BOOT_LINES[i];
      if (line) {
        setLines(prev => [...prev.slice(-7), line]);
      }
      
      setPct(Math.round(((i + 1) / BOOT_LINES.length) * 100));
      const dotIdx = DOTS_UNLOCK_AT.indexOf(i);
      if (dotIdx >= 0) setDots(prev => prev.map((v, j) => j === dotIdx ? true : v));
      i++;
      timerId = setTimeout(step, i < 4 ? 320 : i < 10 ? 260 : 200);
    }
    timerId = setTimeout(step, 600);
    
    return () => clearTimeout(timerId);
  }, []);

  useEffect(() => {
    if (logRef.current) logRef.current.scrollTop = logRef.current.scrollHeight;
  }, [lines]);

  const DOT_LABELS = ["KERNEL", "MERCHANT DB", "INTENT ENGINE", "XAI LAYER", "UPLINK"];

  return (
    <div className="boot-screen">
      <div className="boot-scanlines" />
      <div className="boot-topbar">
        <span>BLTMR PLC 2.4.00 // BOOT SEQUENCE INITIATED</span>
        <span className="boot-clock">{new Date().toLocaleTimeString()}</span>
      </div>

      <div className="boot-main">
        <div className="boot-hexbg" />
        {!granted ? (
          <>
            <div className="boot-logo-wrap">
              <div className="boot-logo-eyebrow">// MAGICPIN AI CHALLENGE //</div>
              <div className="boot-logo">VERAFORGE</div>
              <div className="boot-logo-sub">XAI CONTROL ROOM</div>
              <div className="boot-logo-ver">SYS v2.4.00 &bull; BUILD 20250502</div>
            </div>
            <div className="boot-divider" />
            <div className="boot-log" ref={logRef}>
              {lines.map((l, i) => (
                <div key={i} className={`boot-log-line boot-log-${l.cls}`}>
                  <span className="boot-log-ts">[{l.ts}]</span>
                  <span>{l.text}</span>
                </div>
              ))}
            </div>
            <div className="boot-bar-wrap">
              <div className="boot-bar-label">
                <span>// SYSTEM INITIALISATION</span>
                <span>{pct < 100 ? "LOADING..." : "COMPLETE"}</span>
              </div>
              <div className="boot-bar-track">
                <div className="boot-bar-fill" style={{ width: `${pct}%` }} />
              </div>
              <div className="boot-bar-pct">{pct}%</div>
            </div>
            <div className="boot-dots">
              {DOT_LABELS.map((label, i) => (
                <div key={i} className="boot-dot-item">
                  <span className={`boot-dot ${dots[i] ? "on" : ""}`} />
                  <span className="boot-dot-label">{label}</span>
                </div>
              ))}
            </div>
          </>
        ) : (
          <div className="boot-granted">
            <div className="boot-logo" style={{ fontSize: 28, letterSpacing: 6 }}>VERAFORGE</div>
            <div className="boot-logo-sub">XAI CONTROL ROOM</div>
            <div className="boot-granted-divider" />
            <div className="boot-access-text">ACCESS GRANTED</div>
            <div className="boot-access-sub">ALL SYSTEMS OPERATIONAL &bull; 5/10 CONTEXTS LOADED</div>
            <button className="boot-enter-btn" onClick={onComplete}>
              [ ENTER SYSTEM ]
            </button>
          </div>
        )}
      </div>

      <div className="boot-bottombar">
        <span>INITIALISING VERAFORGE XAI ENGINE...</span>
        <span>PROPERTY OF VERAFORGE AI &bull; RESTRICTED ACCESS</span>
      </div>
    </div>
  );
}
