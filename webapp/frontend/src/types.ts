// Shared UI types. These mirror webapp/backend/models.py, which the FastAPI
// backend serializes as camelCase JSON.

export type AgentState = "RUNNING" | "STOPPED";

export type AiProvider = "gemini" | "openai" | "claude" | "claude_code";

export interface DashboardStats {
  bountiesFound: number;
  solved: number;
  prSubmitted: number;
  merged: number;
  estimatedEarnings: number;
  aiCost: number;
}

export type TaskStageKey = "analyze" | "code" | "test" | "pr";
export type StageStatus = "done" | "running" | "waiting" | "failed" | "skipped";

export interface CurrentTask {
  issueTitle: string;
  bountyAmount: number;
  stages: Record<TaskStageKey, StageStatus>;
}

export type Difficulty = "簡單" | "中等" | "困難";

export interface Bounty {
  id: string;
  title: string;
  repository: string;
  source: "opirebot" | "github";
  reward: number;
  language: string;
  type: string;
  difficulty: Difficulty;
  estimatedAiCost: number;
  issueUrl: string;
}

export type RunStatus = "running" | "success" | "failed";

export type RunStageKey =
  | "issue_found"
  | "repo_loaded"
  | "analyzing"
  | "generating_patch"
  | "testing"
  | "pr_submitted";

export interface RunStage {
  key: RunStageKey;
  label: string;
  status: StageStatus;
}

export interface Run {
  id: string;
  issueTitle: string;
  repository: string;
  reward: number;
  startedAt: string;
  status: RunStatus;
  stages: RunStage[];
  prUrl?: string;
  errorMessage?: string;
  logs: string[];
}

export interface BotSettings {
  githubConnected: boolean;
  githubUsername?: string;
  aiProvider: AiProvider;
  apiKeySet: boolean;
  languages: string[];
  minBounty: number;
  maxAiCost: number;
  autoSubmitPr: boolean;
  advanced: {
    pollIntervalSeconds: number;
    dockerMemoryLimit: string;
    dockerCpuLimit: number;
    maxRetries: number;
    maxParallelTests: number;
  };
}
