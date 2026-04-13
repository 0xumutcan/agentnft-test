"""
x402_client.py — HTTP client that handles 402 Payment Required responses.

Flow:
  1. GET <url>  →  if 200, return body
  2. If 402, parse payment requirements
  3. Build & send USDC payment on Base
  4. Retry GET with X-PAYMENT header
  5. Return clue body
"""

import httpx
import json
from eth_account import Account
from web3 import Web3

from config import PRIVATE_KEY, BASE_RPC

# USDC on Base Sepolia
USDC_ADDRESS    = "0x036CbD53842c5426634e7929541eC2318f3dCF7e"
USDC_DECIMALS   = 6

USDC_ABI = json.loads('[{"inputs":[{"name":"to","type":"address"},{"name":"amount","type":"uint256"}],"name":"transfer","outputs":[{"name":"","type":"bool"}],"stateMutability":"nonpayable","type":"function"}]')


class X402Client:
    def __init__(self):
        self.w3      = Web3(Web3.HTTPProvider(BASE_RPC))
        self.account = Account.from_key(PRIVATE_KEY)
        self.usdc    = self.w3.eth.contract(
            address=Web3.to_checksum_address(USDC_ADDRESS),
            abi=USDC_ABI,
        )

    def get(self, url: str) -> dict:
        """
        Fetch a URL, handling x402 payment if required.
        Returns parsed JSON body.
        """
        with httpx.Client(timeout=30) as client:
            resp = client.get(url)

            if resp.status_code == 200:
                return resp.json()

            if resp.status_code == 402:
                payment_info = resp.json()
                print(f"  [x402] 402 received — initiating payment for {url}")
                payment_header = self._pay(payment_info)

                # Retry with payment proof
                retry = client.get(url, headers={"X-PAYMENT": payment_header})
                retry.raise_for_status()
                return retry.json()

            resp.raise_for_status()

    def _pay(self, payment_info: dict) -> str:
        """
        Execute USDC transfer and return X-PAYMENT header value.
        Supports the x402 'exact' scheme.
        """
        accepts = payment_info.get("accepts", [])
        if not accepts:
            raise ValueError("No payment options in 402 response")

        # Pick first accepted option
        option = accepts[0]
        pay_to = Web3.to_checksum_address(option["payTo"])
        amount = int(option["maxAmountRequired"])
        asset  = Web3.to_checksum_address(option["asset"])

        print(f"  [x402] Paying {amount / 10**USDC_DECIMALS:.2f} USDC → {pay_to}")

        # Build USDC transfer tx
        tx = self.usdc.functions.transfer(pay_to, amount).build_transaction({
            "from":  self.account.address,
            "nonce": self.w3.eth.get_transaction_count(self.account.address),
            "gas":   100_000,
            "chainId": self.w3.eth.chain_id,
        })
        signed   = self.account.sign_transaction(tx)
        tx_hash  = self.w3.eth.send_raw_transaction(signed.raw_transaction)
        receipt  = self.w3.eth.wait_for_transaction_receipt(tx_hash)

        if receipt["status"] != 1:
            raise RuntimeError("USDC transfer failed")

        print(f"  [x402] Payment confirmed: {tx_hash.hex()}")

        # Build X-PAYMENT header (x402 exact scheme)
        payment_header = json.dumps({
            "x402Version": 1,
            "scheme": "exact",
            "network": option.get("network", "base-sepolia"),
            "payload": {
                "txHash": tx_hash.hex(),
                "from":   self.account.address,
            }
        })
        return payment_header

    def fetch_paid_clues(self, base_url: str, clue_count: int) -> list[dict]:
        """Fetch all paid clues from an x402 server sequentially."""
        clues = []
        for i in range(2, 2 + clue_count):  # paid clues start at index 2
            url = f"{base_url}/{i}"
            print(f"  [x402] Fetching clue {i} from {url}")
            clue = self.get(url)
            clues.append(clue)
            if clue.get("next") is None:
                break
        return clues
