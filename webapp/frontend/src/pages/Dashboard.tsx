import { Play, Square, Target, CheckCircle2, GitPullRequest, GitMerge, DollarSign, Cpu } from "lucide-react";
import { Button } from "../components/Button";
import { StatCard } from "../components/StatCard";
import { PipelineStepper } from "../components/PipelineStepper";
import { useAppState } from "../state/AppState";
import type { StageStatus } from "../types";

function combine(statuses: StageStatus[]): StageStatus {
  if (statuses.some((s) => s === "failed")) return "failed";
  if (statuses.every((s) => s === "done" || s === "skipped")) return "done";
  if (statuses.some((s) => s === "running")) return "running";
  return "waiting";
}

function deriveTaskStages(stageStatuses: StageStatus[]) {
  // Collapse the 6 detailed run stages into the 4 the Dashboard shows:
  // Analyze -> Code -> Test -> PR
  const [issueFound, repoLoaded, analyzing, generating, testing, pr] = stageStatuses;
  return [
    { label: "分析", status: combine([issueFound, repoLoaded, analyzing]) },
    { label: "修補", status: generating },
    { label: "測試", status: testing },
    { label: "PR", status: pr },
  ];
}

export function Dashboard() {
  const { agentState, agentError, setAgentState, bounties, runs, activeRun } = useAppState();
  const isRunning = agentState === "RUNNING";

  const solved = runs.filter((r) => r.status === "success").length;
  const prSubmitted = runs.filter((r) => !!r.prUrl).length;
  const estimatedEarnings = runs
    .filter((r) => r.status === "success" && !r.duplicatePr)
    .reduce((sum, r) => sum + r.reward, 0);
  const aiCost = runs
    .filter((r) => r.stages.some((s) => s.key === "generating_patch" && (s.status === "done" || s.status === "skipped")))
    .reduce((sum, r) => sum + (bounties.find((b) => b.repository === r.repository)?.estimatedAiCost ?? 0), 0);

  return (
    <div className="space-y-6">
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-xl font-semibold text-ink">儀表板</h1>
          <p className="text-sm text-muted">快速掌握 Agent 現在正在做什麼。</p>
        </div>
      </div>

      <div className="rounded-xl border border-border bg-panel p-5">
        <div className="flex items-center justify-between">
          <div className="flex items-center gap-3">
            <span className={`h-2.5 w-2.5 rounded-full ${isRunning ? "bg-action" : "bg-muted"}`} />
            <div>
              <p className="text-sm text-muted">Agent 狀態</p>
              <p className={`text-lg font-semibold ${isRunning ? "text-action" : "text-ink"}`}>
                {isRunning ? "運行中" : "已停止"}
              </p>
            </div>
          </div>
          {isRunning ? (
            <Button variant="danger" onClick={() => setAgentState("STOPPED")}>
              <Square size={15} /> 停止 Agent
            </Button>
          ) : (
            <Button onClick={() => setAgentState("RUNNING")}>
              <Play size={15} /> 啟動 Agent
            </Button>
          )}
        </div>
        {agentError && (
          <p className="mt-3 rounded-lg border border-danger/30 bg-danger/10 p-3 text-sm text-danger">{agentError}</p>
        )}
      </div>

      <div className="grid grid-cols-2 gap-4 sm:grid-cols-3 lg:grid-cols-6">
        <StatCard label="發現懸賞" value={bounties.length} icon={<Target size={16} />} />
        <StatCard label="已解決" value={solved} icon={<CheckCircle2 size={16} />} />
        <StatCard label="已提交 PR" value={prSubmitted} icon={<GitPullRequest size={16} />} />
        <StatCard label="已合併" value={0} icon={<GitMerge size={16} />} />
        <StatCard label="預估收入" value={`$${estimatedEarnings}`} tone="action" icon={<DollarSign size={16} />} />
        <StatCard label="AI／API 成本" value={`$${aiCost.toFixed(2)}`} icon={<Cpu size={16} />} />
      </div>

      <div className="rounded-xl border border-border bg-panel p-5">
        <p className="text-sm text-muted">目前任務</p>
        {activeRun ? (
          <div className="mt-3 space-y-4">
            <div className="flex items-center justify-between">
              <p className="font-medium text-ink">{activeRun.issueTitle}</p>
              <span className="text-sm font-semibold text-action">${activeRun.reward}</span>
            </div>
            <PipelineStepper stages={deriveTaskStages(activeRun.stages.map((s) => s.status))} />
          </div>
        ) : (
          <p className="mt-3 text-sm text-muted">
            {isRunning ? "目前沒有任務，正在等待下一個符合條件的懸賞。" : "Agent 已停止，啟動後即可開始處理懸賞。"}
          </p>
        )}
      </div>
    </div>
  );
}
