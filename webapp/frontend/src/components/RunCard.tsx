import { useState } from "react";
import { ChevronDown, ChevronUp, ExternalLink, RotateCcw } from "lucide-react";
import { Badge } from "./Badge";
import { Button } from "./Button";
import { StageIcon } from "./StageIcon";
import type { Run } from "../types";

const STATUS_BADGE = {
  running: { tone: "info" as const, label: "執行中" },
  success: { tone: "success" as const, label: "成功" },
  failed: { tone: "danger" as const, label: "失敗" },
  // Distinct from "failed": the AI judged the issue suspicious/illegitimate
  // and declined to generate a patch - a safety mechanism working, not a bug.
  declined: { tone: "neutral" as const, label: "已略過" },
};

export function RunCard({ run, onRetry }: { run: Run; onRetry: (runId: string) => void }) {
  const [showLogs, setShowLogs] = useState(false);
  const status = STATUS_BADGE[run.status];

  return (
    <div className="rounded-xl border border-border bg-panel p-5">
      <div className="flex items-start justify-between gap-3">
        <div>
          <p className="font-medium text-ink">{run.issueTitle}</p>
          <p className="mt-1 text-sm text-muted">
            {run.repository} · ${run.reward}
          </p>
        </div>
        <Badge tone={status.tone}>{status.label}</Badge>
      </div>

      <div className="mt-5 flex flex-wrap items-start gap-y-4 overflow-x-auto">
        {run.stages.map((stage, i) => (
          <div key={stage.key} className="flex items-center">
            <div className="flex flex-col items-center gap-1.5 px-1">
              <StageIcon status={stage.status} />
              <span
                className={`text-[11px] whitespace-nowrap ${
                  stage.status === "waiting" || stage.status === "skipped" ? "text-muted" : "text-ink"
                }`}
              >
                {stage.label}
              </span>
            </div>
            {i < run.stages.length - 1 && (
              <div className={`mx-1 h-px w-6 sm:w-10 ${stage.status === "done" ? "bg-action" : "bg-border"}`} />
            )}
          </div>
        ))}
      </div>

      {run.status === "failed" && run.errorMessage && (
        <div className="mt-4 rounded-lg border border-danger/30 bg-danger/10 p-3 text-sm text-danger">
          {run.errorMessage}
        </div>
      )}

      {run.status === "declined" && run.errorMessage && (
        <div className="mt-4 rounded-lg border border-border bg-white/5 p-3 text-sm text-muted">
          <p className="mb-1 font-medium text-ink">AI 判斷此 issue 可疑，已拒絕生成修補程式（安全機制正常運作，非程式錯誤）</p>
          {run.errorMessage}
        </div>
      )}

      <div className="mt-4 flex items-center justify-between border-t border-border pt-4">
        <button
          onClick={() => setShowLogs((v) => !v)}
          className="flex items-center gap-1 text-xs text-muted hover:text-ink"
        >
          {showLogs ? <ChevronUp size={14} /> : <ChevronDown size={14} />}
          查看紀錄
        </button>

        <div className="flex gap-2">
          {(run.status === "failed" || run.status === "declined") && (
            <Button variant="ghost" onClick={() => onRetry(run.id)}>
              <RotateCcw size={14} /> 重試
            </Button>
          )}
          {run.status === "success" && run.prUrl && (
            <a href={run.prUrl} target="_blank" rel="noreferrer">
              <Button variant="secondary">
                查看 Pull Request <ExternalLink size={14} />
              </Button>
            </a>
          )}
        </div>
      </div>

      {showLogs && (
        <pre className="mt-3 max-h-48 overflow-y-auto rounded-lg bg-bg p-3 text-xs text-muted">
          {run.logs.join("\n")}
        </pre>
      )}
    </div>
  );
}
