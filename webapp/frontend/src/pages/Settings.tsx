import { useEffect, useRef, useState, type ReactNode } from "react";
import { Check, ChevronDown, ChevronUp, Loader2 } from "lucide-react";
import { Button } from "../components/Button";
import { Toggle } from "../components/Toggle";
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

const LANGUAGES = ["Python", "TypeScript", "JavaScript", "Go", "Rust"];

function Section({ title, description, children }: { title: string; description?: string; children: ReactNode }) {
  return (
    <div className="rounded-xl border border-border bg-panel p-5">
      <h2 className="font-medium text-ink">{title}</h2>
      {description && <p className="mt-1 text-sm text-muted">{description}</p>}
      <div className="mt-4 space-y-4">{children}</div>
    </div>
  );
}

function Field({ label, children }: { label: string; children: ReactNode }) {
  return (
    <label className="flex items-center justify-between gap-4">
      <span className="text-sm text-ink">{label}</span>
      {children}
    </label>
  );
}

const inputClass =
  "w-40 rounded-lg border border-border bg-bg px-3 py-1.5 text-sm text-ink text-right focus:border-primary focus:outline-none";

export function Settings() {
  const { settings, settingsLoaded, updateSettings, connectGithub } = useAppState();
  const [form, setForm] = useState(settings);
  const initialized = useRef(false);
  const [newApiKey, setNewApiKey] = useState("");
  const [advancedOpen, setAdvancedOpen] = useState(false);
  const [saving, setSaving] = useState(false);
  const [saved, setSaved] = useState(false);
  const [saveError, setSaveError] = useState<string | null>(null);

  const [githubToken, setGithubToken] = useState("");
  const [githubConnecting, setGithubConnecting] = useState(false);
  const [githubError, setGithubError] = useState<string | null>(null);

  useEffect(() => {
    if (settingsLoaded && !initialized.current) {
      setForm(settings);
      initialized.current = true;
    }
  }, [settingsLoaded, settings]);

  const toggleLanguage = (lang: string) => {
    setForm((f) => ({
      ...f,
      languages: f.languages.includes(lang) ? f.languages.filter((l) => l !== lang) : [...f.languages, lang],
    }));
  };

  const handleSave = async () => {
    setSaving(true);
    setSaveError(null);
    try {
      await updateSettings({ ...form, apiKey: newApiKey || undefined });
      setNewApiKey("");
      setSaved(true);
      setTimeout(() => setSaved(false), 2000);
    } catch (e) {
      setSaveError(e instanceof Error ? e.message : "儲存失敗，請稍後再試。");
    } finally {
      setSaving(false);
    }
  };

  const handleConnectGithub = async () => {
    setGithubConnecting(true);
    setGithubError(null);
    try {
      const result = await connectGithub(githubToken);
      if (result.connected) {
        setGithubToken("");
      } else {
        setGithubError(result.error ?? "連接失敗，請確認 Token 是否正確。");
      }
    } catch (e) {
      setGithubError(e instanceof Error ? e.message : "無法連線到後端伺服器。");
    } finally {
      setGithubConnecting(false);
    }
  };

  return (
    <div className="space-y-6">
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-xl font-semibold text-ink">設定</h1>
          <p className="text-sm text-muted">只保留日常會用到的設定，其餘都收在「進階設定」。</p>
        </div>
        <Button onClick={handleSave} disabled={saving || !settingsLoaded}>
          {saving ? <Loader2 size={15} className="animate-spin" /> : saved ? <Check size={15} /> : null}
          {saving ? "儲存中" : saved ? "已儲存" : "儲存"}
        </Button>
      </div>
      {saveError && <div className="rounded-xl border border-danger/30 bg-danger/10 p-4 text-sm text-danger">{saveError}</div>}

      <Section title="GitHub 連線" description="Bounty Bot 會用這個帳號 Fork 倉庫並開啟 Pull Request。">
        {settings.githubConnected && (
          <div className="flex items-center gap-2 text-sm text-action">
            <Check size={16} /> 已連接 @{settings.githubUsername}
          </div>
        )}
        <div className="flex flex-col gap-2 sm:flex-row">
          <input
            type="password"
            value={githubToken}
            onChange={(e) => setGithubToken(e.target.value)}
            placeholder={settings.githubConnected ? "輸入新的 Token 以更換帳號" : "ghp_..."}
            className="flex-1 rounded-lg border border-border bg-bg px-3 py-2 text-sm text-ink placeholder:text-muted focus:border-primary focus:outline-none"
          />
          <button
            onClick={handleConnectGithub}
            disabled={!githubToken || githubConnecting}
            className="flex items-center justify-center gap-2 rounded-lg border border-border bg-white/5 px-4 py-2 text-sm font-medium text-ink transition hover:bg-white/10 disabled:cursor-not-allowed disabled:opacity-60"
          >
            {githubConnecting ? <Loader2 size={16} className="animate-spin" /> : <GithubMark size={16} />}
            {settings.githubConnected ? "更換帳號" : "連接 GitHub"}
          </button>
        </div>
        {githubError && <p className="text-xs text-danger">{githubError}</p>}
      </Section>

      <Section title="AI 供應商">
        <div className="grid grid-cols-1 gap-2 sm:grid-cols-2">
          {PROVIDERS.map((p) => (
            <button
              key={p.id}
              disabled={!p.available}
              onClick={() => setForm((f) => ({ ...f, aiProvider: p.id }))}
              className={`flex items-center justify-between rounded-lg border px-4 py-2.5 text-sm transition disabled:cursor-not-allowed disabled:opacity-40 ${
                form.aiProvider === p.id ? "border-primary/50 bg-primary/10 text-ink" : "border-border text-muted hover:bg-white/5"
              }`}
            >
              {p.label}
              {!p.available && <span className="text-xs">即將推出</span>}
              {p.available && form.aiProvider === p.id && <Check size={15} className="text-primary" />}
            </button>
          ))}
        </div>
        {form.aiProvider === "claude_code" ? (
          <p className="text-xs text-muted">
            會使用這台機器上已登入的 Claude Code CLI（<code>claude /login</code>），不需要在這裡設定 API 金鑰。
          </p>
        ) : (
          <Field label={settings.apiKeySet ? "API 金鑰（已設定，輸入新值以更新）" : "API 金鑰"}>
            <input
              type="password"
              value={newApiKey}
              onChange={(e) => setNewApiKey(e.target.value)}
              placeholder={settings.apiKeySet ? "••••••••" : "sk-..."}
              className={inputClass}
            />
          </Field>
        )}
      </Section>

      <Section title="倉庫篩選條件">
        <div>
          <p className="mb-2 text-sm text-ink">程式語言</p>
          <div className="flex flex-wrap gap-2">
            {LANGUAGES.map((lang) => (
              <button
                key={lang}
                onClick={() => toggleLanguage(lang)}
                className={`rounded-full border px-3 py-1 text-xs transition ${
                  form.languages.includes(lang)
                    ? "border-primary/40 bg-primary/15 text-primary"
                    : "border-border text-muted hover:text-ink"
                }`}
              >
                {lang}
              </button>
            ))}
          </div>
        </div>
        <Field label="最低懸賞金額（美元）">
          <input
            type="number"
            value={form.minBounty}
            onChange={(e) => setForm((f) => ({ ...f, minBounty: Number(e.target.value) }))}
            className={inputClass}
          />
        </Field>
        <Field label="每個 Issue 的最高 AI 成本（美元）">
          <input
            type="number"
            step="0.5"
            value={form.maxAiCost}
            onChange={(e) => setForm((f) => ({ ...f, maxAiCost: Number(e.target.value) }))}
            className={inputClass}
          />
        </Field>
      </Section>

      <Section title="自動化">
        <Field label="測試通過後自動提交 PR">
          <Toggle checked={form.autoSubmitPr} onChange={(v) => setForm((f) => ({ ...f, autoSubmitPr: v }))} />
        </Field>
      </Section>

      <div className="rounded-xl border border-border bg-panel">
        <button
          onClick={() => setAdvancedOpen((v) => !v)}
          className="flex w-full items-center justify-between px-5 py-4 text-sm text-muted hover:text-ink"
        >
          進階設定
          {advancedOpen ? <ChevronUp size={16} /> : <ChevronDown size={16} />}
        </button>
        {advancedOpen && (
          <div className="space-y-4 border-t border-border p-5">
            <Field label="輪詢間隔（秒）">
              <input
                type="number"
                value={form.advanced.pollIntervalSeconds}
                onChange={(e) =>
                  setForm((f) => ({ ...f, advanced: { ...f.advanced, pollIntervalSeconds: Number(e.target.value) } }))
                }
                className={inputClass}
              />
            </Field>
            <Field label="Docker 記憶體限制">
              <input
                value={form.advanced.dockerMemoryLimit}
                onChange={(e) => setForm((f) => ({ ...f, advanced: { ...f.advanced, dockerMemoryLimit: e.target.value } }))}
                className={inputClass}
              />
            </Field>
            <Field label="Docker CPU 限制">
              <input
                type="number"
                value={form.advanced.dockerCpuLimit}
                onChange={(e) =>
                  setForm((f) => ({ ...f, advanced: { ...f.advanced, dockerCpuLimit: Number(e.target.value) } }))
                }
                className={inputClass}
              />
            </Field>
            <Field label="最大重試次數">
              <input
                type="number"
                value={form.advanced.maxRetries}
                onChange={(e) => setForm((f) => ({ ...f, advanced: { ...f.advanced, maxRetries: Number(e.target.value) } }))}
                className={inputClass}
              />
            </Field>
            <Field label="最大平行測試數">
              <input
                type="number"
                value={form.advanced.maxParallelTests}
                onChange={(e) =>
                  setForm((f) => ({ ...f, advanced: { ...f.advanced, maxParallelTests: Number(e.target.value) } }))
                }
                className={inputClass}
              />
            </Field>
          </div>
        )}
      </div>
    </div>
  );
}
