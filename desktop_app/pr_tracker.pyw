"""Standalone desktop widget: lists bounties this bot has submitted a PR
for, shows each PR's live GitHub status and conversation, and lets you post
a reply - independent of the Bounty Bot web backend, Docker, or any AI
provider being run. Reads run history directly from
webapp/backend/data/runs.json and the GitHub token from .env; only talks to
GitHub when you open it or click "重新整理" - it never polls in the
background.
"""

from __future__ import annotations

import json
import re
import threading
import tkinter as tk
import webbrowser
from pathlib import Path
from tkinter import messagebox, scrolledtext, ttk

import requests
from dotenv import dotenv_values

PROJECT_ROOT = Path(__file__).resolve().parents[1]
ENV_PATH = PROJECT_ROOT / ".env"
RUNS_PATH = PROJECT_ROOT / "webapp" / "backend" / "data" / "runs.json"

# Matches the app's own dark theme (webapp/frontend/src/index.css).
BG = "#070b12"
PANEL = "#0d1420"
BORDER = "#1c2534"
INK = "#e6ebf5"
MUTED = "#8b95a8"
ACTION = "#19e68c"
PRIMARY = "#168bff"

PR_URL_RE = re.compile(r"github\.com/([^/]+)/([^/]+)/pull/(\d+)")


def load_token() -> str | None:
    return dotenv_values(ENV_PATH).get("GITHUB_TOKEN") or None


def load_submitted_prs() -> list[dict]:
    if not RUNS_PATH.exists():
        return []
    try:
        raw = json.loads(RUNS_PATH.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return []
    # Retries against the same bounty reuse one PR - keep only the most
    # recent run per PR URL so it isn't listed more than once.
    by_pr_url: dict[str, dict] = {}
    for run in raw.values():
        url = run.get("pr_url")
        if not url or not PR_URL_RE.search(url):
            continue
        existing = by_pr_url.get(url)
        if existing is None or run.get("started_at", "") > existing.get("started_at", ""):
            by_pr_url[url] = run
    items = list(by_pr_url.values())
    items.sort(key=lambda r: r.get("started_at", ""), reverse=True)
    return items


class PrTrackerApp:
    def __init__(self, root: tk.Tk):
        self.root = root
        self.token = load_token()
        self.prs: list[dict] = []
        self.live_status: dict[str, dict] = {}
        self.selected_index: int | None = None

        self._build_ui()
        self.refresh_all()

        if not self.token:
            messagebox.showwarning(
                "找不到 GitHub Token",
                "在 .env 找不到 GITHUB_TOKEN，可以看到已提交的 PR 清單，\n"
                "但無法查詢即時狀態、留言或回覆。",
            )

    # -------- UI construction --------

    def _build_ui(self) -> None:
        self.root.title("Bounty Bot - PR 追蹤")
        self.root.configure(bg=BG)
        self.root.geometry("920x580")
        self.root.minsize(760, 480)

        style = ttk.Style(self.root)
        try:
            style.theme_use("clam")
        except tk.TclError:
            pass
        style.configure("Treeview", background=PANEL, fieldbackground=PANEL, foreground=INK,
                         borderwidth=0, rowheight=28)
        style.configure("Treeview.Heading", background=BG, foreground=MUTED, borderwidth=0)
        style.map("Treeview", background=[("selected", PRIMARY)])

        toolbar = tk.Frame(self.root, bg=BG)
        toolbar.pack(fill="x", padx=12, pady=(12, 6))
        tk.Label(toolbar, text="已提交的 Pull Request", bg=BG, fg=INK,
                 font=("Segoe UI", 13, "bold")).pack(side="left")
        self.status_label = tk.Label(toolbar, text="", bg=BG, fg=MUTED, font=("Segoe UI", 9))
        self.status_label.pack(side="left", padx=12)
        tk.Button(toolbar, text="重新整理", command=self.refresh_all, bg=PANEL, fg=INK,
                  activebackground=BORDER, activeforeground=INK, relief="flat",
                  padx=10, pady=4).pack(side="right")

        body = tk.Frame(self.root, bg=BG)
        body.pack(fill="both", expand=True, padx=12, pady=(0, 12))

        columns = ("repo", "title", "reward", "status")
        self.tree = ttk.Treeview(body, columns=columns, show="headings", selectmode="browse")
        for col, label, width in (
            ("repo", "倉庫", 190), ("title", "標題", 250), ("reward", "獎勵", 70), ("status", "狀態", 90),
        ):
            self.tree.heading(col, text=label)
            self.tree.column(col, width=width, anchor="w")
        self.tree.pack(side="left", fill="both", expand=True)
        self.tree.bind("<<TreeviewSelect>>", self._on_select)

        detail = tk.Frame(body, bg=PANEL, width=380)
        detail.pack(side="left", fill="y", padx=(10, 0))
        detail.pack_propagate(False)

        self.detail_title = tk.Label(detail, text="選擇一個 PR 查看詳情", bg=PANEL, fg=INK,
                                      font=("Segoe UI", 11, "bold"), wraplength=356, justify="left")
        self.detail_title.pack(anchor="w", padx=12, pady=(12, 4))
        self.detail_link = tk.Label(detail, text="", bg=PANEL, fg=PRIMARY, cursor="hand2",
                                     wraplength=356, justify="left")
        self.detail_link.pack(anchor="w", padx=12)
        self.detail_link.bind("<Button-1>", self._open_selected_pr)

        tk.Label(detail, text="留言", bg=PANEL, fg=MUTED, font=("Segoe UI", 9)).pack(
            anchor="w", padx=12, pady=(12, 2))
        self.comments_box = scrolledtext.ScrolledText(
            detail, height=14, bg=BG, fg=INK, insertbackground=INK,
            relief="flat", wrap="word", state="disabled",
        )
        self.comments_box.pack(fill="both", expand=True, padx=12)

        tk.Label(detail, text="回覆", bg=PANEL, fg=MUTED, font=("Segoe UI", 9)).pack(
            anchor="w", padx=12, pady=(10, 2))
        self.reply_entry = tk.Text(detail, height=3, bg=BG, fg=INK, insertbackground=INK,
                                    relief="flat", wrap="word")
        self.reply_entry.pack(fill="x", padx=12)
        tk.Button(detail, text="送出回覆", command=self._send_reply, bg=ACTION, fg="#04160e",
                  relief="flat", padx=10, pady=6).pack(anchor="e", padx=12, pady=(6, 12))

    # -------- data / list --------

    def _status_label_for(self, pr: dict) -> str:
        live = self.live_status.get(pr["pr_url"])
        if live is not None:
            if live.get("merged"):
                return "已合併"
            return "已關閉" if live.get("state") == "closed" else "開啟中"
        if pr.get("merged"):
            return "已合併"
        return "開啟中" if not pr.get("duplicate_pr") else "重複"

    def _populate_list(self) -> None:
        for row in self.tree.get_children():
            self.tree.delete(row)
        for pr in self.prs:
            self.tree.insert(
                "", "end",
                values=(pr["repository"], pr["issue_title"][:40], f"${pr['reward']:.0f}", self._status_label_for(pr)),
            )

    def _on_select(self, _event=None) -> None:
        selection = self.tree.selection()
        if not selection:
            return
        self.selected_index = self.tree.index(selection[0])
        pr = self.prs[self.selected_index]
        self.detail_title.configure(text=pr["issue_title"])
        self.detail_link.configure(text=pr["pr_url"])
        self._load_comments(pr)

    def _open_selected_pr(self, _event=None) -> None:
        if self.selected_index is None:
            return
        webbrowser.open(self.prs[self.selected_index]["pr_url"])

    # -------- GitHub API --------

    def _headers(self) -> dict:
        return {"Authorization": f"token {self.token}", "Accept": "application/vnd.github+json"}

    def refresh_all(self) -> None:
        self.prs = load_submitted_prs()
        self._populate_list()
        self.selected_index = None
        self.detail_title.configure(text="選擇一個 PR 查看詳情")
        self.detail_link.configure(text="")
        self._set_comments_text("")
        if self.token and self.prs:
            self.status_label.configure(text="正在查詢最新狀態...")
            threading.Thread(target=self._refresh_live_status_bg, daemon=True).start()
        else:
            self.status_label.configure(text=f"共 {len(self.prs)} 筆")

    def _refresh_live_status_bg(self) -> None:
        for pr in self.prs:
            match = PR_URL_RE.search(pr["pr_url"])
            if not match:
                continue
            owner, repo, number = match.groups()
            try:
                resp = requests.get(
                    f"https://api.github.com/repos/{owner}/{repo}/pulls/{number}",
                    headers=self._headers(), timeout=15,
                )
                if resp.status_code == 200:
                    data = resp.json()
                    self.live_status[pr["pr_url"]] = {"state": data.get("state"), "merged": data.get("merged")}
            except requests.RequestException:
                pass
        self.root.after(0, self._populate_list)
        self.root.after(0, lambda: self.status_label.configure(text=f"共 {len(self.prs)} 筆 · 已更新即時狀態"))

    def _load_comments(self, pr: dict) -> None:
        self._set_comments_text("載入中...")
        if not self.token:
            self._set_comments_text("（沒有 GitHub Token，無法載入留言）")
            return
        threading.Thread(target=self._fetch_comments_bg, args=(pr,), daemon=True).start()

    def _fetch_comments_bg(self, pr: dict) -> None:
        match = PR_URL_RE.search(pr["pr_url"])
        if not match:
            self.root.after(0, self._set_comments_text, "（無法解析 PR 網址）")
            return
        owner, repo, number = match.groups()
        try:
            resp = requests.get(
                f"https://api.github.com/repos/{owner}/{repo}/issues/{number}/comments",
                headers=self._headers(), timeout=15,
            )
            resp.raise_for_status()
            comments = resp.json()
        except requests.RequestException as exc:
            self.root.after(0, self._set_comments_text, f"（載入留言失敗：{exc}）")
            return
        if not comments:
            text = "（目前沒有留言）"
        else:
            text = "\n---\n".join(
                f"@{c['user']['login']}  {c.get('created_at', '')}\n{c['body']}" for c in comments
            )
        self.root.after(0, self._set_comments_text, text)

    def _set_comments_text(self, text: str) -> None:
        self.comments_box.configure(state="normal")
        self.comments_box.delete("1.0", "end")
        self.comments_box.insert("end", text)
        self.comments_box.configure(state="disabled")

    def _send_reply(self) -> None:
        if self.selected_index is None:
            messagebox.showinfo("提示", "請先選擇一個 PR")
            return
        if not self.token:
            messagebox.showerror("錯誤", ".env 沒有設定 GITHUB_TOKEN，無法回覆")
            return
        body = self.reply_entry.get("1.0", "end").strip()
        if not body:
            return
        pr = self.prs[self.selected_index]
        match = PR_URL_RE.search(pr["pr_url"])
        if not match:
            return
        owner, repo, number = match.groups()
        try:
            resp = requests.post(
                f"https://api.github.com/repos/{owner}/{repo}/issues/{number}/comments",
                headers=self._headers(), json={"body": body}, timeout=15,
            )
            resp.raise_for_status()
        except requests.RequestException as exc:
            messagebox.showerror("回覆失敗", str(exc))
            return
        self.reply_entry.delete("1.0", "end")
        self._load_comments(pr)


def main() -> None:
    root = tk.Tk()
    PrTrackerApp(root)
    root.mainloop()


if __name__ == "__main__":
    main()
