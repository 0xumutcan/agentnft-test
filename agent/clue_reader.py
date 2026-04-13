"""
clue_reader.py — Reads on-chain clues from PuzzleRegistry events.

Primary discovery: eth_getLogs on ClueDeposited events.
If a TYPE_POINTER clue is found pointing to an x402 server,
the paid_clue_endpoint is returned for the x402 client to handle.
"""

from dataclasses import dataclass
from typing import Optional
from web3 import Web3
from web3.middleware import ExtraDataToPOAMiddleware
import json, os

from config import ABSTRACT_RPC, PUZZLE_REGISTRY_ADDR

# Clue type constants (mirror PuzzleRegistry.sol)
TYPE_TEXT        = 0
TYPE_HINT        = 1
TYPE_ELIMINATION = 2
TYPE_CONTEXT     = 3
TYPE_POINTER     = 4

TYPE_NAMES = {
    TYPE_TEXT:        "TEXT",
    TYPE_HINT:        "HINT",
    TYPE_ELIMINATION: "ELIMINATION",
    TYPE_CONTEXT:     "CONTEXT",
    TYPE_POINTER:     "POINTER",
}

REGISTRY_ABI = json.loads("""[
  {
    "anonymous": false,
    "inputs": [
      {"indexed": true,  "name": "puzzleId", "type": "bytes32"},
      {"indexed": false, "name": "index",    "type": "uint256"},
      {"indexed": false, "name": "clueType", "type": "uint8"},
      {"indexed": false, "name": "data",     "type": "bytes"}
    ],
    "name": "ClueDeposited",
    "type": "event"
  },
  {
    "inputs": [{"name": "puzzleId", "type": "bytes32"}],
    "name": "getVerifier",
    "outputs": [{"name": "", "type": "address"}],
    "stateMutability": "view",
    "type": "function"
  },
  {
    "inputs": [{"name": "puzzleId", "type": "bytes32"}],
    "name": "isPuzzleActive",
    "outputs": [{"name": "", "type": "bool"}],
    "stateMutability": "view",
    "type": "function"
  }
]""")


@dataclass
class Clue:
    index:    int
    type_id:  int
    type_name: str
    raw:      bytes
    text:     Optional[str]       = None  # decoded for TEXT/HINT/ELIMINATION/CONTEXT
    pointer:  Optional[dict]      = None  # decoded for TYPE_POINTER


@dataclass
class X402Pointer:
    protocol:    str
    base_url:    str
    clue_count:  int
    price_per_clue: int  # in smallest unit (e.g. 1000000 = 1 USDC)


def _decode_clue(clue_type: int, raw: bytes) -> tuple[Optional[str], Optional[dict]]:
    try:
        if clue_type in (TYPE_TEXT, TYPE_HINT, TYPE_ELIMINATION, TYPE_CONTEXT):
            text = Web3.to_text(raw) if raw[:2] != b'\x00\x00' else _abi_decode_string(raw)
            return text, None
        elif clue_type == TYPE_POINTER:
            decoded = _abi_decode_pointer(raw)
            return None, decoded
    except Exception:
        pass
    return raw.hex(), None


def _abi_decode_string(raw: bytes) -> str:
    """ABI-decode a single string (abi.encode(string))."""
    from eth_abi import decode
    (text,) = decode(["string"], raw)
    return text


def _abi_decode_pointer(raw: bytes) -> dict:
    """ABI-decode x402 pointer: (string protocol, string url, uint256 count, uint256 price)."""
    from eth_abi import decode
    protocol, base_url, count, price = decode(
        ["string", "string", "uint256", "uint256"], raw
    )
    return {
        "protocol":        protocol,
        "base_url":        base_url,
        "clue_count":      int(count),
        "price_per_clue":  int(price),
    }


class ClueReader:
    def __init__(self):
        self.w3 = Web3(Web3.HTTPProvider(ABSTRACT_RPC))
        self.w3.middleware_onion.inject(ExtraDataToPOAMiddleware, layer=0)
        self.registry = self.w3.eth.contract(
            address=Web3.to_checksum_address(PUZZLE_REGISTRY_ADDR),
            abi=REGISTRY_ABI,
        )

    def fetch_clues(self, puzzle_id_hex: str) -> list[Clue]:
        """
        Fetch all ClueDeposited events for a puzzle.
        Returns clues sorted by index.
        """
        puzzle_id_bytes = bytes.fromhex(puzzle_id_hex.replace("0x", ""))

        events = self.registry.events.ClueDeposited.get_logs(
            from_block=0,
            to_block="latest",
            argument_filters={"puzzleId": puzzle_id_bytes},
        )

        clues = []
        for ev in events:
            ctype = ev["args"]["clueType"]
            raw   = ev["args"]["data"]
            text, pointer = _decode_clue(ctype, raw)
            clues.append(Clue(
                index=ev["args"]["index"],
                type_id=ctype,
                type_name=TYPE_NAMES.get(ctype, str(ctype)),
                raw=raw,
                text=text,
                pointer=pointer,
            ))

        clues.sort(key=lambda c: c.index)
        return clues

    def get_x402_pointer(self, clues: list[Clue]) -> Optional[X402Pointer]:
        """Extract x402 pointer from clue list, if present."""
        for clue in clues:
            if clue.type_id == TYPE_POINTER and clue.pointer:
                p = clue.pointer
                if p.get("protocol") == "x402":
                    return X402Pointer(
                        protocol=p["protocol"],
                        base_url=p["base_url"],
                        clue_count=p["clue_count"],
                        price_per_clue=p["price_per_clue"],
                    )
        return None

    def get_verifier(self, puzzle_id_hex: str) -> str:
        puzzle_id_bytes = bytes.fromhex(puzzle_id_hex.replace("0x", ""))
        return self.registry.functions.getVerifier(puzzle_id_bytes).call()
