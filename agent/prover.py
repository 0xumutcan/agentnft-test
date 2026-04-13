"""
prover.py — Computes embedding, applies PCA, generates EZKL zkML proof.

Pipeline (all off-circuit except the last step):
  answer text
    → sentence-transformers  →  384-dim embedding  (off-circuit)
    → PCA (puzzle-specific)  →   8-dim projection   (off-circuit)
    → EZKL MLP proof         →  correctness proof   (ZK circuit)
"""

import sys, os, pickle
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "../ml"))

import numpy as np
from sentence_transformers import SentenceTransformer
from ezkl_pipeline import generate_proof

EMBED_MODEL = "all-MiniLM-L6-v2"

_embedder = None
_pca_cache: dict = {}


def _get_embedder() -> SentenceTransformer:
    global _embedder
    if _embedder is None:
        _embedder = SentenceTransformer(EMBED_MODEL)
    return _embedder


def _get_pca_bundle(puzzle_id_short: str, artifacts_dir: str):
    """Returns {"pca": PCA, "scaler": StandardScaler}"""
    if puzzle_id_short not in _pca_cache:
        pca_path = os.path.join(artifacts_dir, f"pca_{puzzle_id_short}.pkl")
        with open(pca_path, "rb") as f:
            _pca_cache[puzzle_id_short] = pickle.load(f)
    return _pca_cache[puzzle_id_short]


def prove(puzzle_id_hex: str, answer: str, artifacts_dir: str = None) -> tuple[bytes, list[int]]:
    """
    Full prove pipeline:
      answer → 384-dim embed → PCA (8-dim) → EZKL proof
    Returns (proof_bytes, public_inputs_uint256_list).
    """
    if artifacts_dir is None:
        from config import ML_ARTIFACTS_DIR
        artifacts_dir = ML_ARTIFACTS_DIR
    puzzle_id_short = puzzle_id_hex.replace("0x", "")[:8]

    # Step 1: sentence embedding (384-dim, off-circuit)
    print(f"[Prover] Embedding: '{answer}'")
    embedding_384 = _get_embedder().encode(
        answer, normalize_embeddings=True
    ).astype(np.float32).reshape(1, -1)

    # Step 2: PCA + standardize (384 → 32, off-circuit)
    bundle = _get_pca_bundle(puzzle_id_short, artifacts_dir)
    pca, scaler = bundle["pca"], bundle["scaler"]
    embedding_pca    = pca.transform(embedding_384).astype(np.float32)
    embedding_32     = scaler.transform(embedding_pca).astype(np.float32).flatten()
    print(f"[Prover] PCA+scale: 384-dim -> {embedding_32.shape[0]}-dim  "
          f"range=[{embedding_32.min():.2f}, {embedding_32.max():.2f}]")

    # Step 3: EZKL proof (32-dim → MLP → score > 0.7)
    print(f"[Prover] Generating EZKL proof...")
    proof_bytes, public_inputs = generate_proof(
        puzzle_id_short=puzzle_id_short,
        embedding=embedding_32,
        output_dir=artifacts_dir,
    )

    print(f"[Prover] Done. Proof size: {len(proof_bytes):,} bytes")
    return proof_bytes, public_inputs
