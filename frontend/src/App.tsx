import { useEffect, useState, useRef } from "react";
import { Transcript } from "./components/Transcript";
import { RetroChart } from "./components/RetroChart";
import { RadarMap } from "./components/RadarMap";
import BootScreen from "./components/BootScreen";
import { api, type DemoState, type ReplyResult, type TickAction } from "./lib/api";

type Merchant = Record<string, unknown> & {
  merchant_id: string;
  category_slug: string;
  identity?: {
    name?: string;
    city?: string;
    locality?: string;
    owner_first_name?: string;
  };
  signals?: string[];
};

type Trigger = Record<string, unknown> & {
  id: string;
  kind: string;
  scope: "merchant" | "customer";
  merchant_id: string;
  customer_id?: string | null;
  urgency?: number;
  payload?: Record<string, unknown>;
};

type Conversation = Record<string, unknown> & {
  conversation_id: string;
  trigger_id: string;
  merchant_id: string;
  customer_id?: string | null;
  history?: Array<{ at: string; from: string; body: string; cta?: string; intent?: string; rationale?: string }>;
};

export default function App() {
  const [state, setState] = useState<DemoState | null>(null);
  const [selectedMerchantId, setSelectedMerchantId] = useState<string>("");
  const [selectedTriggerId, setSelectedTriggerId] = useState<string>("");
  const [activeConversationId, setActiveConversationId] = useState<string>("");
  const [replyDraft, setReplyDraft] = useState("");
  const [lastAction, setLastAction] = useState<TickAction | null>(null);
  const [loading, setLoading] = useState(true);
  const [working, setWorking] = useState(false);
  const [error, setError] = useState<string>("");
  const [bootComplete, setBootComplete] = useState(false);
  const [activeTab, setActiveTab] = useState("CHAT");
  const [soundEnabled, setSoundEnabled] = useState(true);
  const chatBottomRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    void initialize();
  }, []);

  async function initialize() {
    try {
      setLoading(true);
      setError("");
      
      await api.bootstrap();
      const res = await api.state(); // get latest state
      setState(res);

      // grab first merchant
      const firstMerchant = (res.merchants[0] as Merchant | undefined)?.merchant_id ?? "";
      setSelectedMerchantId(firstMerchant);

      const firstTrigger = (res.triggers.find((item) => (item as Trigger).merchant_id === firstMerchant) as Trigger | undefined)?.id ?? "";
      setSelectedTriggerId(firstTrigger);
    } catch (err) {
      console.error(err);
      setError(err instanceof Error ? err.message : "failed to boot api");
    } finally {
      setLoading(false);
    }
  }

  async function refreshState() {
    const res = await api.state();
    setState(res);
    // hack to force scroll after state updates
    setTimeout(() => {
      chatBottomRef.current?.scrollIntoView({ behavior: "smooth" });
    }, 100);
  }

  const merchants = (state?.merchants as Merchant[] | undefined) ?? [];
  const selectedMerchant = merchants.find(m => m.merchant_id === selectedMerchantId) ?? null;
  const triggers = (state?.triggers as Trigger[] | undefined) ?? [];
  const conversations = (state?.conversations as Conversation[] | undefined) ?? [];

  const visibleTriggers = triggers.filter((trigger) => trigger.merchant_id === selectedMerchantId);
  const selectedTrigger = visibleTriggers.find((trigger) => trigger.id === selectedTriggerId) ?? visibleTriggers[0] ?? null;
  const activeConversation = conversations.find((conversation) => conversation.conversation_id === activeConversationId) ?? null;

  useEffect(() => {
    if (!selectedTrigger && visibleTriggers[0]) {
      setSelectedTriggerId(visibleTriggers[0].id);
    }
  }, [selectedTrigger, visibleTriggers]);

  async function generateMove() {
    if (!selectedTrigger) return;
    try {
      setWorking(true);
      setError("");
      const result = await api.tick(selectedTrigger.id);
      const action = result.actions.find((item) => item.trigger_id === selectedTrigger.id) ?? result.actions[0] ?? null;
      if (!action) throw new Error("NO ACTION RECEIVED");
      setLastAction(action);
      setActiveConversationId(action.conversation_id);
      await refreshState();
    } catch (err) {
      setError(err instanceof Error ? err.message : "ERR: GENERATE FAILED");
    } finally {
      setWorking(false);
    }
  }

  async function sendReply() {
    if (!activeConversation || !replyDraft.trim()) return;
    try {
      setWorking(true);
      setError("");
      await api.reply({
        conversation_id: activeConversation.conversation_id,
        merchant_id: activeConversation.merchant_id,
        customer_id: activeConversation.customer_id ?? null,
        from_role: activeConversation.customer_id ? "customer" : "merchant",
        message: replyDraft,
        received_at: new Date().toISOString(),
        turn_number: ((activeConversation.history?.length ?? 0) + 1)
      });
      setReplyDraft("");
      await refreshState();
    } catch (err) {
      setError(err instanceof Error ? err.message : "ERR: TRANSMISSION FAILED");
    } finally {
      setWorking(false);
    }
  }

  if (loading || !bootComplete) {
    return <BootScreen onComplete={() => setBootComplete(true)} />;
  }

  return (
    <main className="app-wrapper">
      <div className="app-frame">
        <div className="top-bar">
          <span>VERAFORGE XAI SYS v2.4.00</span>
          <span>
            <button 
              onClick={() => setSoundEnabled(!soundEnabled)} 
              style={{ background: 'none', border: 'none', color: 'var(--phosphor-dim)', marginRight: '16px' }}
            >
              [ SOUND: {soundEnabled ? "ON" : "OFF"} ]
            </button>
            SYS OK <span className="blinking-cursor"></span>
          </span>
        </div>
        
        <div className="tab-bar">
          <div className={`tab ${activeTab === "CHAT" ? "active" : ""}`} onClick={() => setActiveTab("CHAT")}>CHAT</div>
          <div className="tab">CONTACTS</div>
          <div className="tab">INTENTS</div>
          <div className="tab">TRIGGERS</div>
          <div className={`tab ${activeTab === "MAP" ? "active" : ""}`} onClick={() => setActiveTab("MAP")}>MAP</div>
        </div>

        <div className="main-content">
          <div className="sidebar-left">
            <div className="section-label">// THREADS</div>
            {merchants.map((merchant) => {
              const isActive = merchant.merchant_id === selectedMerchantId;
              return (
                <div 
                  key={merchant.merchant_id} 
                  className={`contact-item ${isActive ? "active" : ""}`}
                  onClick={() => {
                    setSelectedMerchantId(merchant.merchant_id);
                    const t = triggers.find(t => t.merchant_id === merchant.merchant_id)?.id ?? "";
                    setSelectedTriggerId(t);
                    setActiveConversationId("");
                  }}
                >
                  <div className="contact-name">[{isActive ? "*" : " "}] {merchant.identity?.name?.substring(0, 15)}</div>
                  <div className="contact-meta">
                    {merchant.identity?.city}
                  </div>
                </div>
              );
            })}
          </div>

          {activeTab === "MAP" ? (
            <RadarMap city={selectedMerchant?.identity?.city} locality={selectedMerchant?.identity?.locality} />
          ) : (
            <div className="chat-panel">
              {error && <div className="error-msg">{error}</div>}
              
              <Transcript items={activeConversation?.history ?? []} soundEnabled={soundEnabled} />
              <div ref={chatBottomRef} />
              
              <div className="chat-input-area">
                {!activeConversation ? (
                  <div className="actions-row" style={{ justifyContent: "space-between" }}>
                    <div style={{ display: 'flex', gap: '8px', flex: 1 }}>
                      <select 
                        value={selectedTriggerId} 
                        onChange={(e) => setSelectedTriggerId(e.target.value)}
                        style={{ flex: 1 }}
                      >
                        {visibleTriggers.map(t => <option key={t.id} value={t.id}>TRG: {t.kind.toUpperCase()}</option>)}
                        {!visibleTriggers.length && <option value="">NO TRIGGERS</option>}
                      </select>
                      <button onClick={() => void generateMove()} disabled={working || !selectedTrigger}>
                        {working ? "GEN..." : "INIT SEQUENCE"}
                      </button>
                    </div>
                  </div>
                ) : (
                  <>
                    <textarea 
                      rows={3} 
                      value={replyDraft}
                      onChange={(e) => setReplyDraft(e.target.value)}
                      placeholder="> ENTER TRANSMISSION..."
                      onKeyDown={(e) => {
                        if (e.key === "Enter" && !e.shiftKey) {
                          e.preventDefault();
                          void sendReply();
                        }
                      }}
                    />
                    <div className="actions-row">
                      <button onClick={() => { setReplyDraft("Stop messaging me, not interested."); setTimeout(sendReply, 500); }} style={{ background: 'transparent', color: 'var(--int-wait)' }}>
                        [ RUN SIMULATION ]
                      </button>
                      <button onClick={() => void sendReply()} disabled={working || !replyDraft.trim()}>
                        {working ? "TRANSMITTING..." : "SEND"}
                      </button>
                    </div>
                  </>
                )}
              </div>
            </div>
          )}

          <div className="sidebar-right">
            <div className="section-label">// XAI METRICS</div>
            
            <RetroChart merchantId={selectedMerchantId} />

            <div className="metric-block" style={{marginTop: '16px'}}>
              <div className="metric-label">TURNS</div>
              <div className="metric-value">{activeConversation?.history?.length ?? 0}</div>
            </div>
            <div className="metric-block">
              <div className="metric-label">CTX LOADED</div>
              <div className="metric-value">{state?.merchants.length ?? 0}</div>
            </div>
            {lastAction && (
               <div className="metric-block">
                 <div className="metric-label">LAST TEMPLATE</div>
                 <div className="metric-value" style={{fontSize: '0.8rem'}}>{lastAction.template_name}</div>
               </div>
            )}
            <div className="metric-block">
              <div className="metric-label">SYSTEM UPTIME</div>
              <div className="metric-value">{(state?.conversations.length ?? 0) * 12}M</div>
            </div>
            <button style={{marginTop: '16px', fontSize: '0.7rem'}} onClick={() => void initialize()} disabled={working}>
              RESET SYSTEM
            </button>
          </div>
        </div>

        <div className="bottom-bar">
          <div className="status-left">
            <span>LOW SIGNAL</span>
            <span>UPLINK: STABLE</span>
          </div>
          <span>VERAFORGE (C)</span>
        </div>
      </div>
    </main>
  );
}
