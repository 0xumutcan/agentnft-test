"""
main.py — Autonomous zkML puzzle-solving agent.

Usage:
    python agent/main.py --puzzle 0x0000...0001

Flow:
  1. Read free on-chain clues (ClueDeposited events)
  2. Check for x402 POINTER clue → fetch paid clues if present
  3. LLM reasons over all clues → produces answer
  4. Compute embedding → generate EZKL proof
  5. mintWithProof() on Abstract L2
"""

import argparse
import sys

from clue_reader import ClueReader, Clue, TYPE_POINTER
from x402_client import X402Client
from llm_reasoner import reason
from prover import prove
from minter import Minter


def merge_paid_clues(base_clues: list[Clue], paid_responses: list[dict]) -> list[Clue]:
    """Convert x402 JSON responses into Clue objects and append."""
    from clue_reader import Clue
    merged = list(base_clues)
    for resp in paid_responses:
        type_name = resp.get("type", "CONTEXT")
        type_map  = {"TEXT": 0, "HINT": 1, "ELIMINATION": 2, "CONTEXT": 3}
        merged.append(Clue(
            index=resp.get("clue_index", len(merged)),
            type_id=type_map.get(type_name, 3),
            type_name=type_name,
            raw=b"",
            text=resp.get("data"),
        ))
    return merged


def run(puzzle_id: str, skip_paid: bool = False) -> None:
    print(f"\n{'='*60}")
    print(f"  zkML Puzzle Agent")
    print(f"  Puzzle: {puzzle_id}")
    print(f"{'='*60}\n")

    # ── Step 1: Read free on-chain clues ──────────────────────────────────────
    print("[1/5] Reading on-chain clues...")
    reader = ClueReader()
    clues  = reader.fetch_clues(puzzle_id)

    free_clues = [c for c in clues if c.type_id != TYPE_POINTER]
    print(f"  Found {len(free_clues)} free clue(s):")
    for c in free_clues:
        print(f"  [{c.type_name}] {c.text or '(binary)'}")

    # ── Step 2: Fetch paid clues via x402 (if pointer exists) ─────────────────
    pointer = reader.get_x402_pointer(clues)
    if pointer and not skip_paid:
        print(f"\n[2/5] x402 pointer found → {pointer.base_url}")
        print(f"  {pointer.clue_count} paid clue(s), ~{pointer.price_per_clue/1e6:.0f} USDC each")
        x402   = X402Client()
        paid   = x402.fetch_paid_clues(pointer.base_url, pointer.clue_count)
        clues  = merge_paid_clues(free_clues, paid)
        print(f"  Total clues after purchase: {len(clues)}")
    else:
        print(f"\n[2/5] No x402 pointer {'(skipped)' if skip_paid else '— using free clues only'}")
        clues = free_clues

    # ── Step 3: LLM reasoning ─────────────────────────────────────────────────
    print("\n[3/5] LLM reasoning over clues...")
    answer = reason(clues)
    print(f"  Answer: '{answer}'")

    # ── Step 4: zkML proof generation ─────────────────────────────────────────
    print("\n[4/5] Generating EZKL zkML proof...")
    proof_bytes, public_inputs = prove(puzzle_id, answer)

    # ── Step 5: Mint NFT on Abstract L2 ───────────────────────────────────────
    print("\n[5/5] Minting NFT on Abstract L2...")
    minter = Minter()

    if minter.already_claimed(puzzle_id):
        print("  Already claimed this puzzle — skipping mint.")
        return

    tx_hash = minter.mint(puzzle_id, proof_bytes, public_inputs)

    print(f"\n{'='*60}")
    print(f"  Puzzle solved!")
    print(f"  TX: {tx_hash}")
    print(f"  Explorer: https://sepolia.abscan.org/tx/{tx_hash}")
    print(f"{'='*60}\n")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="zkML puzzle-solving agent")
    parser.add_argument(
        "--puzzle",
        default="0x0000000000000000000000000000000000000000000000000000000000000002",
        help="Puzzle ID (bytes32 hex)",
    )
    parser.add_argument(
        "--skip-paid",
        action="store_true",
        help="Skip x402 paid clues (use free on-chain clues only)",
    )
    args = parser.parse_args()
    run(args.puzzle, skip_paid=args.skip_paid)
