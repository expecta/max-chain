"""Max Chain desktop app (learning project - NOT real money). Uses the logic in max.py."""
import threading, time, tkinter as tk
from tkinter import ttk, messagebox, simpledialog
import max as M

BG, PANEL, FG, ACC, MUTED = "#12121a", "#1e1e2e", "#e8e8f0", "#ffb000", "#8888a0"

class App(tk.Tk):
    def __init__(self):
        super().__init__()
        self.title("MAX Chain Wallet"); self.geometry("900x600"); self.configure(bg=BG)
        st = ttk.Style(self); st.theme_use("clam")
        st.configure(".", background=BG, foreground=FG, fieldbackground=PANEL, font=("Segoe UI", 10))
        st.configure("TNotebook", background=BG, borderwidth=0)
        st.configure("TNotebook.Tab", background=PANEL, foreground=FG, padding=(14, 6))
        st.map("TNotebook.Tab", background=[("selected", ACC)], foreground=[("selected", BG)])
        st.configure("TButton", background=ACC, foreground=BG, padding=6, font=("Segoe UI", 10, "bold"))
        st.map("TButton", background=[("active", "#ffc840")])
        st.configure("Treeview", background=PANEL, foreground=FG, fieldbackground=PANEL, rowheight=26)
        st.configure("Treeview.Heading", background="#2a2a3e", foreground=ACC)
        st.configure("TEntry", foreground=FG, insertcolor=FG)
        st.configure("TCombobox", foreground=FG)
        hdr = tk.Frame(self, bg=BG); hdr.pack(fill="x", padx=16, pady=(12, 4))
        tk.Label(hdr, text="◆ MAX", fg=ACC, bg=BG, font=("Segoe UI", 24, "bold")).pack(side="left")
        tk.Label(hdr, text="  learning blockchain · not real money", fg=MUTED, bg=BG, font=("Segoe UI", 10)).pack(side="left", pady=(10, 0))
        self.nb = ttk.Notebook(self); self.nb.pack(fill="both", expand=True, padx=12, pady=8)
        for name in ("Wallets", "Send", "Mine", "Blockchain", "Leaderboard"):
            f = ttk.Frame(self.nb, padding=12); self.nb.add(f, text=name); getattr(self, "build_" + name.lower())(f)
        self.status = tk.Label(self, text="Ready", fg=MUTED, bg=BG, anchor="w"); self.status.pack(fill="x", padx=16, pady=(0, 8))
        self.nb.bind("<<NotebookTabChanged>>", lambda e: self.refresh()); self.refresh()

    # helpers
    def err(self, e): messagebox.showerror("MAX", str(e), parent=self)
    def tree(self, parent, cols, widths):
        t = ttk.Treeview(parent, columns=cols, show="headings")
        for c, w in zip(cols, widths): t.heading(c, text=c); t.column(c, width=w, anchor="w")
        return t
    def ask_pw(self, title, confirm=False):
        p = simpledialog.askstring(title, "Wallet password:", show="•", parent=self)
        if p is None: return None
        if confirm and simpledialog.askstring(title, "Type the password again:", show="•", parent=self) != p:
            self.err("Passwords didn't match."); return None
        return p
    def names(self): return [w["name"] for w in M.list_wallets()]
    def selected_wallet(self):
        s = self.wt.selection()
        if not s: self.err("Pick a wallet in the list first."); return None
        return self.wt.item(s[0])["values"][0]

    # tabs
    def build_wallets(self, f):
        bar = ttk.Frame(f); bar.pack(fill="x", pady=(0, 8))
        for txt, cmd in (("New wallet", self.new_wallet), ("Import from key", self.import_wallet),
                         ("Copy address", self.copy_addr), ("Reveal private key", self.reveal)):
            ttk.Button(bar, text=txt, command=cmd).pack(side="left", padx=4)
        self.wt = self.tree(f, ("Name", "Balance", "Address"), (120, 110, 560)); self.wt.pack(fill="both", expand=True)
    def new_wallet(self):
        n = simpledialog.askstring("New wallet", "Wallet name:", parent=self)
        if not n: return
        p = self.ask_pw("New wallet", True)
        if p is None: return
        try: M.new_wallet(n.strip(), p); self.say(f"Created wallet '{n}'. Remember your password!")
        except M.MaxError as e: self.err(e)
        self.refresh()
    def import_wallet(self):
        n = simpledialog.askstring("Import", "Name for this wallet:", parent=self)
        if not n: return
        k = simpledialog.askstring("Import", "Paste the private key:", show="•", parent=self)
        if not k: return
        p = self.ask_pw("Import", True)
        if p is None: return
        try: a = M.import_wallet(n.strip(), k, p); self.say(f"Imported '{n}' ({a[:12]}...)")
        except M.MaxError as e: self.err(e)
        self.refresh()
    def copy_addr(self):
        n = self.selected_wallet()
        if n: self.clipboard_clear(); self.clipboard_append(M.load_wallet(n)["address"]); self.say(f"Copied {n}'s address")
    def reveal(self):
        n = self.selected_wallet()
        if not n: return
        if not messagebox.askyesno("Secret!", "Your private key is like the password to your money.\nNEVER share it with anyone.\n\nShow it anyway?", icon="warning", parent=self): return
        p = self.ask_pw("Unlock " + n)
        if p is None: return
        try: messagebox.showinfo(f"{n} private key", "KEEP SECRET:\n\n" + M.unlock(n, p)["private"], parent=self)
        except M.MaxError as e: self.err(e)

    def build_send(self, f):
        ttk.Label(f, text="From wallet").grid(row=0, column=0, sticky="w", pady=6)
        self.s_from = ttk.Combobox(f, state="readonly", width=30); self.s_from.grid(row=0, column=1, sticky="w")
        ttk.Label(f, text="To (name or address)").grid(row=1, column=0, sticky="w", pady=6)
        self.s_to = ttk.Entry(f, width=70); self.s_to.grid(row=1, column=1, sticky="w")
        ttk.Label(f, text="Amount (MAX)").grid(row=2, column=0, sticky="w", pady=6)
        self.s_amt = ttk.Entry(f, width=12); self.s_amt.grid(row=2, column=1, sticky="w")
        ttk.Button(f, text="Send MAX", command=self.do_send).grid(row=3, column=1, sticky="w", pady=12)
        ttk.Label(f, text="Sends wait in line until someone mines the next block.", foreground=MUTED).grid(row=4, column=1, sticky="w")
    def do_send(self):
        if not self.s_from.get(): return self.err("Pick a wallet to send from.")
        p = self.ask_pw("Unlock " + self.s_from.get())
        if p is None: return
        try: M.send(self.s_from.get(), p, self.s_to.get(), self.s_amt.get()); self.say("Sent! Now mine a block to confirm it.")
        except M.MaxError as e: self.err(e)
        self.refresh()

    def build_mine(self, f):
        ttk.Label(f, text="Reward goes to").pack(anchor="w")
        self.m_who = ttk.Combobox(f, state="readonly", width=30); self.m_who.pack(anchor="w", pady=6)
        self.m_btn = ttk.Button(f, text=f"⛏  Mine a block (earn MAX)", command=self.do_mine); self.m_btn.pack(anchor="w", pady=6)
        self.m_bar = ttk.Progressbar(f, mode="indeterminate", length=400); self.m_bar.pack(anchor="w", pady=6)
        self.m_msg = ttk.Label(f, text=""); self.m_msg.pack(anchor="w")
        self.m_stats = ttk.Label(f, text="", foreground=MUTED, justify="left"); self.m_stats.pack(anchor="w", pady=10)
    def do_mine(self):
        who = self.m_who.get()
        if not who: return self.err("Pick a wallet to get the reward.")
        self.m_btn.state(["disabled"]); self.m_bar.start(12); self.m_msg.config(text=f"Guessing numbers... ⛏ (difficulty {M.stats(M.load())['next']})")
        def work():
            t0 = time.time()
            try: b = M.mine(who); msg = f"Mined block #{b['index']} in {time.time()-t0:.1f}s (nonce {b['nonce']}) +{b['txs'][-1]['amount']} MAX to {who}!"
            except Exception as e: msg = f"Error: {e}"
            self.after(0, lambda: self.mine_done(msg))
        threading.Thread(target=work, daemon=True).start()
    def mine_done(self, msg):
        self.m_bar.stop(); self.m_btn.state(["!disabled"]); self.m_msg.config(text=msg); self.say(msg); self.refresh()

    def build_blockchain(self, f):
        bar = ttk.Frame(f); bar.pack(fill="x", pady=(0, 8))
        ttk.Button(bar, text="Validate chain", command=self.do_validate).pack(side="left")
        self.v_msg = ttk.Label(bar, text=""); self.v_msg.pack(side="left", padx=12)
        self.b_stats = ttk.Label(f, text="", foreground=MUTED, justify="left"); self.b_stats.pack(anchor="w", pady=(0, 8))
        self.bt = self.tree(f, ("#", "Diff", "Hash", "Prev", "Nonce", "Txs"), (40, 50, 250, 250, 80, 50)); self.bt.pack(fill="both", expand=True)
    def do_validate(self):
        ok, msg = M.validate(M.load()); self.v_msg.config(text=("✅ " if ok else "❌ ") + msg, foreground="#6f6" if ok else "#f66")

    def build_leaderboard(self, f):
        self.lt = self.tree(f, ("Rank", "Name", "Address", "Balance", "Blocks mined"), (70, 120, 300, 110, 110)); self.lt.pack(fill="both", expand=True)

    def say(self, t): self.status.config(text=t)
    def refresh(self):
        try: d = M.load()
        except M.MaxError as e: self.err(e); return
        names = self.names(); st = M.stats_text(d)
        self.m_stats.config(text=st); self.b_stats.config(text=st)
        self.wt.delete(*self.wt.get_children())
        for w in M.list_wallets(): self.wt.insert("", "end", values=(w["name"], f"{M.balance(d, w['address'], False)} MAX", w["address"]))
        for cb in (self.s_from, self.m_who):
            cb["values"] = names
            if cb.get() not in names: cb.set(names[0] if names else "")
        self.bt.delete(*self.bt.get_children())
        for b in reversed(d["chain"]): self.bt.insert("", "end", values=(b["index"], b["difficulty"], b["hash"][:28] + "…", b["prev"][:28] + "…", b["nonce"], len(b["txs"])))
        self.lt.delete(*self.lt.get_children())
        for i, (n, a, bal, m) in enumerate(M.leaderboard(d)):
            self.lt.insert("", "end", values=(M.MEDALS[i] if i < 3 else f"#{i+1}", n, a[:20] + "…", f"{bal} MAX", m))

if __name__ == "__main__":
    App().mainloop()
