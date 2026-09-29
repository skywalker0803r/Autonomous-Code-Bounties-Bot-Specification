import { createContext, useCallback, useContext, useEffect, useRef, useState, type ReactNode } from "react";
import type { AgentState, Bounty, BotSettings, Run } from "../types";
import { api, type GithubConnectResult } from "../api";

const EMPTY_SETTINGS: BotSettings = {
  githubConnected: false,
  aiProvider: "gemini",
  apiKeySet: false,
  localBaseUrl: "http://127.0.0.1:11434/v1",
  localApiKeySet: false,
  languages: [],
  minBounty: 50,
  maxAiCost: 5,
  autoSubmitPr: true,
  emailNotifications: false,
  smtpPort: 587,
  smtpPasswordSet: false,
  advanced: {
    pollIntervalSeconds: 300,
    dockerMemoryLimit: "4g",
    dockerCpuLimit: 2,
    maxRetries: 3,
    maxParallelTests: 1,
  },
};

interface AppStateValue {
  onboarded: boolean;
  completeOnboarding: () => void;
  backendOnline: boolean;
  agentState: AgentState;
  agentError: string | null;
  setAgentState: (s: AgentState) => void;
  bounties: Bounty[];
  runs: Run[];
  activeRun: Run | undefined;
  startRunFromBounty: (bounty: Bounty) => Promise<void>;
  retryRun: (runId: string) => Promise<void>;
  deleteRun: (runId: string) => Promise<void>;
  settings: BotSettings;
  settingsLoaded: boolean;
  updateSettings: (patch: Partial<BotSettings> & { apiKey?: string; smtpPassword?: string }) => Promise<void>;
  connectGithub: (token: string) => Promise<GithubConnectResult>;
}

const AppStateContext = createContext<AppStateValue | null>(null);

export function AppStateProvider({ children }: { children: ReactNode }) {
  const [onboarded, setOnboarded] = useState<boolean>(() => localStorage.getItem("bb_onboarded") === "1");
  const [backendOnline, setBackendOnline] = useState(true);
  const [agentState, setAgentStateRaw] = useState<AgentState>("STOPPED");
  const [agentError, setAgentError] = useState<string | null>(null);
  const [bounties, setBounties] = useState<Bounty[]>([]);
  const [runs, setRuns] = useState<Run[]>([]);
  const [settings, setSettings] = useState<BotSettings>(EMPTY_SETTINGS);
  const [settingsLoaded, setSettingsLoaded] = useState(false);
  const settingsFetchStarted = useRef(false);

  const completeOnboarding = useCallback(() => {
    localStorage.setItem("bb_onboarded", "1");
    setOnboarded(true);
  }, []);

  const refresh = useCallback(async () => {
    try {
      const [status, bountyList, runList] = await Promise.all([api.getStatus(), api.getBounties(), api.getRuns()]);
      setAgentStateRaw(status.state);
      setAgentError(status.lastError ?? null);
      setBounties(bountyList);
      setRuns(runList);
      setBackendOnline(true);

      if (!settingsFetchStarted.current) {
        settingsFetchStarted.current = true;
        setSettings(await api.getSettings());
        setSettingsLoaded(true);
      }
    } catch {
      setBackendOnline(false);
    }
  }, []);

  useEffect(() => {
    refresh();
    const interval = window.setInterval(refresh, 3000);
    return () => window.clearInterval(interval);
  }, [refresh]);

  const setAgentState = useCallback((next: AgentState) => {
    const action = next === "RUNNING" ? api.startAgent() : api.stopAgent();
    action
      .then((status) => {
        setAgentStateRaw(status.state);
        setAgentError(status.lastError ?? null);
      })
      .catch((e: Error) => setAgentError(e.message));
  }, []);

  const startRunFromBounty = useCallback(async (bounty: Bounty) => {
    const run = await api.solveBounty(bounty.id);
    setRuns((prev) => [run, ...prev.filter((r) => r.id !== run.id)]);
  }, []);

  const retryRun = useCallback(async (runId: string) => {
    const run = await api.retryRun(runId);
    setRuns((prev) => prev.map((r) => (r.id === runId ? run : r)));
  }, []);

  const deleteRun = useCallback(async (runId: string) => {
    await api.deleteRun(runId);
    setRuns((prev) => prev.filter((r) => r.id !== runId));
  }, []);

  const updateSettings = useCallback(async (patch: Partial<BotSettings> & { apiKey?: string; smtpPassword?: string }) => {
    const next = await api.saveSettings(patch);
    setSettings(next);
  }, []);

  const connectGithub = useCallback(async (token: string) => {
    const result = await api.connectGithub(token);
    if (result.connected) {
      setSettings((prev) => ({ ...prev, githubConnected: true, githubUsername: result.username ?? undefined }));
    }
    return result;
  }, []);

  const activeRun = runs.find((r) => r.status === "running");

  const value: AppStateValue = {
    onboarded,
    completeOnboarding,
    backendOnline,
    agentState,
    agentError,
    setAgentState,
    bounties,
    runs,
    activeRun,
    startRunFromBounty,
    retryRun,
    deleteRun,
    settings,
    settingsLoaded,
    updateSettings,
    connectGithub,
  };

  return <AppStateContext.Provider value={value}>{children}</AppStateContext.Provider>;
}

export function useAppState() {
  const ctx = useContext(AppStateContext);
  if (!ctx) throw new Error("useAppState must be used within AppStateProvider");
  return ctx;
}
