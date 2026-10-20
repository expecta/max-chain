"""Max - a tiny learning blockchain with the MAX coin. NOT a real cryptocurrency, has no value."""
import hashlib, json, os, sys, time, threading

HERE = os.path.dirname(os.path.abspath(__file__))
DATA = os.path.abspath(os.environ.get("MAX_DATA", HERE))   # folder for chain/wallets/peers (one per node)
CHAIN_FILE = os.path.join(DATA, "chain.json")
WALLET_DIR = os.path.join(DATA, "wallets")
PEERS_FILE = os.path.join(DATA, "peers.json")
# Network rules. They are baked into the genesis block: nodes with different rules are different networks.
START_DIFFICULTY = int(os.environ.get("MAX_DIFFICULTY", "4"))
TARGET_SECONDS = int(os.environ.get("MAX_TARGET", "30"))       # wanted time per block
RETARGET_EVERY = int(os.environ.get("MAX_RETARGET", "10"))     # check speed every N blocks
HALVING_EVERY = int(os.environ.get("MAX_HALVING", "210000"))   # reward halves every N blocks
REWARD = 50                                                    # starting block reward
MAX_SUPPLY = 21_000_000
MIN_DIFF, MAX_DIFF = 3, 7
MAX_TXS_PER_BLOCK = 200
VERSION = "max-v2"
LOCK = threading.RLock()   # one change to the chain at a time

def sha(s): return hashlib.sha256(s.encode()).hexdigest()

# ---------- wallets (password-locked) ----------
import base64, getpass
from cryptography.fernet import Fernet, InvalidToken
from cryptography.hazmat.primitives.kdf.scrypt import Scrypt

class MaxError(Exception):
    """Friendly error shown to the user (CLI and GUI)."""

def _fernet(password, salt):
    key = Scrypt(salt=salt, length=32, n=2**15, r=8, p=1).derive(password.encode())
    return Fernet(base64.urlsafe_b64encode(key))

def _wpath(name): return os.path.join(WALLET_DIR, name + ".json")

def address_of(priv_hex):
    try: k = Ed25519PrivateKey.from_private_bytes(bytes.fromhex(priv_hex.strip()))
    except Exception: raise MaxError("That doesn't look like a valid private key (64 hex characters).")
    return k.public_key().public_bytes(S.Encoding.Raw, S.PublicFormat.Raw).hex()

def _check_name(name):
    if not name or not all(c.isalnum() or c in "-_" for c in name):
        raise MaxError("Wallet names can only use letters, numbers, - and _")

def save_wallet(name, priv_hex, password, overwrite=False):
    _check_name(name)
    if len(password) < 4: raise MaxError("Password must be at least 4 characters.")
    os.makedirs(WALLET_DIR, exist_ok=True)
    if os.path.exists(_wpath(name)) and not overwrite: raise MaxError(f"Wallet '{name}' already exists.")
    addr = address_of(priv_hex); salt = os.urandom(16)
    token = _fernet(password, salt).encrypt(priv_hex.strip().encode()).decode()
    json.dump({"name": name, "address": addr, "salt": salt.hex(), "encrypted_key": token}, open(_wpath(name), "w"), indent=2)
    return addr

def new_wallet(name, password):
    k = Ed25519PrivateKey.generate()
    return save_wallet(name, k.private_bytes(S.Encoding.Raw, S.PrivateFormat.Raw, S.NoEncryption()).hex(), password)

def import_wallet(name, priv_hex, password): return save_wallet(name, priv_hex, password)

def load_wallet(name):
    if not os.path.exists(_wpath(name)): raise MaxError(f"No wallet named '{name}'.")
    return json.load(open(_wpath(name)))

def list_wallets():
    if not os.path.isdir(WALLET_DIR): return []
    return sorted((load_wallet(f[:-5]) for f in os.listdir(WALLET_DIR) if f.endswith(".json")), key=lambda w: w["name"])

def unlock(name, password):
    w = load_wallet(name)
    try: priv = _fernet(password, bytes.fromhex(w["salt"])).decrypt(w["encrypted_key"].encode()).decode()
    except InvalidToken: raise MaxError("Oops! Wrong password for that wallet. Try again.")
    return dict(w, private=priv)

def export_wallet(name, file):
    w = load_wallet(name); json.dump(w, open(file, "w"), indent=2)  # stays encrypted

def resolve(who):
    return load_wallet(who)["address"] if os.path.exists(_wpath(who)) else who

# ---------- transactions ----------
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey, Ed25519PublicKey
from cryptography.hazmat.primitives import serialization as S

TX_FIELDS = ("chain", "sender", "to", "amount", "fee", "nonce", "time")
def tx_body(tx): return json.dumps({k: tx[k] for k in TX_FIELDS}, sort_keys=True)
def tx_id(tx): return sha(tx_body(tx) + tx.get("signature", ""))

def sign_tx(wallet, to, amount, fee, nonce, chain_id):
    tx = {"chain": chain_id, "sender": wallet["address"], "to": to, "amount": amount, "fee": fee, "nonce": nonce, "time": time.time()}
    key = Ed25519PrivateKey.from_private_bytes(bytes.fromhex(wallet["private"]))
    tx["signature"] = key.sign(tx_body(tx).encode()).hex()
    return tx

def is_addr(a): return isinstance(a, str) and len(a) == 64 and all(c in "0123456789abcdef" for c in a)
def is_int(x): return type(x) is int

def verify_sig(tx):
    try:
        Ed25519PublicKey.from_public_bytes(bytes.fromhex(tx["sender"])).verify(bytes.fromhex(tx["signature"]), tx_body(tx).encode())
        return True
    except Exception: return False

def check_tx(tx, st, chain_id):
    """Check a normal payment against a state {bal, nonce}. Returns error text or None."""
    if not isinstance(tx, dict) or any(k not in tx for k in TX_FIELDS + ("signature",)): return "malformed transaction"
    if tx["chain"] != chain_id: return "transaction is for a different Max network"
    if not (is_addr(tx["sender"]) and is_addr(tx["to"])): return "bad address"
    if not (is_int(tx["amount"]) and tx["amount"] > 0): return "amount must be a whole number above 0"
    if not (is_int(tx["fee"]) and tx["fee"] >= 0): return "fee must be a whole number, 0 or more"
    if not is_int(tx["nonce"]) or tx["nonce"] != st["nonce"].get(tx["sender"], 0) + 1:
        return f"wrong nonce (expected {st['nonce'].get(tx['sender'], 0) + 1}) - replayed or out-of-order transaction"
    if not verify_sig(tx): return "bad signature"
    if st["bal"].get(tx["sender"], 0) < tx["amount"] + tx["fee"]: return "not enough MAX (amount + fee)"
    return None

def apply_tx(tx, st):
    st["bal"][tx["sender"]] -= tx["amount"] + tx["fee"]
    st["bal"][tx["to"]] = st["bal"].get(tx["to"], 0) + tx["amount"]
    st["nonce"][tx["sender"]] = tx["nonce"]

# ---------- blocks / rules ----------
def block_hash(b):
    return sha(json.dumps({k: b[k] for k in ("index", "time", "txs", "prev", "nonce", "difficulty")}, sort_keys=True))

_GENESIS = None
def make_genesis():
    """Same rules -> same genesis on every computer, so nodes can find each other's chain."""
    global _GENESIS
    if _GENESIS is None: _GENESIS = json.dumps(_make_genesis())
    return json.loads(_GENESIS)

def _make_genesis():
    rules = {"version": VERSION, "target": TARGET_SECONDS, "retarget": RETARGET_EVERY, "halving": HALVING_EVERY,
             "reward": REWARD, "max_supply": MAX_SUPPLY, "start_difficulty": START_DIFFICULTY}
    g = {"index": 0, "time": 1760000000, "txs": [{"rules": rules}], "prev": "0" * 64, "nonce": 0, "difficulty": START_DIFFICULTY}
    while not block_hash(g).startswith("0" * START_DIFFICULTY): g["nonce"] += 1
    g["hash"] = block_hash(g); return g

def rules(chain): return chain[0]["txs"][0]["rules"]
def chain_id(chain): return chain[0]["hash"][:16]
def work(chain): return sum(16 ** b["difficulty"] for b in chain)

def subsidy(index, minted, r):
    halvings = index // r["halving"]
    base = r["reward"] >> halvings if halvings < 64 else 0
    return max(0, min(base, r["max_supply"] - minted))

def expected_difficulty(chain, index):
    if index == 0: return chain[0]["difficulty"]
    prev = chain[index - 1]["difficulty"]; r = rules(chain); n = r["retarget"]
    if index % n != 0 or index < n: return prev
    took = chain[index - 1]["time"] - chain[index - n]["time"]
    want = r["target"] * (n - 1)
    if took < want / 2: return min(MAX_DIFF, prev + 1)
    if took > want * 2: return max(MIN_DIFF, prev - 1)
    return prev

def new_state(): return {"bal": {}, "nonce": {}, "minted": 0, "mined": {}}

def check_block(b, chain, st, now=None):
    """Check block b as the next block after `chain` with state `st`; applies it to st. Returns error or None."""
    i = len(chain); prev = chain[-1]; r = rules(chain); cid = chain_id(chain)
    if not isinstance(b, dict) or any(k not in b for k in ("index", "time", "txs", "prev", "nonce", "difficulty", "hash")): return "malformed block"
    if b["index"] != i: return f"wrong index {b['index']}"
    if b["prev"] != prev["hash"]: return "doesn't link to the previous block"
    if block_hash(b) != b["hash"]: return "hash doesn't match contents (tampered!)"
    if b["difficulty"] != expected_difficulty(chain + [b], i): return f"wrong difficulty (should be {expected_difficulty(chain + [b], i)})"
    if not b["hash"].startswith("0" * b["difficulty"]): return "not enough proof-of-work"
    if not isinstance(b["time"], (int, float)) or b["time"] < prev["time"]: return "time goes backwards"
    if b["time"] > (now or time.time()) + 120: return "block from the future"
    txs = b["txs"]
    if not isinstance(txs, list) or not txs or len(txs) > MAX_TXS_PER_BLOCK + 1: return "bad transaction list"
    cb = txs[-1]
    if cb.get("sender") != "REWARD" or not is_addr(cb.get("to")) or not is_int(cb.get("amount")) or cb.get("height") != i:
        return "last transaction must be the miner reward"
    fees = 0
    for t in txs[:-1]:
        err = check_tx(t, st, cid)
        if err: return "transaction: " + err
        apply_tx(t, st); fees += t["fee"]
    allowed = subsidy(i, st["minted"], r) + fees
    if cb["amount"] < 0 or cb["amount"] > allowed: return f"miner reward too big ({cb['amount']} > {allowed})"
    st["bal"][cb["to"]] = st["bal"].get(cb["to"], 0) + cb["amount"]
    st["minted"] += cb["amount"] - fees
    st["mined"][cb["to"]] = st["mined"].get(cb["to"], 0) + 1
    return None

def replay(chain):
    """Check a whole chain from the start. Returns (error or None, state)."""
    st = new_state()
    if not chain or chain[0] != make_genesis(): return "different genesis block (different network or old version)", st
    for i in range(1, len(chain)):
        err = check_block(chain[i], chain[:i], st)
        if err: return f"block {i}: {err}", st
    return None, st

def mine_block(chain, txs, progress=None):
    i = len(chain)
    b = {"index": i, "time": max(time.time(), chain[-1]["time"]), "txs": txs, "prev": chain[-1]["hash"], "nonce": 0, "difficulty": 0}
    b["difficulty"] = expected_difficulty(chain + [b], i); want = "0" * b["difficulty"]
    while True:
        h = block_hash(b)
        if h.startswith(want): b["hash"] = h; return b
        b["nonce"] += 1
        if progress and b["nonce"] % 20000 == 0: progress(b["nonce"])   # may raise to stop

# ---------- storage ----------
def load():
    with LOCK:
        if os.path.exists(CHAIN_FILE):
            d = json.load(open(CHAIN_FILE))
            if not d["chain"][0]["txs"] or "rules" not in d["chain"][0]["txs"][0]:
                raise MaxError("This chain.json is from an older Max version. Delete chain.json to start a new chain (wallets are fine).")
            if d["chain"][0] != make_genesis():
                raise MaxError("chain.json was made with different network rules (MAX_HALVING/MAX_TARGET/...). Use the same settings or delete chain.json.")
            return d
        d = {"chain": [make_genesis()], "pending": []}; save(d); return d

def save(d):
    with LOCK:
        os.makedirs(DATA, exist_ok=True)
        tmp = CHAIN_FILE + ".tmp"; json.dump(d, open(tmp, "w"), indent=1); os.replace(tmp, CHAIN_FILE)

def chain_state(d):
    err, st = replay(d["chain"])
    if err: raise MaxError("Your chain.json is broken: " + err)
    return st

def mempool_state(d):
    """State after confirmed chain + all pending transactions."""
    st = chain_state(d)
    for t in d["pending"]: apply_tx(t, st)
    return st

def rebuild_mempool(d, candidates):
    """Keep only pending txs that are still valid on top of the chain (in order)."""
    st = chain_state(d); cid = chain_id(d["chain"]); keep, seen = [], set()
    for t in sorted(candidates, key=lambda t: (t.get("sender", ""), t.get("nonce", 0))):
        k = tx_id(t)
        if k in seen or check_tx(t, st, cid): continue
        apply_tx(t, st); keep.append(t); seen.add(k)
    d["pending"] = keep

def add_tx(tx):
    """Add a transaction from anywhere (you or a peer). Returns True if it was new."""
    with LOCK:
        d = load()
        if any(tx_id(t) == tx_id(tx) for t in d["pending"]): return False
        err = check_tx(tx, mempool_state(d), chain_id(d["chain"]))
        if err: raise MaxError("Transaction rejected: " + err)
        d["pending"].append(tx); save(d); return True

def add_block(b):
    """Add a block from a peer or our miner. Returns 'added', 'known', 'need_sync' or raises."""
    with LOCK:
        d = load(); ch = d["chain"]
        if any(x["hash"] == b.get("hash") for x in ch): return "known"
        if b.get("prev") != ch[-1]["hash"]:
            return "need_sync" if isinstance(b.get("index"), int) and b["index"] >= len(ch) else "stale"
        st = chain_state(d)
        err = check_block(b, ch, st)
        if err: raise MaxError("Block rejected: " + err)
        ch.append(b); rebuild_mempool(d, d["pending"]); save(d); return "added"

def replace_chain(new_chain):
    """Fork choice: switch to new_chain if it is valid and has MORE total work. Returns True if switched."""
    with LOCK:
        d = load()
        if work(new_chain) <= work(d["chain"]): return False
        err, _ = replay(new_chain)
        if err: raise MaxError("Peer chain rejected: " + err)
        old = d["chain"]; common = 0
        while common < min(len(old), len(new_chain)) and old[common]["hash"] == new_chain[common]["hash"]: common += 1
        orphaned = [t for b in old[common:] for t in b["txs"][:-1]]   # give dropped payments another chance
        d["chain"] = new_chain; rebuild_mempool(d, orphaned + d["pending"]); save(d); return True

def balance(d, addr, include_pending=True):
    return (mempool_state(d) if include_pending else chain_state(d))["bal"].get(addr, 0)

def validate(d):
    err, st = replay(d["chain"])
    return (False, err) if err else (True, f"Chain is VALID ({len(d['chain'])} blocks, {st['minted']:,} MAX in circulation)")

def send(from_name, password, to, amount, fee=0):
    try: amount, fee = int(amount), int(fee or 0)
    except Exception: raise MaxError("Amount and fee must be whole numbers.")
    if amount <= 0: raise MaxError("Amount must be more than 0.")
    if fee < 0: raise MaxError("Fee can't be negative.")
    w = unlock(from_name, password); to = resolve(str(to).strip())
    if not is_addr(to): raise MaxError("Send to a wallet name or a 64-character address.")
    with LOCK:
        d = load(); st = mempool_state(d); have = st["bal"].get(w["address"], 0)
        if have < amount + fee: raise MaxError(f"Not enough MAX! {from_name} has {have} (need {amount + fee} with fee).")
        tx = sign_tx(w, to, amount, fee, st["nonce"].get(w["address"], 0) + 1, chain_id(d["chain"]))
        add_tx(tx); return tx

def build_block_txs(d, miner_addr):
    """Pick pending txs (biggest fee first, nonces in order) and add the miner reward."""
    st = chain_state(d); cid = chain_id(d["chain"]); picked = []
    pool = sorted(d["pending"], key=lambda t: (-t["fee"], t["nonce"]))
    progress = True
    while progress and len(picked) < MAX_TXS_PER_BLOCK:
        progress = False
        for t in pool:
            if t in picked or check_tx(t, st, cid): continue
            apply_tx(t, st); picked.append(t); progress = True
            if len(picked) >= MAX_TXS_PER_BLOCK: break
    i = len(d["chain"]); fees = sum(t["fee"] for t in picked)
    reward = subsidy(i, st["minted"], rules(d["chain"])) + fees
    return picked + [{"sender": "REWARD", "to": miner_addr, "amount": reward, "height": i, "fees": fees, "time": time.time(), "signature": ""}]

def mine(miner_name, progress=None):
    w = load_wallet(miner_name); d = load()
    b = mine_block(d["chain"], build_block_txs(d, w["address"]), progress)
    r = add_block(b)
    if r != "added": raise MaxError("Someone else found a block first. Try again!")
    return b

def total_supply(d): return chain_state(d)["minted"]

def stats(d):
    c = d["chain"]; r = rules(c); n = r["retarget"]; nxt = len(c); st = chain_state(d)
    recent = c[max(1, nxt - n):]
    avg = (recent[-1]["time"] - recent[0]["time"]) / (len(recent) - 1) if len(recent) > 1 else None
    nr = ((nxt // n) + (0 if nxt % n == 0 and nxt >= n else 1)) * n
    nh = (nxt // r["halving"] + 1) * r["halving"]
    return {"height": nxt - 1, "current": c[-1]["difficulty"], "next": expected_difficulty(c + [{"time": time.time()}], nxt),
            "target": r["target"], "every": n, "next_retarget": nr, "blocks_left": nr - nxt, "avg": avg,
            "supply": st["minted"], "max_supply": r["max_supply"], "reward": subsidy(nxt, st["minted"], r),
            "halving_every": r["halving"], "next_halving": nh, "halvings": nxt // r["halving"],
            "work": work(c), "tip": c[-1]["hash"], "mempool": len(d["pending"]), "chain_id": chain_id(c)}

# ---------- leaderboard ----------
MEDALS = ["\U0001F947", "\U0001F948", "\U0001F949"]

def names(): return {w["address"]: w["name"] for w in list_wallets()}

def leaderboard(d):
    st = chain_state(d); nm = names()
    addrs = set(nm) | set(st["bal"])
    rows = [(nm.get(a, "?"), a, st["bal"].get(a, 0), st["mined"].get(a, 0)) for a in addrs]
    rows.sort(key=lambda r: (-r[2], -r[3], r[0]))
    return rows

# ---------- peers ----------
def load_peers():
    try: return json.load(open(PEERS_FILE))
    except Exception: return []
def save_peers(p):
    os.makedirs(DATA, exist_ok=True); json.dump(sorted(set(p))[:50], open(PEERS_FILE, "w"), indent=1)

# ---------- explorer ----------
def explorer(port=8000):
    from http.server import HTTPServer, BaseHTTPRequestHandler
    import html
    class H(BaseHTTPRequestHandler):
        def do_GET(self):
            d = load(); ok, msg = validate(d)
            rows = "".join(f"<div class=b><b>Block #{b['index']}</b> nonce {b['nonce']}<br><small>hash {b['hash']}<br>prev {b['prev']}</small><ul>" +
                "".join(f"<li>{html.escape(t['sender'][:12])} &rarr; {html.escape(t['to'][:12])}: {t['amount']} MAX</li>" for t in b["txs"] if "sender" in t) + "</ul></div>"
                for b in reversed(d["chain"]))
            lb = "".join(f"<tr><td>{MEDALS[i] if i < 3 else i+1}</td><td>{html.escape(n)}</td><td>{a[:12]}...</td><td>{bal} MAX</td><td>{m}</td></tr>" for i, (n, a, bal, m) in enumerate(leaderboard(d)))
            rows = f"<h2>Leaderboard</h2><table border=1 cellpadding=6><tr><th>Rank</th><th>Name</th><th>Address</th><th>Balance</th><th>Blocks mined</th></tr>{lb}</table><h2>Blocks</h2>" + rows
            page = f"<html><meta charset=utf-8><head><title>Max Explorer</title><style>body{{font-family:sans-serif;background:#111;color:#eee}}.b{{background:#223;margin:8px;padding:8px;border-radius:8px}}</style></head><body><h1>Max Chain Explorer</h1><p>{msg}</p>{rows}</body></html>"
            self.send_response(200); self.send_header("Content-Type", "text/html"); self.end_headers(); self.wfile.write(page.encode())
    print(f"Explorer at http://localhost:{port}  (Ctrl+C to stop)")
    HTTPServer(("127.0.0.1", port), H).serve_forever()

USAGE = """Max chain (learning project - NOT real money)
  python max.py new-wallet NAME
  python max.py import-wallet NAME PRIVATEKEY
  python max.py export-wallet NAME FILE
  python max.py show-key NAME
  python max.py balance NAME
  python max.py send FROM_NAME TO_NAME_OR_ADDRESS AMOUNT [FEE]
  python max.py mine MINER_NAME
  python max.py chain | stats | validate | leaderboard
  python max.py explorer [PORT]
Network rules: MAX_TARGET, MAX_RETARGET, MAX_DIFFICULTY, MAX_HALVING. Data folder: MAX_DATA.
To join other players run the node app: python max_app.py
Passwords are asked for privately. For scripts you can set MAX_PASSWORD."""

def stats_text(d):
    s = stats(d); avg = f"{s['avg']:.1f}s" if s["avg"] is not None else "n/a"
    return (f"Height: {s['height']} | Difficulty now: {s['current']} | Next block: {s['next']}\n"
            f"Target: {s['target']}s per block | Recent average: {avg}\n"
            f"Next retarget at block #{s['next_retarget']} ({s['blocks_left']} blocks to go, checks every {s['every']})\n"
            f"Supply: {s['supply']:,} / {s['max_supply']:,} MAX | Reward now: {s['reward']} MAX | Next halving at block #{s['next_halving']} (every {s['halving_every']})\n"
            f"Mempool: {s['mempool']} waiting | Network id: {s['chain_id']}")

def ask_password(confirm=False):
    if os.environ.get("MAX_PASSWORD"): return os.environ["MAX_PASSWORD"]
    p = getpass.getpass("Wallet password: ")
    if confirm and getpass.getpass("Type it again: ") != p: raise MaxError("Passwords didn't match.")
    return p

def main(a):
    if not a: print(USAGE); return
    cmd = a[0]
    def need(n):
        if len(a) < n + 1: raise MaxError("Missing info.\n" + USAGE)
    if cmd == "new-wallet":
        need(1); print(f"Created wallet '{a[1]}' address: {new_wallet(a[1], ask_password(True))}")
    elif cmd == "import-wallet":
        need(2); print(f"Imported wallet '{a[1]}' address: {import_wallet(a[1], a[2], ask_password(True))}")
    elif cmd == "export-wallet":
        need(2); export_wallet(a[1], a[2]); print(f"Saved '{a[1]}' to {a[2]} (still password-locked)")
    elif cmd == "show-key":
        need(1); w = unlock(a[1], ask_password())
        print("!!! SECRET !!! Never share this key. Anyone who has it controls this wallet.")
        print(w["private"])
    elif cmd == "balance":
        need(1); w = load_wallet(a[1]); d = load()
        print(f"{a[1]} ({w['address'][:16]}...): {balance(d, w['address'], False)} MAX confirmed, {balance(d, w['address'])} incl. pending")
    elif cmd == "send":
        need(3); fee = a[4] if len(a) > 4 else 0
        tx = send(a[1], ask_password(), a[2], a[3], fee); print(f"Signed tx #{tx['nonce']}: {a[1]} -> {a[2]} {a[3]} MAX, fee {tx['fee']} (waiting in the mempool)")
    elif cmd == "mine":
        need(1); t0 = time.time(); b = mine(a[1])
        print(f"Mined block #{b['index']} in {time.time()-t0:.2f}s nonce={b['nonce']} hash={b['hash'][:20]}... ({len(b['txs'])-1} payments, +{b['txs'][-1]['amount']} MAX to {a[1]})")
    elif cmd == "stats":
        print(stats_text(load()))
    elif cmd == "chain":
        d = load()
        for b in d["chain"]:
            print(f"#{b['index']} diff={b['difficulty']} hash={b['hash'][:16]}... prev={b['prev'][:16]}... nonce={b['nonce']}")
            for t in b["txs"]:
                if "sender" in t: print(f"    {t['sender'][:10]} -> {t['to'][:10]} : {t['amount']} MAX" + (f" (fee {t['fee']})" if t.get("fee") else ""))
        print(stats_text(d))
    elif cmd == "validate":
        ok, msg = validate(load()); print(msg); sys.exit(0 if ok else 1)
    elif cmd == "leaderboard":
        print("=== MAX LEADERBOARD ===")
        print(f"{'Rank':<6}{'Name':<12}{'Address':<16}{'Balance':>10}{'Mined':>7}")
        for i, (n, ad, bal, m) in enumerate(leaderboard(load())):
            rank = MEDALS[i] if i < 3 else f"#{i+1}"
            print(f"{rank:<6}{n:<12}{ad[:12]+'...':<16}{str(bal)+' MAX':>10}{m:>7}")
    elif cmd == "explorer":
        explorer(int(a[1]) if len(a) > 1 else 8000)
    else: print(USAGE)

if __name__ == "__main__":
    try: sys.stdout.reconfigure(encoding="utf-8")
    except Exception: pass
    try: main(sys.argv[1:])
    except MaxError as e: print("Error:", e); sys.exit(1)
    except KeyboardInterrupt: pass
