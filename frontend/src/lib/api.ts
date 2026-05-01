export type TickAction = {
  conversation_id: string;
  merchant_id: string;
  customer_id: string | null;
  send_as: "vera" | "merchant_on_behalf";
  trigger_id: string;
  template_name: string;
  template_params: string[];
  body: string;
  cta: "yes_stop" | "open_ended" | "none";
  suppression_key: string;
  rationale: string;
};

export type ReplyResult = {
  action: "send" | "wait" | "end";
  body?: string | null;
  cta?: "yes_stop" | "open_ended" | "none" | null;
  wait_seconds?: number | null;
  rationale: string;
};

export type DemoState = {
  categories: Array<Record<string, unknown>>;
  merchants: Array<Record<string, unknown>>;
  customers: Array<Record<string, unknown>>;
  triggers: Array<Record<string, unknown>>;
  conversations: Array<Record<string, unknown>>;
};

const API_BASE = import.meta.env.VITE_API_BASE ?? "";

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  const response = await fetch(`${API_BASE}${path}`, {
    headers: {
      "Content-Type": "application/json",
      ...(init?.headers ?? {})
    },
    ...init
  });

  if (!response.ok) {
    const text = await response.text();
    throw new Error(text || `Request failed: ${response.status}`);
  }

  return response.json() as Promise<T>;
}

export const api = {
  bootstrap: () => request<{ ok: boolean; counts: Record<string, number> }>("/v1/demo/bootstrap", { method: "POST" }),
  state: () => request<DemoState>("/v1/demo/state"),
  tick: (triggerId: string) =>
    request<{ actions: TickAction[] }>("/v1/tick", {
      method: "POST",
      body: JSON.stringify({
        now: new Date().toISOString(),
        available_triggers: [triggerId]
      })
    }),
  reply: (payload: Record<string, unknown>) =>
    request<ReplyResult>("/v1/reply", {
      method: "POST",
      body: JSON.stringify(payload)
    })
};
