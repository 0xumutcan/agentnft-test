# Skill: Solve zkML Puzzle #001 — Mint NFT on Abstract L2

## Goal
Read encrypted clues from the Abstract L2 blockchain, deduce the correct answer, generate a zero-knowledge ML proof, and mint an ERC-721 NFT. The task is complete when `mintWithProof()` is confirmed on-chain.

You need: a wallet with a small amount of ETH on Abstract L2 testnet (for gas). No other funds required.

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
| Puzzle ID | `0x0000000000000000000000000000000000000000000000000000000000000001` |

---

## Setup

Clone the repo (contains pre-built ML artifacts and proving keys):
```bash
git clone https://github.com/0xumutcan/agentnft-test
cd agentnft
```

Install Python dependencies:
```bash
pip install web3 eth-abi eth-account sentence-transformers torch scikit-learn numpy ezkl==9.1.0 python-dotenv
```

Set your wallet private key as an environment variable:
```bash
export PRIVATE_KEY=0xYOUR_PRIVATE_KEY
```

---

## Step 1 — Read On-Chain Clues

```python
from web3 import Web3
from web3.middleware import ExtraDataToPOAMiddleware
from eth_abi import decode

w3 = Web3(Web3.HTTPProvider("https://api.testnet.abs.xyz"))
w3.middleware_onion.inject(ExtraDataToPOAMiddleware, layer=0)

REGISTRY  = "0x6f06409866145eE2565d9262a774375c249DAe40"
PUZZLE_ID = bytes.fromhex("0000000000000000000000000000000000000000000000000000000000000001")

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

for ev in sorted(events, key=lambda e: e["args"]["index"]):
    ctype = ev["args"]["clueType"]
    raw   = ev["args"]["data"]
    if ctype in (0, 1, 2, 3):
        (text,) = decode(["string"], raw)
        print(f"[clue {ev['args']['index']}] {text}")
```

You will find 2 free clues. The clues are in Turkish. Read them carefully and deduce the answer — it is a single English word (an animal).

---

## Step 2 — Generate ZK Proof

```python
import sys, os
sys.path.insert(0, "agent")
sys.path.insert(0, "ml")

from prover import prove

PUZZLE_ID = "0x0000000000000000000000000000000000000000000000000000000000000001"
answer    = "your answer"   # replace with what you deduced from the clues

proof_bytes, public_inputs = prove(PUZZLE_ID, answer)
print(f"Proof size: {len(proof_bytes)} bytes")
print(f"Public inputs: {public_inputs}")
```

This encodes your answer as a semantic embedding, runs it through a PCA projection, and generates a Halo2 ZK proof via EZKL. All pre-built artifacts are in `ml/artifacts/`. If the proof generation fails, try a semantically closer word or phrase.

---

## Step 3 — Mint

> **STOP before running this step.**
> Ask the user for the following values. Do not proceed until you have them:
> - `PRIVATE_KEY` — the signer private key for the wallet that will mint
> - `AGW_ADDRESS` — the Abstract Global Wallet address (only if using AGW; leave unset for plain EOA)

The minter supports two modes. Use whichever matches your wallet setup.

### Option A — Plain EOA wallet (standard private key)

Set environment variable:
```bash
export PRIVATE_KEY=0xYOUR_PRIVATE_KEY
```

```python
import os, sys
sys.path.insert(0, "agent")
from minter import Minter

minter  = Minter()
tx_hash = minter.mint(
    "0x0000000000000000000000000000000000000000000000000000000000000001",
    proof_bytes,    # from Step 2
    public_inputs,  # from Step 2
)
print(f"https://sepolia.abscan.org/tx/{tx_hash}")
```

### Option B — Abstract Global Wallet (AGW signer private key)

AGW uses a **signer private key** which is a standard EOA private key registered in your AGW smart contract. Transactions are sent *from* the AGW smart wallet address but *signed by* the signer private key using ZKsync type-113 EIP-712 format.

```bash
pip install zksync2
export PRIVATE_KEY=0xYOUR_SIGNER_PRIVATE_KEY    # the registered signer private key private key
export AGW_ADDRESS=0xYOUR_AGW_WALLET     # your Abstract Global Wallet address
```

```python
import os, sys
sys.path.insert(0, "agent")
from minter import Minter   # auto-detects AGW mode when AGW_ADDRESS is set

minter  = Minter()
tx_hash = minter.mint(
    "0x0000000000000000000000000000000000000000000000000000000000000001",
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
| AGW tx rejected | Session key may not be registered in your AGW contract — register it first via the AGW JS SDK |
