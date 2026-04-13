"""
minter.py — Sends mintWithProof() transaction to ZkMLNFT on Abstract L2.

Supports two signing modes:
  1. EOA mode  : standard private key, web3.py (default)
  2. AGW mode  : Abstract Global Wallet signer private key, ZKsync type-113 tx

Set env vars:
  PRIVATE_KEY      = 0x...   (signer private key or plain EOA key)
  AGW_ADDRESS      = 0x...   (only for AGW mode — the smart wallet address)

If AGW_ADDRESS is set, AGW mode is used automatically.
"""

import json, os
from web3 import Web3
from web3.middleware import ExtraDataToPOAMiddleware
from eth_account import Account

from config import ABSTRACT_RPC, PRIVATE_KEY, NFT_CONTRACT_ADDR

NFT_ABI = json.loads("""[
  {
    "inputs": [
      {"name": "puzzleId",  "type": "bytes32"},
      {"name": "proof",     "type": "bytes"},
      {"name": "instances", "type": "uint256[]"}
    ],
    "name": "mintWithProof",
    "outputs": [],
    "stateMutability": "nonpayable",
    "type": "function"
  },
  {
    "inputs": [
      {"name": "puzzleId", "type": "bytes32"},
      {"name": "solver",   "type": "address"}
    ],
    "name": "claimed",
    "outputs": [{"name": "", "type": "bool"}],
    "stateMutability": "view",
    "type": "function"
  },
  {
    "anonymous": false,
    "inputs": [
      {"indexed": true, "name": "puzzleId", "type": "bytes32"},
      {"indexed": true, "name": "solver",   "type": "address"},
      {"indexed": false,"name": "tokenId",  "type": "uint256"}
    ],
    "name": "PuzzleSolved",
    "type": "event"
  }
]""")

CHAIN_ID = 11124


class Minter:
    def __init__(self):
        self.w3          = Web3(Web3.HTTPProvider(ABSTRACT_RPC))
        self.w3.middleware_onion.inject(ExtraDataToPOAMiddleware, layer=0)
        self.signer_key = Account.from_key(PRIVATE_KEY)
        self.agw_address = os.environ.get("AGW_ADDRESS")   # optional
        # sender = AGW smart wallet (if set) else plain EOA
        self.sender      = Web3.to_checksum_address(self.agw_address) \
                           if self.agw_address else self.signer_key.address
        self.nft         = self.w3.eth.contract(
            address=Web3.to_checksum_address(NFT_CONTRACT_ADDR),
            abi=NFT_ABI,
        )
        if self.agw_address:
            print(f"[Minter] AGW mode  — wallet: {self.sender}")
            print(f"[Minter]             signer: {self.signer_key.address}")
        else:
            print(f"[Minter] EOA mode  — address: {self.sender}")

    # ── public ────────────────────────────────────────────────────────────────

    def already_claimed(self, puzzle_id_hex: str) -> bool:
        puzzle_id_bytes = bytes.fromhex(puzzle_id_hex.replace("0x", ""))
        return self.nft.functions.claimed(puzzle_id_bytes, self.sender).call()

    def mint(self, puzzle_id_hex: str, proof_bytes: bytes, public_inputs: list[int]) -> str:
        puzzle_id_bytes = bytes.fromhex(puzzle_id_hex.replace("0x", ""))
        print(f"[Minter] mintWithProof | proof={len(proof_bytes)}B | inputs={len(public_inputs)}")

        if self.agw_address:
            return self._mint_agw(puzzle_id_bytes, proof_bytes, public_inputs)
        else:
            return self._mint_eoa(puzzle_id_bytes, proof_bytes, public_inputs)

    # ── EOA path (plain private key, standard tx) ─────────────────────────────

    def _mint_eoa(self, puzzle_id_bytes, proof_bytes, public_inputs):
        tx = self.nft.functions.mintWithProof(
            puzzle_id_bytes, proof_bytes, public_inputs,
        ).build_transaction({
            "from":    self.sender,
            "nonce":   self.w3.eth.get_transaction_count(self.sender),
            "gas":     900_000,
            "chainId": CHAIN_ID,
        })
        signed  = self.signer_key.sign_transaction(tx)
        tx_hash = self.w3.eth.send_raw_transaction(signed.raw_transaction)
        return self._wait(tx_hash)

    # ── AGW path (signer private key, ZKsync type-113 EIP-712 tx) ───────────────────

    def _mint_agw(self, puzzle_id_bytes, proof_bytes, public_inputs):
        """
        Constructs a ZKsync EIP-712 type-113 transaction signed by the signer private key,
        sent FROM the AGW smart wallet address.

        Requires: pip install zksync2
        """
        try:
            from zksync2.module.module_builder import ZkSyncBuilder
            from zksync2.core.types import EthBlockParams, PaymasterParams
            from zksync2.signer.eth_signer import PrivateKeyEthSigner
            from zksync2.transaction.transaction_builders import TxFunctionCall
        except ImportError:
            raise ImportError(
                "AGW mode requires zksync2: pip install zksync2"
            )

        zk = ZkSyncBuilder.build(ABSTRACT_RPC)
        signer = PrivateKeyEthSigner(self.signer_key, CHAIN_ID)

        calldata = self.nft.encodeABI(
            fn_name="mintWithProof",
            args=[puzzle_id_bytes, proof_bytes, public_inputs],
        )

        nonce     = zk.zksync.get_transaction_count(self.sender, EthBlockParams.LATEST.value)
        gas_price = zk.eth.gas_price

        tx_func = TxFunctionCall(
            chain_id=CHAIN_ID,
            nonce=nonce,
            from_=self.sender,
            to=Web3.to_checksum_address(NFT_CONTRACT_ADDR),
            data=calldata,
            gas_limit=900_000,
            gas_price=gas_price,
            max_priority_fee_per_gas=gas_price,
        )

        estimated = zk.zksync.eth_estimate_gas(tx_func.tx)
        tx_func.tx["gas"] = estimated

        signed_msg = signer.sign_typed_data(tx_func.tx712(estimated))
        raw        = tx_func.encode(signed_msg)

        tx_hash = zk.zksync.send_raw_transaction(raw)
        return self._wait(tx_hash)

    # ── helpers ───────────────────────────────────────────────────────────────

    def _wait(self, tx_hash) -> str:
        print(f"[Minter] TX sent: {tx_hash.hex()}")
        receipt = self.w3.eth.wait_for_transaction_receipt(tx_hash, timeout=120)
        if receipt["status"] == 1:
            logs = self.nft.events.PuzzleSolved().process_receipt(receipt)
            if logs:
                print(f"[Minter] NFT minted! Token ID: {logs[0]['args']['tokenId']}")
            print(f"[Minter] https://sepolia.abscan.org/tx/{tx_hash.hex()}")
            return tx_hash.hex()
        raise RuntimeError(f"TX reverted: {tx_hash.hex()}")
