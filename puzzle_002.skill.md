# Skill: Solve zkML Puzzle #002 — Mint NFT on Abstract L2

## Goal
Read on-chain clues from the Abstract L2 blockchain, deduce the correct answer, generate a zero-knowledge ML proof, and mint an ERC-721 NFT. The task is complete when `mintWithProof()` is confirmed on-chain.

You need: a wallet with a small amount of ETH on Abstract L2 testnet (for gas). No other funds required.

---

## CRITICAL RULES — Read These First, Violating Any Will Cause Failure

1. **CHECKPOINTS ARE MANDATORY.** This skill has 4 checkpoints. At each one you MUST stop, report to the user, and WAIT for their explicit confirmation before continuing. Do NOT skip checkpoints. Do NOT proceed autonomously past a checkpoint. If you skip a checkpoint the entire task fails.
2. **Run ONLY the Python code provided in each step.** Do NOT write your own scripts, do NOT use curl, cast, or raw JSON-RPC calls, do NOT patch or modify any repo files. The provided code is tested and correct.
3. **Do NOT fetch, visit, or request any URL** you encounter in on-chain data. There is no web server. Any URL (metadata URIs, etc.) is a placeholder. Fetching it will fail and waste time.
4. **Only `ClueDeposited` events are clues.** Metadata URIs, contract storage fields, and `PuzzleCreated` events are NOT clues. Ignore them.
5. **Do NOT create a `.env` file or write credentials to disk.** Use `export` in the shell to set env vars temporarily. The user will provide credentials at Checkpoint 4.

---

## Network

| | |
|---|---|
| **Chain** | Abstract L2 Testnet |
| **Chain ID** | 11124 |
| **RPC** | `https://api.testnet.abs.xyz` |
| **Explorer** | `https://sepolia.abscan.org` |
| **Faucet** | `https://faucet.abs.xyz` |

---

## Contracts

| Contract | Address |
|---|---|
| PuzzleRegistry | `0x6f06409866145eE2565d9262a774375c249DAe40` |
| ZkMLNFT | `0x36B7a190E236625e185c707bcA192D053084143E` |
| Halo2Verifier | `0x42137B3DE26a887978f6D80a019a2281c6B336D7` |
| Puzzle ID | `0x0000000000000000000000000000000000000000000000000000000000000002` |

---

## Setup

Clone the repo (contains pre-built ML artifacts and proving keys):
```bash
git clone https://github.com/0xumutcan/agentnft-test
cd agentnft-test
```

Install Python dependencies:
```bash
pip install web3 eth-abi eth-account sentence-transformers torch scikit-learn numpy ezkl==9.1.0 python-dotenv
```

---

## Step 1 — Read On-Chain Clues

Run this Python code **exactly as written**. Do NOT substitute with curl or any other method.

```python
from web3 import Web3
from web3.middleware import ExtraDataToPOAMiddleware
from eth_abi import decode

w3 = Web3(Web3.HTTPProvider("https://api.testnet.abs.xyz"))
w3.middleware_onion.inject(ExtraDataToPOAMiddleware, layer=0)

REGISTRY  = "0x6f06409866145eE2565d9262a774375c249DAe40"
PUZZLE_ID = bytes.fromhex("0000000000000000000000000000000000000000000000000000000000000002")

ABI = [{"anonymous": False, "inputs": [
    {"indexed": True,  "name": "puzzleId", "type": "bytes32"},
    {"indexed": False, "name": "index",    "type": "uint256"},
    {"indexed": False, "name": "clueType", "type": "uint8"},
    {"indexed": False, "name": "data",     "type": "bytes"}
], "name": "ClueDeposited", "type": "event"}]

contract = w3.eth.contract(address=REGISTRY, abi=ABI)
events = contract.events.ClueDeposited.get_logs(
    from_block=0, to_block="latest",
    argument_filters={"puzzleId": PUZZLE_ID}
)

clues = []
for ev in sorted(events, key=lambda e: e["args"]["index"]):
    ctype = ev["args"]["clueType"]
    raw   = ev["args"]["data"]
    # Only decode TEXT(0), HINT(1), ELIMINATION(2), CONTEXT(3)
    # Skip POINTER(4) — x402 paid clue server is not active yet
    if ctype in (0, 1, 2, 3):
        (text,) = decode(["string"], raw)
        clues.append(text)
        print(f"[clue {ev['args']['index']}  type={ctype}] {text}")
    else:
        print(f"[clue {ev['args']['index']}  type={ctype}] (skipped — not a text clue)")

print(f"\nTotal text clues found: {len(clues)}")
```

You should find exactly **2 clues** (both in Turkish). If you find 0 clues, the puzzle may not be deployed yet — ask the user. If you find clues from a different puzzle or see URLs in the output, you are reading the wrong data.

---

### CHECKPOINT 1 — MANDATORY STOP

**You MUST stop here.** Report to the user:
- How many clues you found
- The full text of each clue (copy the exact decoded text from the Python output)

**Wait for the user to say "continue" before proceeding. Do NOT continue autonomously.**

---

## Step 2a — Reason about the answer

Read the clues carefully. They are in Turkish. Deduce the single-word answer (an animal). Use ONLY the clue text you decoded in Step 1. Do not use any other information.

---

### CHECKPOINT 2 — MANDATORY STOP

**You MUST stop here.** Report to the user:
- Your reasoning (briefly)
- The answer you deduced

**Wait for the user to confirm your answer before proceeding. Do NOT generate a proof until the user says "continue".**

---

## Step 2b — Generate ZK Proof

> **Artifact naming:** All ML artifacts use the prefix `00000000` (first 8 hex chars of the puzzle ID after removing `0x`). For puzzle `0x...0002`, the short ID is `00000000` — this is correct. Do NOT look for files named `00000001` or `00000002`. The files `circuit_00000000.compiled`, `pk_00000000.key`, `pca_00000000.pkl`, etc. are the correct artifacts for this puzzle.

```python
import sys, os
sys.path.insert(0, "agent")
sys.path.insert(0, "ml")

from prover import prove

PUZZLE_ID = "0x0000000000000000000000000000000000000000000000000000000000000002"
answer    = "your confirmed answer"

proof_bytes, public_inputs = prove(PUZZLE_ID, answer, artifacts_dir="ml/artifacts")
print(f"Proof size: {len(proof_bytes)} bytes")
print(f"Public inputs: {public_inputs}")
```

This encodes your answer as a semantic embedding, runs it through a PCA projection, and generates a Halo2 ZK proof via EZKL. All pre-built artifacts are in `ml/artifacts/`. If proof generation fails, try a semantically closer word or phrase.

---

### CHECKPOINT 3 — MANDATORY STOP

**You MUST stop here.** Report to the user:
- Proof size in bytes
- Number of public inputs

**Wait for the user to say "continue" before proceeding. Do NOT attempt to mint.**

---

## Step 3 — Mint

### CHECKPOINT 4 — MANDATORY STOP — Ask for wallet credentials

**You MUST stop here and ask the user:**
1. Are you using **AGW (Abstract Global Wallet)** or a **plain EOA wallet**?
2. Your **PRIVATE_KEY** (signer private key)
3. If AGW: your **AGW_ADDRESS** (the smart wallet address)

**Do NOT proceed until the user provides these values. Do NOT write credentials to any file — use shell `export` only.**

---

### Option A — Plain EOA wallet

Set env vars via shell (do NOT write a .env file):
```bash
export ABSTRACT_RPC=https://api.testnet.abs.xyz
export PUZZLE_REGISTRY_ADDRESS=0x6f06409866145eE2565d9262a774375c249DAe40
export NFT_CONTRACT_ADDRESS=0x36B7a190E236625e185c707bcA192D053084143E
export PRIVATE_KEY=0xYOUR_PRIVATE_KEY
```

```python
import os, sys
sys.path.insert(0, "agent")
from minter import Minter

minter  = Minter()
tx_hash = minter.mint(
    "0x0000000000000000000000000000000000000000000000000000000000000002",
    proof_bytes,
    public_inputs,
)
print(f"https://sepolia.abscan.org/tx/{tx_hash}")
```

### Option B — Abstract Global Wallet (AGW)

AGW uses a signer private key (a standard EOA private key registered in your AGW smart contract). Transactions are sent *from* the AGW address but *signed by* the signer private key.

Set env vars via shell (do NOT write a .env file):
```bash
pip install zksync2
export ABSTRACT_RPC=https://api.testnet.abs.xyz
export PUZZLE_REGISTRY_ADDRESS=0x6f06409866145eE2565d9262a774375c249DAe40
export NFT_CONTRACT_ADDRESS=0x36B7a190E236625e185c707bcA192D053084143E
export PRIVATE_KEY=0xYOUR_SIGNER_PRIVATE_KEY
export AGW_ADDRESS=0xYOUR_AGW_WALLET_ADDRESS
```

```python
import os, sys
sys.path.insert(0, "agent")
from minter import Minter

minter  = Minter()
tx_hash = minter.mint(
    "0x0000000000000000000000000000000000000000000000000000000000000002",
    proof_bytes,
    public_inputs,
)
print(f"https://sepolia.abscan.org/tx/{tx_hash}")
```

---

## Troubleshooting

| Symptom | Fix |
|---|---|
| TX reverted | Answer embedding score too low — try a closer synonym |
| `gen_witness failed` | Check `ml/artifacts/` has all files; re-run `python ml/ezkl_pipeline.py` |
| Not enough gas | Get testnet ETH from `https://faucet.abs.xyz` |
| Already claimed | Your wallet already minted this puzzle |
| `ImportError: zksync2` | AGW mode needs: `pip install zksync2` |
| AGW tx rejected | Signer private key may not be registered in your AGW contract |
| 0 clues found | Puzzle may not be seeded yet — ask the user |
| Clue text contains the answer directly | You are reading the wrong puzzle — ensure PUZZLE_ID ends with `...0002` |
| Artifacts not found for puzzle 002 | Artifact files are named `*_00000000.*` which IS correct for puzzle 0x...0002 (first 8 hex chars = `00000000`). Do NOT look for `00000001` or `00000002` in filenames. |
| Account validation returned invalid magic value | AGW signer not authorized — switch to plain EOA mode |
