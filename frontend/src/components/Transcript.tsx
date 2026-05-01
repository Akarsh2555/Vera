import { useState, useEffect } from "react";

type TranscriptItem = {
  at: string;
  from: string;
  body: string;
  cta?: string;
  intent?: string;
  rationale?: string;
};

type TranscriptProps = {
  items: TranscriptItem[];
  soundEnabled?: boolean;
};

// Initialize audio context lazily so it doesn't crash SSR or before user interaction
let audioCtx: AudioContext | null = null;
function playKeystroke() {
  try {
    if (!audioCtx) audioCtx = new (window.AudioContext || (window as any).webkitAudioContext)();
    if (audioCtx.state === 'suspended') void audioCtx.resume();
    const osc = audioCtx.createOscillator();
    const gainNode = audioCtx.createGain();
    osc.type = "square";
    osc.frequency.setValueAtTime(800 + Math.random() * 200, audioCtx.currentTime); 
    gainNode.gain.setValueAtTime(0.02, audioCtx.currentTime);
    gainNode.gain.exponentialRampToValueAtTime(0.001, audioCtx.currentTime + 0.05);
    osc.connect(gainNode);
    gainNode.connect(audioCtx.destination);
    osc.start();
    osc.stop(audioCtx.currentTime + 0.05);
  } catch (e) {
    // Ignore audio errors
  }
}

function MessageBubble({ item, soundEnabled }: { item: TranscriptItem, soundEnabled?: boolean }) {
  const [showRationale, setShowRationale] = useState(false);
  const [displayedBody, setDisplayedBody] = useState(item.from === "user" ? item.body : "");

  useEffect(() => {
    if (item.from === "user") {
      setDisplayedBody(item.body);
      return;
    }
    
    // Typewriter effect for bot messages
    let i = 0;
    setDisplayedBody("");
    const interval = setInterval(() => {
      setDisplayedBody((prev) => prev + item.body.charAt(i));
      if (soundEnabled && i % 2 === 0) playKeystroke(); // play every other char so it's not too aggressive
      i++;
      if (i >= item.body.length) {
        clearInterval(interval);
      }
    }, 20); // 20ms per character

    return () => clearInterval(interval);
  }, [item.body, item.from, soundEnabled]);

  const intentClass = item.intent ? `badge intent-${item.intent.toLowerCase()}` : "badge";

  return (
    <div className={`message ${item.from}`}>
      <span className="message-prefix">
        {item.from === "bot" ? "# BOT:" : "> YOU:"} [{new Date(item.at).toLocaleTimeString()}]
      </span>
      <div className="message-body">
        {displayedBody}
        {item.from === "bot" && displayedBody.length < item.body.length && <span className="blinking-cursor"></span>}
      </div>
      <div className="message-actions">
        {item.intent ? <span className={intentClass}>[{item.intent.toUpperCase()}]</span> : null}
        {item.cta ? <span className="badge">[CTA: {item.cta.toUpperCase()}]</span> : null}
        {item.rationale ? (
          <button 
            className="rationale-btn" 
            onClick={() => setShowRationale(!showRationale)}
          >
            {showRationale ? "[- RATIONALE]" : "[+ RATIONALE]"}
          </button>
        ) : null}
      </div>
      {showRationale && item.rationale ? (
        <div className="rationale-drawer">
          <span className="drawer-label">// AI RATIONALE</span>
          {item.rationale}
        </div>
      ) : null}
    </div>
  );
}

export function Transcript({ items, soundEnabled }: TranscriptProps) {
  if (!items.length) {
    return <div className="empty-state">// NO ACTIVE THREAD</div>;
  }

  return (
    <div className="chat-history">
      {items.map((item, index) => (
        <MessageBubble key={`${item.at}-${index}`} item={item} soundEnabled={soundEnabled} />
      ))}
    </div>
  );
}
