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

```python
import os
from web3 import Web3
from web3.middleware import ExtraDataToPOAMiddleware
from eth_account import Account

w3 = Web3(Web3.HTTPProvider("https://api.testnet.abs.xyz"))
w3.middleware_onion.inject(ExtraDataToPOAMiddleware, layer=0)

account = Account.from_key(os.environ["PRIVATE_KEY"])

NFT_ABI = [
    {"inputs": [
        {"name": "puzzleId",  "type": "bytes32"},
        {"name": "proof",     "type": "bytes"},
        {"name": "instances", "type": "uint256[]"}
    ], "name": "mintWithProof", "outputs": [], "stateMutability": "nonpayable", "type": "function"},
    {"inputs": [
        {"name": "puzzleId", "type": "bytes32"},
        {"name": "solver",   "type": "address"}
    ], "name": "claimed", "outputs": [{"name": "", "type": "bool"}], "stateMutability": "view", "type": "function"}
]

nft = w3.eth.contract(address="0x36B7a190E236625e185c707bcA192D053084143E", abi=NFT_ABI)
puzzle_id_bytes = bytes.fromhex("0000000000000000000000000000000000000000000000000000000000000001")

if nft.functions.claimed(puzzle_id_bytes, account.address).call():
    print("Already claimed.")
else:
    tx = nft.functions.mintWithProof(
        puzzle_id_bytes, proof_bytes, public_inputs
    ).build_transaction({
        "from":    account.address,
        "nonce":   w3.eth.get_transaction_count(account.address),
        "gas":     900_000,
        "chainId": 11124,
    })
    signed  = account.sign_transaction(tx)
    tx_hash = w3.eth.send_raw_transaction(signed.raw_transaction)
    receipt = w3.eth.wait_for_transaction_receipt(tx_hash, timeout=120)

    if receipt["status"] == 1:
        print(f"NFT minted! https://sepolia.abscan.org/tx/{tx_hash.hex()}")
    else:
        print(f"TX reverted — wrong answer? Try a different word.")
```

---

## Troubleshooting

| Symptom | Fix |
|---|---|
| TX reverted | Answer embedding score too low — try a closer synonym |
| `gen_witness failed` | Check `ml/artifacts/` has all files; re-run `python ml/ezkl_pipeline.py` |
| Not enough gas | Get testnet ETH from `https://faucet.abs.xyz` |
| Already claimed | Your wallet already minted this puzzle |
