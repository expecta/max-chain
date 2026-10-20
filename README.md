# Max Chain - your own toy blockchain (coin: MAX)

> **This is a learning project.** MAX coins are NOT real money, can't be bought or sold, and only exist on your own computer.

## Setup on Windows
1. Go to https://www.python.org/downloads/ and download Python 3.
2. Run the installer and **tick "Add python.exe to PATH"** at the bottom, then click Install Now.
3. Unzip `max-chain.zip` somewhere, like your Desktop.
4. **Desktop app (easiest):** double-click `run_gui.bat`. A MAX window opens with tabs for Wallets, Send, Mine, Blockchain and Leaderboard.
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
| `send FROM TO AMOUNT` | Signs a payment and puts it in the waiting list |
| `mine NAME` | Solves a puzzle to make a new block, gets 50 MAX |
| `chain` | Prints all blocks |
| `stats` | Shows difficulty, average block time and next retarget |
| `validate` | Checks nobody cheated |
| `leaderboard` | Ranks everyone by MAX, with 🥇🥈🥉 medals for the top 3 and how many blocks they mined |
| `explorer` | Local web page to look at the chain |

Run `python max.py stats` to see the difficulty and when it changes next. Want to start over? Delete `chain.json` and the `wallets` folder.

## ⚙️ Changing the speed rules (optional)
These are only used when a **brand-new chain** is made (they're saved in the first block):
`set MAX_TARGET=30` (seconds per block), `set MAX_RETARGET=10` (check every N blocks), `set MAX_DIFFICULTY=4` (starting zeros). In PowerShell use `$env:MAX_TARGET=30`.

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
- **Mining is a guessing game.** The computer keeps trying numbers (the "nonce") until the fingerprint starts with a few zeros. That takes work, and the winner gets 50 MAX as a prize.
- **The puzzle gets harder or easier by itself.** Max wants one block about every 30 seconds. Every 10 blocks it checks how fast people were. Way too fast (less than half the time)? It adds one more zero, so it's harder. Way too slow (more than double)? It takes a zero away. It never goes below 3 or above 7 zeros. Each block writes down its difficulty, and `validate` checks that every block followed the rule, so nobody can cheat by making it easy.
- **The first page is the genesis block.** It starts the whole notebook.
- **Wallets have a secret key and a public address.** Your address is like your name tag; your secret key is like your signature pen. Never share the secret key (it's in the `wallets` folder).
- **Signed transactions:** when you send MAX, your secret key signs it. Anyone can check the signature with your address, but nobody can fake it. You also can't send more than you have.
