"""
minter.py — Sends mintWithProof() transaction to ZkMLNFT on Abstract L2.
"""

import json
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


class Minter:
    def __init__(self):
        self.w3      = Web3(Web3.HTTPProvider(ABSTRACT_RPC))
        self.w3.middleware_onion.inject(ExtraDataToPOAMiddleware, layer=0)
        self.account = Account.from_key(PRIVATE_KEY)
        self.nft     = self.w3.eth.contract(
            address=Web3.to_checksum_address(NFT_CONTRACT_ADDR),
            abi=NFT_ABI,
        )

    def already_claimed(self, puzzle_id_hex: str) -> bool:
        puzzle_id_bytes = bytes.fromhex(puzzle_id_hex.replace("0x", ""))
        return self.nft.functions.claimed(
            puzzle_id_bytes, self.account.address
        ).call()

    def mint(
        self,
        puzzle_id_hex: str,
        proof_bytes: bytes,
        public_inputs: list[int],
    ) -> str:
        """
        Submit mintWithProof() to Abstract L2.
        Returns tx hash on success.
        """
        puzzle_id_bytes = bytes.fromhex(puzzle_id_hex.replace("0x", ""))

        print(f"[Minter] Building mintWithProof tx...")
        print(f"  puzzle_id : {puzzle_id_hex}")
        print(f"  proof size: {len(proof_bytes)} bytes")
        print(f"  instances : {len(public_inputs)} values")

        tx = self.nft.functions.mintWithProof(
            puzzle_id_bytes,
            proof_bytes,
            public_inputs,
        ).build_transaction({
            "from":    self.account.address,
            "nonce":   self.w3.eth.get_transaction_count(self.account.address),
            "gas":     900_000,
            "chainId": self.w3.eth.chain_id,
        })

        signed   = self.account.sign_transaction(tx)
        tx_hash  = self.w3.eth.send_raw_transaction(signed.raw_transaction)

        print(f"[Minter] TX sent: {tx_hash.hex()}")
        print(f"[Minter] Waiting for confirmation...")

        receipt = self.w3.eth.wait_for_transaction_receipt(tx_hash, timeout=120)

        if receipt["status"] == 1:
            # Parse PuzzleSolved event for token ID
            logs = self.nft.events.PuzzleSolved().process_receipt(receipt)
            if logs:
                token_id = logs[0]["args"]["tokenId"]
                print(f"[Minter] NFT minted! Token ID: {token_id}")
            return tx_hash.hex()
        else:
            raise RuntimeError(f"TX reverted: {tx_hash.hex()}")
