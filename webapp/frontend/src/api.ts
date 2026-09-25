import type { AgentState, BotSettings, Bounty, Run } from "./types";

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  const res = await fetch(`/api${path}`, {
    headers: { "Content-Type": "application/json", "X-Bounty-Bot-Client": "1" },
    ...init,
  });
  if (!res.ok) {
    const body = await res.json().catch(() => ({}));
    throw new Error(body.detail || `請求失敗（${res.status}）`);
  }
  return res.json() as Promise<T>;
}

export interface AgentStatus {
  state: AgentState;
  lastError?: string | null;
}

export interface GithubConnectResult {
  connected: boolean;
  username?: string | null;
  error?: string | null;
}

export const api = {
  getStatus: () => request<AgentStatus>("/agent/status"),
  startAgent: () => request<AgentStatus>("/agent/start", { method: "POST" }),
  stopAgent: () => request<AgentStatus>("/agent/stop", { method: "POST" }),

  getBounties: () => request<Bounty[]>("/bounties"),
  solveBounty: (bountyId: string) => request<Run>(`/bounties/${bountyId}/solve`, { method: "POST" }),

  getRuns: () => request<Run[]>("/runs"),
  retryRun: (runId: string) => request<Run>(`/runs/${runId}/retry`, { method: "POST" }),

  getSettings: () => request<BotSettings>("/settings"),
  saveSettings: (patch: Partial<BotSettings> & { apiKey?: string }) =>
    request<BotSettings>("/settings", { method: "POST", body: JSON.stringify(patch) }),

  connectGithub: (token: string) =>
    request<GithubConnectResult>("/settings/github/connect", {
      method: "POST",
      body: JSON.stringify({ token }),
    }),
};
