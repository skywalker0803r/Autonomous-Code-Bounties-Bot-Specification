import { RunCard } from "../components/RunCard";
import { useAppState } from "../state/AppState";

export function Runs() {
  const { runs, retryRun, deleteRun } = useAppState();

  const handleRetry = (runId: string) => {
    retryRun(runId).catch(() => {
      // The run card already reflects failure state via polling; a toast
      // isn't needed for a background retry that itself just failed to start.
    });
  };

  const handleDelete = (runId: string) => {
    if (!window.confirm("確定要刪除這筆執行紀錄嗎？此操作無法復原。")) return;
    deleteRun(runId).catch(() => {
      // Deletion failing (404 - already gone, or a network blip) doesn't
      // need its own toast; the card simply stays in the list.
    });
  };

  return (
    <div className="space-y-6">
      <div>
        <h1 className="text-xl font-semibold text-ink">執行紀錄</h1>
        <p className="text-sm text-muted">追蹤每個懸賞從 Issue 到 Pull Request 的過程。</p>
      </div>

      {runs.length === 0 ? (
        <div className="rounded-xl border border-border bg-panel p-10 text-center text-sm text-muted">
          還沒有任何執行紀錄，先到懸賞頁面點擊「解決」吧。
        </div>
      ) : (
        <div className="space-y-4">
          {runs.map((run) => (
            <RunCard key={run.id} run={run} onRetry={handleRetry} onDelete={handleDelete} />
          ))}
        </div>
      )}
    </div>
  );
}
