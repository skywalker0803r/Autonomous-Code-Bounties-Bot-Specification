import { useState } from "react";
import { useNavigate } from "react-router-dom";
import { Check, Loader2 } from "lucide-react";
import { Button } from "../components/Button";
import { GithubMark } from "../components/GithubMark";
import { useAppState } from "../state/AppState";
import type { AiProvider } from "../types";

const PROVIDERS: { id: AiProvider; label: string; available: boolean }[] = [
  { id: "gemini", label: "Gemini", available: true },
  { id: "openai", label: "OpenAI", available: true },
  { id: "claude_code", label: "Claude Code（本機 CLI）", available: true },
  { id: "local", label: "本地模型（Ollama）", available: true },
  { id: "claude", label: "Claude", available: false },
];

export function Onboarding() {
  const [step, setStep] = useState(1);
  const [githubToken, setGithubToken] = useState("");
  const [githubUsername, setGithubUsername] = useState<string | null>(null);
  const [connecting, setConnecting] = useState(false);
  const [githubError, setGithubError] = useState<string | null>(null);
  const [provider, setProvider] = useState<AiProvider>("gemini");
  const [apiKey, setApiKey] = useState("");
  const [starting, setStarting] = useState(false);
  const [startError, setStartError] = useState<string | null>(null);
  const { completeOnboarding, setAgentState, updateSettings, connectGithub } = useAppState();
  const navigate = useNavigate();

  const handleConnectGithub = async () => {
    setConnecting(true);
    setGithubError(null);
    try {
      const result = await connectGithub(githubToken);
      if (result.connected) {
        setGithubUsername(result.username ?? null);
      } else {
        setGithubError(result.error ?? "連接失敗，請確認 Token 是否正確。");
      }
    } catch (e) {
      setGithubError(e instanceof Error ? e.message : "無法連線到後端伺服器。");
    } finally {
      setConnecting(false);
    }
  };

  const handleStart = async () => {
    setStarting(true);
    setStartError(null);
    try {
      await updateSettings({ aiProvider: provider, apiKey: apiKey || undefined });
      setAgentState("RUNNING");
      completeOnboarding();
      navigate("/dashboard");
    } catch (e) {
      setStartError(e instanceof Error ? e.message : "無法儲存設定，請稍後再試。");
    } finally {
      setStarting(false);
    }
  };

  return (
    <div className="flex min-h-screen items-center justify-center bg-bg px-4">
      <div className="w-full max-w-md rounded-2xl border border-border bg-panel p-8">
        <div className="mb-6 flex items-center gap-2">
          <img src="/logo.webp" alt="Bounty Bot" className="h-9 w-9 rounded-lg" />
          <div>
            <p className="text-sm font-semibold text-ink">Bounty Bot</p>
            <p className="text-xs text-muted">一分鐘內完成設定</p>
          </div>
        </div>

        <div className="mb-6 flex items-center gap-2">
          {[1, 2, 3].map((n) => (
            <div key={n} className={`h-1.5 flex-1 rounded-full ${n <= step ? "bg-primary" : "bg-border"}`} />
          ))}
        </div>

        {step === 1 && (
          <div>
            <h2 className="text-lg font-semibold text-ink">連接 GitHub</h2>
            <p className="mt-1 text-sm text-muted">
              貼上一個具備 <code className="text-ink">repo</code> 權限的 GitHub Personal Access Token，Bounty
              Bot 會用它讀取 Issue 並代表你開啟 Pull Request。
            </p>
            <input
              type="password"
              value={githubToken}
              onChange={(e) => setGithubToken(e.target.value)}
              placeholder="ghp_..."
              disabled={!!githubUsername}
              className="mt-4 w-full rounded-lg border border-border bg-bg px-3 py-2.5 text-sm text-ink placeholder:text-muted focus:border-primary focus:outline-none disabled:opacity-60"
            />
            <button
              onClick={handleConnectGithub}
              disabled={!githubToken || connecting || !!githubUsername}
              className={`mt-3 flex w-full items-center justify-center gap-2 rounded-lg border px-4 py-2.5 text-sm font-medium transition disabled:cursor-not-allowed ${
                githubUsername
                  ? "border-action/30 bg-action/10 text-action"
                  : "border-border bg-white/5 text-ink hover:bg-white/10 disabled:opacity-60"
              }`}
            >
              {connecting ? (
                <Loader2 size={16} className="animate-spin" />
              ) : githubUsername ? (
                <Check size={16} />
              ) : (
                <GithubMark size={16} />
              )}
              {githubUsername ? `已連接 @${githubUsername}` : connecting ? "連接中..." : "連接 GitHub"}
            </button>
            {githubError && <p className="mt-2 text-xs text-danger">{githubError}</p>}
            <Button className="mt-6 w-full" disabled={!githubUsername} onClick={() => setStep(2)}>
              繼續
            </Button>
          </div>
        )}

        {step === 2 && (
          <div>
            <h2 className="text-lg font-semibold text-ink">選擇 AI 供應商</h2>
            <p className="mt-1 text-sm text-muted">這個模型會負責產生並檢查 Bounty Bot 提交的修補程式。</p>
            <div className="mt-5 space-y-2">
              {PROVIDERS.map((p) => (
                <button
                  key={p.id}
                  disabled={!p.available}
                  onClick={() => setProvider(p.id)}
                  className={`flex w-full items-center justify-between rounded-lg border px-4 py-3 text-sm transition disabled:cursor-not-allowed disabled:opacity-40 ${
                    provider === p.id
                      ? "border-primary/50 bg-primary/10 text-ink"
                      : "border-border text-muted hover:bg-white/5"
                  }`}
                >
                  <span>{p.label}</span>
                  {!p.available && <span className="text-xs text-muted">即將推出</span>}
                  {p.available && provider === p.id && <Check size={16} className="text-primary" />}
                </button>
              ))}
            </div>
            <Button className="mt-6 w-full" onClick={() => setStep(3)}>
              繼續
            </Button>
          </div>
        )}

        {step === 3 && provider === "claude_code" && (
          <div>
            <h2 className="text-lg font-semibold text-ink">免 API 金鑰</h2>
            <p className="mt-1 text-sm text-muted">
              Claude Code 會使用這台機器上已登入的 CLI（終端機執行 <code className="text-ink">claude /login</code>），
              不需要另外設定 API 金鑰。
            </p>
            {startError && <p className="mt-2 text-xs text-danger">{startError}</p>}
            <Button className="mt-6 w-full" disabled={starting} onClick={handleStart}>
              {starting ? <Loader2 size={15} className="animate-spin" /> : null}
              啟動 Agent →
            </Button>
          </div>
        )}

        {step === 3 && provider !== "claude_code" && (
          <div>
            <h2 className="text-lg font-semibold text-ink">{provider === "local" ? "本地模型" : "API 金鑰"}</h2>
            <p className="mt-1 text-sm text-muted">
              {provider === "local"
                ? "請先在本機啟動 Ollama，並安裝 qwen2.5-coder:7b。預設端點為 http://127.0.0.1:11434。"
                : `你的 ${PROVIDERS.find((p) => p.id === provider)?.label} API 金鑰只會存在本機設定檔中。`}
            </p>
            {provider !== "local" && (
              <input
                type="password"
                value={apiKey}
                onChange={(e) => setApiKey(e.target.value)}
                placeholder="貼上你的 API 金鑰"
                className="mt-5 w-full rounded-lg border border-border bg-bg px-3 py-2.5 text-sm text-ink placeholder:text-muted focus:border-primary focus:outline-none"
              />
            )}
            {startError && <p className="mt-2 text-xs text-danger">{startError}</p>}
            <Button className="mt-6 w-full" disabled={(provider !== "local" && !apiKey) || starting} onClick={handleStart}>
              {starting ? <Loader2 size={15} className="animate-spin" /> : null}
              啟動 Agent →
            </Button>
          </div>
        )}
      </div>
    </div>
  );
}
