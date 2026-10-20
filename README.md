# Max Chain - your own toy blockchain (coin: MAX)

> **This is a learning project.** MAX coins are NOT real money, can't be bought or sold, and only exist on your own computer.

## Setup on Windows
1. Go to https://www.python.org/downloads/ and download Python 3.
2. Run the installer and **tick "Add python.exe to PATH"** at the bottom, then click Install Now.
3. Unzip `max-chain.zip` somewhere, like your Desktop.
4. **MAX app (easiest, new!):** double-click `run_app.bat`. Your web browser opens the MAX app at `http://127.0.0.1:8765`, with Dashboard, Wallets, Send, Mine, Explorer, Leaderboard and Stats pages. It runs only on your computer and needs no internet. Keep the black window open while you play; close it to stop the app.
   - Prefer the old simple window? Double-click `run_gui.bat` (classic app, `max_gui_classic.py`).
5. **Demo:** double-click `run_demo.bat`. It runs a quick demo using the practice password `demo1234` (only for the demo!).
6. **Do it yourself:** open PowerShell or Command Prompt and type:
   ```
   cd Desktop\max-chain
   python -m pip install -r requirements.txt
   python max.py new-wallet alice
   python max.py new-wallet bob
   python max.py show-key alice
   python max.py mine alice
   python max.py send alice bob 20
   python max.py mine bob
   python max.py balance bob
   python max.py validate
   python max.py leaderboard
   python max.py explorer
   ```
   If `python` doesn't work, use `py` instead (e.g. `py max.py mine alice`).
   The explorer opens a web page at http://localhost:8000 showing the leaderboard and every block.

## Commands
| Command | What it does |
|---|---|
| `new-wallet NAME` | Makes a wallet (a secret key + an address) |
| `show-key NAME` | Shows your SECRET private key (asks your password) |
| `import-wallet NAME KEY` | Brings back a wallet from its private key |
| `export-wallet NAME FILE` | Saves a backup copy (still password-locked) |
| `balance NAME` | Shows how many MAX it has |
| `send FROM TO AMOUNT [FEE]` | Signs a payment (optional fee for the miner) and puts it in the mempool |
| `mine NAME` | Solves a puzzle to make a new block and earns the reward plus fees. The command line mines locally; use the app to share blocks with friends |
| `chain` | Prints all blocks |
| `stats` | Shows difficulty, average block time and next retarget |
| `validate` | Checks nobody cheated |
| `leaderboard` | Ranks everyone by MAX, with 🥇🥈🥉 medals for the top 3 and how many blocks they mined |
| `explorer` | Local web page to look at the chain |

Run `python max.py stats` to see the difficulty and when it changes next. Want to start over? Delete `chain.json` and the `wallets` folder.

## 🖥️ The MAX app
- **Dashboard:** total MAX mined, block height, difficulty, average block time, next speed check, recent blocks and top miners.
- **Wallets:** wallet cards with balances. Copy your address, make or import wallets, and see your private key (only after typing your password).
- **Send:** pick a wallet, type a name or address and an amount, and enter your password.
- **Mine:** press the big button. Turn on **Auto-mine** to keep mining block after block. Press it again to stop.
- **Explorer:** click a block to see its payments. Press **Validate** to check nobody cheated.
- **Leaderboard** with 🥇🥈🥉 medals, and **Stats** explaining the rules.
- Your password is only used for that one action. It's never saved or written to a log, and the app only listens on your own computer (`127.0.0.1`).
- Port busy? Run `set MAX_PORT=8800` first, then `python max_app.py`.

## 🌐 Max is a real network now (v2)
Every copy of the MAX app is a **node**: a computer that keeps its own copy of the chain and talks to other nodes.
- **Payments travel.** When you send MAX, your node tells its friends (peers), and they pass it on.
- **The mempool is the waiting room.** Signed payments wait there until a miner puts them in a block. See it on the **Mempool** page.
- **Fees:** you can add a small tip (fee) to a payment. The miner who puts it in a block keeps the fee, so payments with bigger fees go first.
- **No copy-paste cheating (nonces):** each payment from a wallet gets the next number (1, 2, 3...). A payment can only be used once, so nobody can "replay" it to make you pay twice.
- **New blocks travel too.** When someone mines a block, every node checks it. Fake or greedy blocks are thrown away.
- **Longest chain wins.** If two people mine at the same time the chain splits for a bit (a "fork"). The side with the most work wins, and payments from the losing side go back to the mempool.
- **Only 21,000,000 MAX can ever exist.** The reward starts at 50 MAX per block and **halves** (50 → 25 → 12 → 6...) every 210,000 blocks. For a quick demo, start every node with the same smaller number, e.g. `set MAX_HALVING=210`.
- **Upgrading from v1?** Old chains don't work. Delete `chain.json` and start fresh. Your wallets still work.

### 👫 Play with a friend on the same Wi-Fi
1. **Both** of you unzip Max and use the **same settings** (just use the defaults).
2. On the friend who will **host**: open PowerShell in the folder and run
   `python max_app.py --public`
   Windows may ask "Allow access?" Choose **Private networks only**.
3. The host finds their computer's address: run `ipconfig` and look for **IPv4 Address**, e.g. `192.168.1.20`.
4. The other player starts the app normally (`run_app.bat`), goes to **Network**, types `192.168.1.20:8766` and clicks **Add peer**.
5. You'll both see the same blocks. Send each other MAX and race to mine!

### 🌍 Playing over the internet (ask a parent first!)
This means opening a door on your home router (**port forwarding**), so **only do it with a parent**.
- The host runs `python max_app.py --public --advertise YOUR_PUBLIC_IP:8766` and forwards TCP port **8766** on the router to their computer.
- **Risks:** anyone on the internet can then reach that port and send your node junk. Max only exposes the node part (blocks, payments, peers). Your wallets and the app page stay on `127.0.0.1` and never open to the internet. Still, it's best to forward the port only while you play and close it afterwards. Never forward port 8765 (the app).
- Safer option: use a private network app like Tailscale or ZeroTier that your parent sets up, and add your friend by their private address.

### Node options
| Option | What it does |
|---|---|
| `--public` | Lets other computers connect to your node (otherwise only your own PC can) |
| `--p2p-port 8766` | Node port for other players |
| `--port 8765` | App page port (always only on your own computer) |
| `--peer host:port` | Connect to a peer at start (you can repeat it) |
| `--data folder` | Use a different folder. Lets you run 2 or 3 nodes on one PC for testing |

Try 3 nodes on one PC:
```
python max_app.py --data node1 --port 9101 --p2p-port 9201
python max_app.py --data node2 --port 9102 --p2p-port 9202 --peer 127.0.0.1:9201
python max_app.py --data node3 --port 9103 --p2p-port 9203 --peer 127.0.0.1:9202
```

## ⚙️ Changing the speed rules (optional)
These are network rules saved in the first block. **Everyone you play with must use the same ones**, or your nodes will say "different network":
`set MAX_TARGET=30` (seconds per block), `set MAX_RETARGET=10` (check every N blocks), `set MAX_DIFFICULTY=4` (starting zeros), `set MAX_HALVING=210000` (blocks between halvings). In PowerShell use `$env:MAX_TARGET=30`.

**Upgrading from v1.0?** Old `chain.json` files don't work with v1.1. Delete `chain.json` to start a fresh chain. Your wallets keep working.

## 🔒 Passwords and your secret key
- Every wallet is **locked with a password** you pick. You type it when you send MAX or look at your key. Mining doesn't need it.
- The password scrambles (encrypts) your private key inside the `wallets` folder, so nobody can read it from the file.
- **Your private key is the real key to your wallet. NEVER share it with anyone,** not friends, not "helpers", not anyone online. Anybody who has it can take everything in that wallet.
- Forgot your password? Then the wallet can't be unlocked. Write your private key on paper and keep it somewhere safe, then use `import-wallet` to get the wallet back.
- If you type the wrong password you'll just see "Wrong password". Try again.
- For scripts only, you can set the password with `set MAX_PASSWORD=...`.

## How it works (simple version)
- **Blocks are pages in a notebook.** Each page lists payments.
- **Hashes are fingerprints.** Every page gets a fingerprint made from what's written on it. Change one letter and the fingerprint totally changes.
- **Chain = each page writes down the fingerprint of the page before it.** So if someone changes an old page, all the links after it break, and `validate` catches it.
- **Mining is a guessing game.** The computer keeps trying numbers (the "nonce") until the fingerprint starts with a few zeros. That takes work, and the winner gets the block reward (50 MAX at first, halving over time) plus the fees.
- **The puzzle gets harder or easier by itself.** Max wants one block about every 30 seconds. Every 10 blocks it checks how fast people were. Way too fast (less than half the time)? It adds one more zero, so it's harder. Way too slow (more than double)? It takes a zero away. It never goes below 3 or above 7 zeros. Each block writes down its difficulty, and `validate` checks that every block followed the rule, so nobody can cheat by making it easy.
- **The first page is the genesis block.** It starts the whole notebook.
- **Wallets have a secret key and a public address.** Your address is like your name tag; your secret key is like your signature pen. Never share the secret key (it's in the `wallets` folder).
- **Signed transactions:** when you send MAX, your secret key signs it. Anyone can check the signature with your address, but nobody can fake it. You also can't send more than you have.
