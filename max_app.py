"""Max Chain app + network node (learning project - NOT real money).
The app (your wallets) only listens on 127.0.0.1. The P2P node port talks to other Max nodes.
Passwords are used once and never stored or logged."""
import argparse, json, os, sys, threading, time, webbrowser, urllib.request, re

ap = argparse.ArgumentParser(description="MAX app and node")
ap.add_argument("--port", type=int, default=int(os.environ.get("MAX_PORT", "8765")), help="app port (always 127.0.0.1 only)")
ap.add_argument("--p2p-port", type=int, default=int(os.environ.get("MAX_P2P_PORT", "8766")), help="node port for other players")
ap.add_argument("--public", action="store_true", default=os.environ.get("MAX_PUBLIC") == "1",
                help="let OTHER computers connect to your node (listen on 0.0.0.0). Off by default.")
ap.add_argument("--advertise", default=os.environ.get("MAX_ADVERTISE"), help="host:port other nodes should use to reach you")
ap.add_argument("--peer", action="append", default=[], help="peer host:port (can repeat)")
ap.add_argument("--data", help="data folder (chain, wallets, peers) - use a different one per node")
ap.add_argument("--no-browser", action="store_true")
ARGS = ap.parse_args()
if ARGS.data: os.environ["MAX_DATA"] = ARGS.data

from http.server import ThreadingHTTPServer, BaseHTTPRequestHandler
import max as M

STATIC = os.path.join(M.HERE, "static")
PORT, P2P_PORT = ARGS.port, ARGS.p2p_port
P2P_HOST = "0.0.0.0" if ARGS.public else "127.0.0.1"
ME = ARGS.advertise or f"127.0.0.1:{P2P_PORT}"
MAX_BODY = 20_000_000
PEER_RE = re.compile(r"^[A-Za-z0-9.\-]{1,253}:\d{1,5}$")

# ---------------- peers / networking ----------------
PEER_INFO = {}           # addr -> {"ok", "height", "work", "seen", "error"}
SYNC = {"status": "starting", "last": None, "switches": 0, "rejected": 0, "log": []}

def log(msg):
    SYNC["log"] = ([{"t": time.time(), "msg": msg}] + SYNC["log"])[:30]
    print(time.strftime("%H:%M:%S"), msg, flush=True)

def peers(): return [p for p in M.load_peers() if p != ME]

def add_peer(addr, announce=True):
    addr = addr.strip()
    if not PEER_RE.match(addr) or not (0 < int(addr.rsplit(":", 1)[1]) < 65536): raise M.MaxError("Peer must look like host:port, e.g. 192.168.1.20:8766")
    if addr == ME: raise M.MaxError("That's this node!")
    p = M.load_peers()
    if addr not in p:
        if len(p) >= 50: raise M.MaxError("Too many peers (50 max).")
        M.save_peers(p + [addr]); log(f"Added peer {addr}")
    if announce: threading.Thread(target=lambda: (call(addr, "/p2p/peers", {"addr": ME}), sync_with(addr)), daemon=True).start()

def remove_peer(addr):
    M.save_peers([p for p in M.load_peers() if p != addr]); PEER_INFO.pop(addr, None)

def call(addr, path, body=None, timeout=5):
    req = urllib.request.Request(f"http://{addr}{path}", data=json.dumps(body).encode() if body is not None else None,
                                 headers={"Content-Type": "application/json", "X-Max-Peer": ME})
    with urllib.request.urlopen(req, timeout=timeout) as r:
        data = r.read(MAX_BODY + 1)
        if len(data) > MAX_BODY: raise ValueError("response too big")
        return json.loads(data)

def broadcast(path, body, skip=None):
    def go(p):
        try: call(p, path, body, timeout=4)
        except Exception as e: PEER_INFO.setdefault(p, {})["error"] = str(e)[:80]
    for p in peers():
        if p != skip: threading.Thread(target=go, args=(p,), daemon=True).start()

def sync_with(addr):
    """Ask a peer how much work its chain has; download it if it's better (longest valid chain wins)."""
    try:
        info = call(addr, "/p2p/info")
        if ME not in info.get("peers", []):
            try: call(addr, "/p2p/peers", {"addr": ME})   # say hi so they send us new blocks
            except Exception: pass
        PEER_INFO[addr] = {"ok": True, "height": info["height"], "work": info["work"], "seen": time.time(), "error": None, "same_network": None}
        d = M.load()
        same = info.get("genesis") == d["chain"][0]["hash"]; PEER_INFO[addr]["same_network"] = same
        if not same: PEER_INFO[addr]["error"] = "different network rules"; return
        if info["work"] > M.work(d["chain"]):
            ch = call(addr, "/p2p/chain", timeout=20)["chain"]
            try:
                if M.replace_chain(ch):
                    SYNC["switches"] += 1; MINER["tip_changed"] = True
                    log(f"Switched to {addr}'s chain (height {len(ch)-1}, more work)")
            except M.MaxError as e: SYNC["rejected"] += 1; log(f"Rejected chain from {addr}: {e}")
        # pick up their waiting payments too
        for tx in call(addr, "/p2p/mempool").get("pending", []):
            try: M.add_tx(tx)
            except M.MaxError: pass
        for p in info.get("peers", [])[:20]:   # learn about other nodes
            if p != ME and p not in M.load_peers() and PEER_RE.match(p):
                try: add_peer(p, announce=False)
                except M.MaxError: pass
    except Exception as e:
        PEER_INFO[addr] = dict(PEER_INFO.get(addr, {}), ok=False, error=str(e)[:80], seen=PEER_INFO.get(addr, {}).get("seen"))

def sync_all():
    SYNC["status"] = "syncing"
    ts = [threading.Thread(target=sync_with, args=(p,)) for p in peers()]
    for t in ts: t.start()
    for t in ts: t.join(30)
    SYNC["status"] = "synced" if any(PEER_INFO.get(p, {}).get("ok") for p in peers()) else ("no peers" if not peers() else "can't reach peers")
    SYNC["last"] = time.time()

def sync_loop():
    while True:
        sync_all(); time.sleep(5)

# ---------------- mining ----------------
MINER = {"running": False, "auto": False, "wallet": None, "nonce": 0, "started": 0, "difficulty": None,
         "last": None, "error": None, "stop": False, "count": 0, "tip_changed": False}
class Stop(Exception): pass
class Restart(Exception): pass

def _progress(n):
    MINER["nonce"] = n
    if MINER["stop"]: raise Stop()
    if MINER["tip_changed"]: raise Restart()   # a peer found a block: start over on the new tip

def _mine_loop():
    while True:
        MINER.update(running=True, nonce=0, started=time.time(), error=None, stop=False, tip_changed=False)
        try:
            MINER["difficulty"] = M.stats(M.load())["next"]
            b = M.mine(MINER["wallet"], progress=_progress)
            MINER["last"] = {"index": b["index"], "nonce": b["nonce"], "hash": b["hash"], "seconds": round(time.time() - MINER["started"], 2),
                             "txs": len(b["txs"]) - 1, "reward": b["txs"][-1]["amount"], "difficulty": b["difficulty"], "wallet": MINER["wallet"], "at": time.time()}
            MINER["count"] += 1; log(f"Mined block #{b['index']} (+{b['txs'][-1]['amount']} MAX)")
            broadcast("/p2p/blocks", {"block": b})
        except Restart: continue
        except Stop: MINER["auto"] = False
        except Exception as e: MINER["error"] = str(e); MINER["auto"] = MINER["auto"] and "first" in str(e)
        if not MINER["auto"]: break
    MINER["running"] = False

def start_mining(wallet, auto):
    M.load_wallet(wallet)
    MINER["wallet"], MINER["auto"] = wallet, bool(auto)
    if not MINER["running"]: threading.Thread(target=_mine_loop, daemon=True).start()

# ---------------- views ----------------
def tx_view(t, names):
    if "sender" not in t: return None
    return {"from": "⛏ Reward" if t["sender"] == "REWARD" else names.get(t["sender"], t["sender"][:12] + "…"),
            "to": names.get(t["to"], t["to"][:12] + "…"), "amount": t["amount"], "fee": t.get("fee", t.get("fees", 0)),
            "nonce": t.get("nonce"), "from_addr": t["sender"], "to_addr": t["to"], "time": t["time"], "reward": t["sender"] == "REWARD"}

def block_view(b, names):
    return {"index": b["index"], "hash": b["hash"], "prev": b["prev"], "nonce": b["nonce"], "difficulty": b["difficulty"],
            "time": b["time"], "txs": [v for v in (tx_view(t, names) for t in b["txs"]) if v]}

def network():
    d = M.load(); st = M.stats(d)
    return {"me": ME, "p2p_port": P2P_PORT, "public": ARGS.public, "height": st["height"], "work": st["work"], "tip": st["tip"],
            "chain_id": st["chain_id"], "sync": SYNC,
            "peers": [dict({"addr": p, "ok": None, "height": None, "seen": None, "error": None}, **PEER_INFO.get(p, {}), addr=p) for p in peers()]}

def state():
    d = M.load(); names = M.names(); st = M.stats(d); conf = M.chain_state(d); mem = M.mempool_state(d)
    wallets = [{"name": w["name"], "address": w["address"], "balance": conf["bal"].get(w["address"], 0),
                "pending": mem["bal"].get(w["address"], 0)} for w in M.list_wallets()]
    lb = [{"rank": i + 1, "name": n, "address": a, "balance": bal, "mined": m} for i, (n, a, bal, m) in enumerate(M.leaderboard(d))]
    miner = {k: MINER[k] for k in ("running", "auto", "wallet", "nonce", "started", "difficulty", "last", "error", "count")}
    miner["now"] = time.time()
    return {"stats": st, "supply": st["supply"], "reward": st["reward"], "wallets": wallets, "leaderboard": lb,
            "pending": [tx_view(t, names) for t in d["pending"]], "recent": [block_view(b, names) for b in reversed(d["chain"][-8:])],
            "miner": miner, "limits": {"min": M.MIN_DIFF, "max": M.MAX_DIFF},
            "net": {"peers": len(peers()), "online": sum(1 for p in peers() if PEER_INFO.get(p, {}).get("ok")), "status": SYNC["status"], "public": ARGS.public}}

# ---------------- HTTP plumbing ----------------
class Base(BaseHTTPRequestHandler):
    def log_message(self, *a): pass   # no request logs (keeps passwords out of logs)
    def send_json(self, obj, code=200):
        body = json.dumps(obj).encode()
        self.send_response(code); self.send_header("Content-Type", "application/json"); self.send_header("Cache-Control", "no-store")
        self.send_header("Content-Length", str(len(body))); self.end_headers(); self.wfile.write(body)
    def body(self):
        n = int(self.headers.get("Content-Length") or 0)
        if n > MAX_BODY: raise M.MaxError("request too big")
        return json.loads(self.rfile.read(n) or b"{}")

class P2P(Base):
    """Endpoints other nodes use. Never touches wallets or passwords."""
    def do_GET(self):
        try:
            p = self.path.split("?")[0]; d = M.load()
            if p == "/p2p/info": return self.send_json({"height": len(d["chain"]) - 1, "work": M.work(d["chain"]), "tip": d["chain"][-1]["hash"],
                                                       "genesis": d["chain"][0]["hash"], "version": M.VERSION, "peers": peers()})
            if p == "/p2p/chain": return self.send_json({"chain": d["chain"]})
            if p == "/p2p/blocks":   # recent blocks
                return self.send_json({"blocks": d["chain"][-20:]})
            if p == "/p2p/mempool": return self.send_json({"pending": d["pending"]})
            if p == "/p2p/peers": return self.send_json({"peers": peers()})
            self.send_json({"error": "not found"}, 404)
        except M.MaxError as e: self.send_json({"error": str(e)}, 400)
    def do_POST(self):
        sender = self.headers.get("X-Max-Peer")
        try:
            q = self.body(); p = self.path
            if p == "/p2p/blocks":
                b = q.get("block"); r = M.add_block(b)
                if r == "added":
                    MINER["tip_changed"] = True; log(f"Got block #{b['index']} from {sender or 'a peer'}"); broadcast("/p2p/blocks", {"block": b}, skip=sender)
                elif r == "need_sync" and sender and PEER_RE.match(sender):
                    threading.Thread(target=sync_with, args=(sender,), daemon=True).start()
                return self.send_json({"result": r})
            if p == "/p2p/tx":
                if M.add_tx(q.get("tx")): broadcast("/p2p/tx", {"tx": q["tx"]}, skip=sender)
                return self.send_json({"result": "ok"})
            if p == "/p2p/peers":
                add_peer(str(q.get("addr", "")), announce=False); return self.send_json({"result": "ok", "peers": peers()})
            self.send_json({"error": "not found"}, 404)
        except M.MaxError as e:
            if self.path == "/p2p/blocks": SYNC["rejected"] += 1; log(f"Rejected block from {sender or '?'}: {e}")
            self.send_json({"error": str(e)}, 400)
        except Exception as e: self.send_json({"error": "bad request: " + type(e).__name__}, 400)

class App(Base):
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
            if path == "/api/network": return self.send_json(network())
            if path == "/api/chain":
                d = M.load(); names = M.names(); return self.send_json({"blocks": [block_view(b, names) for b in reversed(d["chain"])]})
            self.send_json({"error": "not found"}, 404)
        except M.MaxError as e: self.send_json({"error": str(e)}, 400)
    def do_POST(self):
        origin = self.headers.get("Origin")   # only our own page may use the wallet API
        if origin and origin not in (f"http://127.0.0.1:{PORT}", f"http://localhost:{PORT}"): return self.send_json({"error": "forbidden"}, 403)
        try:
            q = self.body(); p = self.path
            if p == "/api/wallet/new": return self.send_json({"ok": True, "address": M.new_wallet(str(q.get("name", "")).strip(), str(q.get("password", "")))})
            if p == "/api/wallet/import": return self.send_json({"ok": True, "address": M.import_wallet(str(q.get("name", "")).strip(), str(q.get("key", "")), str(q.get("password", "")))})
            if p == "/api/wallet/reveal": return self.send_json({"ok": True, "key": M.unlock(str(q.get("name", "")), str(q.get("password", "")))["private"]})
            if p == "/api/send":
                tx = M.send(str(q.get("from", "")), str(q.get("password", "")), str(q.get("to", "")), q.get("amount"), q.get("fee") or 0)
                broadcast("/p2p/tx", {"tx": tx}); return self.send_json({"ok": True, "amount": tx["amount"], "fee": tx["fee"], "nonce": tx["nonce"]})
            if p == "/api/mine": start_mining(str(q.get("wallet", "")), q.get("auto")); return self.send_json({"ok": True})
            if p == "/api/mine/stop":
                MINER["auto"] = False
                if q.get("now"): MINER["stop"] = True
                return self.send_json({"ok": True})
            if p == "/api/validate": ok, msg = M.validate(M.load()); return self.send_json({"ok": ok, "message": msg})
            if p == "/api/peers/add": add_peer(str(q.get("addr", ""))); return self.send_json({"ok": True})
            if p == "/api/peers/remove": remove_peer(str(q.get("addr", ""))); return self.send_json({"ok": True})
            if p == "/api/sync": threading.Thread(target=sync_all, daemon=True).start(); return self.send_json({"ok": True})
            self.send_json({"error": "not found"}, 404)
        except M.MaxError as e: self.send_json({"error": str(e)}, 400)
        except Exception as e: self.send_json({"error": "Something went wrong: " + type(e).__name__}, 500)

def main():
    try: sys.stdout.reconfigure(encoding="utf-8")
    except Exception: pass
    M.load()
    for p in ARGS.peer:
        try: add_peer(p, announce=False)
        except M.MaxError as e: print("Peer skipped:", e)
    p2p = ThreadingHTTPServer((P2P_HOST, P2P_PORT), P2P)
    threading.Thread(target=p2p.serve_forever, daemon=True).start()
    app = ThreadingHTTPServer(("127.0.0.1", PORT), App)
    url = f"http://127.0.0.1:{PORT}/"
    print(f"MAX app: {url}  (only this computer)")
    print(f"MAX node: {P2P_HOST}:{P2P_PORT}  " + ("PUBLIC - other computers can connect" if ARGS.public else "(local only; use --public to play with others)"))
    print(f"Data folder: {M.DATA}")
    for p in peers(): threading.Thread(target=lambda p=p: call(p, "/p2p/peers", {"addr": ME}), daemon=True).start()
    threading.Thread(target=sync_loop, daemon=True).start()
    if not ARGS.no_browser: threading.Timer(0.8, lambda: webbrowser.open(url)).start()
    try: app.serve_forever()
    except KeyboardInterrupt: print("Bye!")

if __name__ == "__main__": main()
