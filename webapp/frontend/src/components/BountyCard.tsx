import { ArrowRight } from "lucide-react";
import { Badge } from "./Badge";
import { Button } from "./Button";
import type { Bounty } from "../types";

const DIFFICULTY_TONE = {
  簡單: "success",
  中等: "info",
  困難: "danger",
} as const;

const SUSPICION_LABEL = {
  high: "⚠️ 高度可疑帳號",
  medium: "可疑帳號",
} as const;

export function BountyCard({ bounty, onSolve }: { bounty: Bounty; onSolve: (bounty: Bounty) => void }) {
  const isOpire = bounty.source === "opire" || bounty.source === "opirebot";
  const isSuspicious = bounty.suspicionLevel === "medium" || bounty.suspicionLevel === "high";

  return (
    <div className="flex flex-col justify-between rounded-xl border border-border bg-panel p-5">
      <div>
        <div className="flex items-start justify-between gap-3">
          <p className="font-medium text-ink">{bounty.title}</p>
          <span className="shrink-0 text-lg font-semibold text-action">${bounty.reward}</span>
        </div>
        <p className="mt-1 text-sm text-muted">
          {bounty.repository}
          {bounty.posterLogin && (
            <>
              {" · "}
              {bounty.posterUrl ? (
                <a
                  href={bounty.posterUrl}
                  target="_blank"
                  rel="noreferrer"
                  className="hover:text-ink hover:underline"
                >
                  @{bounty.posterLogin}
                </a>
              ) : (
                `@${bounty.posterLogin}`
              )}
            </>
          )}
        </p>

        <div className="mt-3 flex flex-wrap gap-2">
          <Badge tone={isOpire ? "success" : "neutral"}>
            {isOpire ? "Opire" : "GitHub"}
          </Badge>
          <Badge tone="neutral">{bounty.language}</Badge>
          <Badge tone="neutral">{bounty.type}</Badge>
          <Badge tone={DIFFICULTY_TONE[bounty.difficulty]}>{bounty.difficulty}</Badge>
          {isSuspicious && (
            <span title={bounty.suspicionReasons.join("；")}>
              <Badge tone={bounty.suspicionLevel === "high" ? "danger" : "info"}>
                {SUSPICION_LABEL[bounty.suspicionLevel as "high" | "medium"]}
              </Badge>
            </span>
          )}
          {bounty.submittedPrUrl && (
            <a href={bounty.submittedPrUrl} target="_blank" rel="noreferrer">
              <Badge tone="success">✓ PR 已提交</Badge>
            </a>
          )}
        </div>
      </div>

      <div className="mt-4 flex items-center justify-between border-t border-border pt-4">
        <span className="text-xs text-muted">預估 AI 成本 ${bounty.estimatedAiCost.toFixed(2)}</span>
        {bounty.submittedPrUrl ? (
          <Button variant="ghost" disabled title="已提交過 PR，避免重複消耗 AI 成本，如需重新處理請至執行紀錄重試">
            已提交過
          </Button>
        ) : (
          <Button onClick={() => onSolve(bounty)}>
            解決 <ArrowRight size={15} />
          </Button>
        )}
      </div>
    </div>
  );
}
