import "dotenv/config";
import express from "express";
import { paymentMiddleware, Network } from "x402-express";
import { privateKeyToAccount } from "viem/accounts";
import fs from "fs";
import path from "path";

const app  = express();
const PORT = process.env.X402_PORT || 3000;

// ── Wallet that receives payments ────────────────────────────────────────────
const account = privateKeyToAccount(process.env.PRIVATE_KEY);
console.log("Payment receiver:", account.address);

// ── Load puzzle clues ────────────────────────────────────────────────────────
function loadPuzzle(id) {
  const p = path.resolve(`../puzzles/puzzle_${id}.json`);
  return JSON.parse(fs.readFileSync(p, "utf8"));
}

// ── Health check (free) ──────────────────────────────────────────────────────
app.get("/health", (_, res) => res.json({ ok: true }));

// ── Puzzle directory (free) ───────────────────────────────────────────────────
// Agents can discover which puzzles exist and their x402 clue endpoints.
app.get("/puzzles", (_, res) => {
  res.json({
    puzzles: [
      {
        id: "001",
        onchain_clues: 2,
        paid_clues: [
          { path: "/ipucu/puzzle_002/2", price_usd: 1 },
          { path: "/ipucu/puzzle_002/3", price_usd: 1 },
          { path: "/ipucu/puzzle_002/4", price_usd: 2 },
        ],
      },
    ],
  });
});

// ── x402 paid clue endpoints ──────────────────────────────────────────────────
//
// Flow:
//   1. Agent GET /ipucu/puzzle_002/2
//   2. Server returns 402 with payment requirements
//   3. Agent pays 1 USDC → retries with X-PAYMENT header
//   4. Middleware verifies payment → handler runs → clue returned
//
// The payment middleware wraps each route with a different price.

function clueHandler(puzzleId, clueIndex) {
  return (req, res) => {
    try {
      const puzzle = loadPuzzle(puzzleId);
      const clue   = puzzle.clues.find((c) => c.index === clueIndex);

      if (!clue) {
        return res.status(404).json({ error: "Clue not found" });
      }

      res.json({
        puzzle_id:  puzzle.id,
        clue_index: clue.index,
        type:       clue.type,
        data:       clue.data,
        // Hint to agent: are there more paid clues?
        next: clueIndex < 4
          ? `/ipucu/puzzle_${puzzleId}/${clueIndex + 1}`
          : null,
      });
    } catch (err) {
      res.status(500).json({ error: err.message });
    }
  };
}

// Clue 2 — $1
app.get(
  "/ipucu/puzzle_002/2",
  paymentMiddleware(account.address, "$1", { network: Network.BaseSepolia }),
  clueHandler("001", 2)
);

// Clue 3 — $1
app.get(
  "/ipucu/puzzle_002/3",
  paymentMiddleware(account.address, "$1", { network: Network.BaseSepolia }),
  clueHandler("001", 3)
);

// Clue 4 — $2 (strongest hint)
app.get(
  "/ipucu/puzzle_002/4",
  paymentMiddleware(account.address, "$2", { network: Network.BaseSepolia }),
  clueHandler("001", 4)
);

// ── 402 response format note for agents ───────────────────────────────────────
// On a 402, the response body looks like:
// {
//   "x402Version": 1,
//   "error": "Payment required",
//   "accepts": [{
//     "scheme": "exact",
//     "network": "base-sepolia",
//     "maxAmountRequired": "1000000",
//     "asset": "0x036CbD53842c5426634e7929541eC2318f3dCF7e",  ← USDC on Base Sepolia
//     "payTo": "<account.address>",
//     "extra": { "name": "Puzzle Clue" }
//   }]
// }

app.listen(PORT, () => {
  console.log(`x402 clue server running on port ${PORT}`);
});
