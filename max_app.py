"""Max Chain app: a local web UI for max.py (learning project - NOT real money).
Runs only on your own computer (127.0.0.1). Passwords are used once and never stored or logged."""
import json, os, sys, threading, time, webbrowser
from http.server import ThreadingHTTPServer, BaseHTTPRequestHandler
import max as M

STATIC = os.path.join(M.HERE, "static")
LOCK = threading.Lock()          # one writer at a time for sends
MINER = {"running": False, "auto": False, "wallet": None, "nonce": 0, "started": 0, "difficulty": None,
         "last": None, "error": None, "stop": False, "count": 0}

class Stop(Exception): pass

def _progress(n):
    MINER["nonce"] = n
    if MINER["stop"]: raise Stop()

def _mine_loop():
    while True:
        MINER.update(running=True, nonce=0, started=time.time(), error=None, stop=False)
        try:
            MINER["difficulty"] = M.stats(M.load())["next"]
            b = M.mine(MINER["wallet"], progress=_progress)
            MINER["last"] = {"index": b["index"], "nonce": b["nonce"], "hash": b["hash"], "seconds": round(time.time() - MINER["started"], 2),
                             "txs": len(b["txs"]), "difficulty": b["difficulty"], "wallet": MINER["wallet"], "at": time.time()}
            MINER["count"] += 1
        except Stop: MINER["auto"] = False
        except Exception as e: MINER["error"] = str(e); MINER["auto"] = False
        if not MINER["auto"]: break
    MINER["running"] = False

def start_mining(wallet, auto):
    M.load_wallet(wallet)
    MINER["wallet"], MINER["auto"] = wallet, bool(auto)
    if not MINER["running"]: threading.Thread(target=_mine_loop, daemon=True).start()

def tx_view(t, names):
    return {"from": "⛏ Reward" if t["sender"] == "REWARD" else names.get(t["sender"], t["sender"][:12] + "…"),
            "to": names.get(t["to"], t["to"][:12] + "…"), "amount": t["amount"], "from_addr": t["sender"], "to_addr": t["to"], "time": t["time"]}

def block_view(b, names):
    return {"index": b["index"], "hash": b["hash"], "prev": b["prev"], "nonce": b["nonce"], "difficulty": b["difficulty"],
            "time": b["time"], "txs": [tx_view(t, names) for t in b["txs"]]}

def state():
    d = M.load(); names = M.names(); st = M.stats(d)
    wallets = [{"name": w["name"], "address": w["address"], "balance": M.balance(d, w["address"], False),
                "pending": M.balance(d, w["address"])} for w in M.list_wallets()]
    lb = [{"rank": i + 1, "name": n, "address": a, "balance": bal, "mined": m} for i, (n, a, bal, m) in enumerate(M.leaderboard(d))]
    miner = {k: MINER[k] for k in ("running", "auto", "wallet", "nonce", "started", "difficulty", "last", "error", "count")}
    miner["now"] = time.time()
    return {"stats": st, "supply": M.total_supply(d), "reward": M.REWARD, "wallets": wallets, "leaderboard": lb,
            "pending": [tx_view(t, names) for t in d["pending"]], "recent": [block_view(b, names) for b in reversed(d["chain"][-8:])],
            "miner": miner, "limits": {"min": M.MIN_DIFF, "max": M.MAX_DIFF}}

class H(BaseHTTPRequestHandler):
    def log_message(self, *a): pass   # no request logging (keeps passwords out of any logs)
    def send_json(self, obj, code=200):
        body = json.dumps(obj).encode()
        self.send_response(code); self.send_header("Content-Type", "application/json"); self.send_header("Cache-Control", "no-store")
        self.send_header("Content-Length", str(len(body))); self.end_headers(); self.wfile.write(body)
    def send_file(self, name, ctype):
        p = os.path.join(STATIC, name)
        if not os.path.exists(p): return self.send_json({"error": "not found"}, 404)
        data = open(p, "rb").read()
        self.send_response(200); self.send_header("Content-Type", ctype); self.send_header("Content-Length", str(len(data))); self.end_headers(); self.wfile.write(data)
    def do_GET(self):
        path = self.path.split("?")[0]
        try:
            if path in ("/", "/index.html"): return self.send_file("index.html", "text/html; charset=utf-8")
            if path in ("/logo.jpg", "/favicon.ico"): return self.send_file("logo.jpg", "image/jpeg")
            if path == "/api/state": return self.send_json(state())
            if path == "/api/chain":
                d = M.load(); names = M.names(); return self.send_json({"blocks": [block_view(b, names) for b in reversed(d["chain"])]})
            self.send_json({"error": "not found"}, 404)
        except M.MaxError as e: self.send_json({"error": str(e)}, 400)
    def do_POST(self):
        # Only accept requests from our own page (blocks other websites from poking the API)
        origin = self.headers.get("Origin")
        if origin and origin not in (f"http://127.0.0.1:{PORT}", f"http://localhost:{PORT}"):
            return self.send_json({"error": "forbidden"}, 403)
        try:
            n = int(self.headers.get("Content-Length") or 0)
            q = json.loads(self.rfile.read(n) or b"{}")
            p = self.path
            if p == "/api/wallet/new":
                with LOCK: a = M.new_wallet(str(q.get("name", "")).strip(), str(q.get("password", "")))
                return self.send_json({"ok": True, "address": a})
            if p == "/api/wallet/import":
                with LOCK: a = M.import_wallet(str(q.get("name", "")).strip(), str(q.get("key", "")), str(q.get("password", "")))
                return self.send_json({"ok": True, "address": a})
            if p == "/api/wallet/reveal":
                return self.send_json({"ok": True, "key": M.unlock(str(q.get("name", "")), str(q.get("password", "")))["private"]})
            if p == "/api/send":
                with LOCK: tx = M.send(str(q.get("from", "")), str(q.get("password", "")), str(q.get("to", "")), q.get("amount"))
                return self.send_json({"ok": True, "amount": tx["amount"]})
            if p == "/api/mine":
                start_mining(str(q.get("wallet", "")), q.get("auto")); return self.send_json({"ok": True})
            if p == "/api/mine/stop":
                MINER["auto"] = False
                if q.get("now"): MINER["stop"] = True
                return self.send_json({"ok": True})
            if p == "/api/validate":
                ok, msg = M.validate(M.load()); return self.send_json({"ok": ok, "message": msg})
            self.send_json({"error": "not found"}, 404)
        except M.MaxError as e: self.send_json({"error": str(e)}, 400)
        except Exception as e: self.send_json({"error": "Something went wrong: " + type(e).__name__}, 500)

PORT = int(os.environ.get("MAX_PORT", "8765"))

def main():
    try: sys.stdout.reconfigure(encoding="utf-8")
    except Exception: pass
    srv = ThreadingHTTPServer(("127.0.0.1", PORT), H)
    url = f"http://127.0.0.1:{PORT}/"
    print(f"MAX app running at {url}  (only on this computer). Close this window or press Ctrl+C to stop.")
    if "--no-browser" not in sys.argv: threading.Timer(0.8, lambda: webbrowser.open(url)).start()
    try: srv.serve_forever()
    except KeyboardInterrupt: print("Bye!")

if __name__ == "__main__": main()
