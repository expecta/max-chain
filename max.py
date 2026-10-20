"""Max - a tiny learning blockchain with the MAX coin. NOT a real cryptocurrency."""
import hashlib, json, os, sys, time
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey, Ed25519PublicKey
from cryptography.hazmat.primitives import serialization as S

HERE = os.path.dirname(os.path.abspath(__file__))
CHAIN_FILE = os.path.join(HERE, "chain.json")
WALLET_DIR = os.path.join(HERE, "wallets")
DIFFICULTY = int(os.environ.get("MAX_DIFFICULTY", "4"))
REWARD = 50

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
def tx_body(tx): return json.dumps({k: tx[k] for k in ("sender", "to", "amount", "time")}, sort_keys=True)

def sign_tx(wallet, to, amount):
    tx = {"sender": wallet["address"], "to": to, "amount": amount, "time": time.time()}
    key = Ed25519PrivateKey.from_private_bytes(bytes.fromhex(wallet["private"]))
    tx["signature"] = key.sign(tx_body(tx).encode()).hex()
    return tx

def verify_tx(tx):
    if tx["sender"] == "REWARD": return True
    try:
        Ed25519PublicKey.from_public_bytes(bytes.fromhex(tx["sender"])).verify(
            bytes.fromhex(tx["signature"]), tx_body(tx).encode()); return True
    except Exception: return False

# ---------- blocks / chain ----------
def block_hash(b): return sha(json.dumps({k: b[k] for k in ("index","time","txs","prev","nonce")}, sort_keys=True))

def mine_block(index, txs, prev):
    b = {"index": index, "time": time.time(), "txs": txs, "prev": prev, "nonce": 0}
    target = "0" * DIFFICULTY
    while True:
        h = block_hash(b)
        if h.startswith(target): b["hash"] = h; b["difficulty"] = DIFFICULTY; return b
        b["nonce"] += 1

def load():
    if os.path.exists(CHAIN_FILE): return json.load(open(CHAIN_FILE))
    data = {"chain": [mine_block(0, [], "0" * 64)], "pending": []}  # genesis block
    save(data); return data

def save(d): json.dump(d, open(CHAIN_FILE, "w"), indent=2)

def balance(d, addr, include_pending=True):
    bal = 0
    txs = [t for b in d["chain"] for t in b["txs"]] + (d["pending"] if include_pending else [])
    for t in txs:
        if t["to"] == addr: bal += t["amount"]
        if t["sender"] == addr: bal -= t["amount"]
    return bal

def validate(d):
    seen = {}
    for i, b in enumerate(d["chain"]):
        if block_hash(b) != b["hash"]: return False, f"block {i}: hash doesn't match contents (tampered!)"
        if not b["hash"].startswith("0" * b["difficulty"]): return False, f"block {i}: not enough proof-of-work"
        if i and b["prev"] != d["chain"][i-1]["hash"]: return False, f"block {i}: broken link to previous block"
        rewards = 0
        for t in b["txs"]:
            if not verify_tx(t): return False, f"block {i}: bad signature"
            if t["sender"] == "REWARD": rewards += t["amount"]
            else:
                if seen.get(t["sender"], 0) < t["amount"]: return False, f"block {i}: overspend"
                seen[t["sender"]] -= t["amount"]
            seen[t["to"]] = seen.get(t["to"], 0) + t["amount"]
        if rewards > REWARD: return False, f"block {i}: too much reward"
    return True, f"Chain is VALID ({len(d['chain'])} blocks)"

def send(from_name, password, to, amount):
    try: amount = int(amount)
    except Exception: raise MaxError("Amount must be a whole number.")
    if amount <= 0: raise MaxError("Amount must be more than 0.")
    w = unlock(from_name, password); to = resolve(to.strip()); d = load()
    if len(to) != 64: raise MaxError("Send to a wallet name or a 64-character address.")
    have = balance(d, w["address"])
    if have < amount: raise MaxError(f"Not enough MAX! {from_name} has {have}.")
    tx = sign_tx(w, to, amount); d["pending"].append(tx); save(d); return tx

def mine(miner_name):
    w = load_wallet(miner_name); d = load()
    txs = [t for t in d["pending"] if verify_tx(t)] + [{"sender": "REWARD", "to": w["address"], "amount": REWARD, "time": time.time(), "signature": ""}]
    b = mine_block(len(d["chain"]), txs, d["chain"][-1]["hash"])
    d["chain"].append(b); d["pending"] = []; save(d); return b

# ---------- leaderboard ----------
MEDALS = ["\U0001F947", "\U0001F948", "\U0001F949"]

def names():
    return {w["address"]: w["name"] for w in list_wallets()}

def leaderboard(d):
    addrs, mined = set(names()), {}
    for b in d["chain"]:
        for t in b["txs"]:
            addrs.add(t["to"])
            if t["sender"] == "REWARD": mined[t["to"]] = mined.get(t["to"], 0) + 1
            else: addrs.add(t["sender"])
    nm = names()
    rows = [(nm.get(a, "?"), a, balance(d, a, False), mined.get(a, 0)) for a in addrs]
    rows.sort(key=lambda r: (-r[2], -r[3], r[0]))
    return rows

# ---------- explorer ----------
def explorer(port=8000):
    from http.server import HTTPServer, BaseHTTPRequestHandler
    import html
    class H(BaseHTTPRequestHandler):
        def do_GET(self):
            d = load(); ok, msg = validate(d)
            rows = "".join(f"<div class=b><b>Block #{b['index']}</b> nonce {b['nonce']}<br><small>hash {b['hash']}<br>prev {b['prev']}</small><ul>" +
                "".join(f"<li>{html.escape(t['sender'][:12])} &rarr; {html.escape(t['to'][:12])}: {t['amount']} MAX</li>" for t in b["txs"]) + "</ul></div>"
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
  python max.py send FROM_NAME TO_NAME_OR_ADDRESS AMOUNT
  python max.py mine MINER_NAME
  python max.py chain | validate | leaderboard
  python max.py explorer [PORT]
Passwords are asked for privately. For scripts you can set MAX_PASSWORD."""

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
        need(3); send(a[1], ask_password(), a[2], a[3]); print(f"Signed tx: {a[1]} -> {a[2]} {a[3]} MAX (waiting to be mined)")
    elif cmd == "mine":
        need(1); t0 = time.time(); b = mine(a[1])
        print(f"Mined block #{b['index']} in {time.time()-t0:.2f}s nonce={b['nonce']} hash={b['hash'][:20]}... ({len(b['txs'])} txs, +{REWARD} MAX to {a[1]})")
    elif cmd == "chain":
        for b in load()["chain"]:
            print(f"#{b['index']} hash={b['hash'][:16]}... prev={b['prev'][:16]}... nonce={b['nonce']}")
            for t in b["txs"]: print(f"    {t['sender'][:10]} -> {t['to'][:10]} : {t['amount']} MAX")
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
