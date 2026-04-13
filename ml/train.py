"""
Train a per-puzzle AnswerValidator MLP.

Pipeline:
  1. Compute 384-dim sentence embeddings for all examples
  2. Fit PCA (384 → 32) on the full corpus
  3. Project all embeddings through PCA
  4. Train MLP on 32-dim PCA features

Artifacts saved:
  ml/artifacts/pca_{puzzle_id}.pkl   — sklearn PCA (used by agent at runtime)
  ml/artifacts/model_{puzzle_id}.pt  — MLP weights (circuit input)

Usage:
    python ml/train.py --puzzle puzzles/puzzle_002.json
"""

import argparse
import json
import os
import pickle
import random

import numpy as np
import torch
import torch.nn as nn
from sentence_transformers import SentenceTransformer
from sklearn.decomposition import PCA
from torch.utils.data import DataLoader, TensorDataset

from model import AnswerValidator, PCA_DIM

EMBED_MODEL = "all-MiniLM-L6-v2"
SEED = 42


def build_negatives(answer: str, answer_variants: list[str]) -> list[str]:
    """Hard-coded negative pool — extend per puzzle as needed."""
    general_negatives = [
        "blockchain", "cryptography", "consensus", "merkle tree",
        "smart contract", "ethereum", "bitcoin", "solidity",
        "polar bear", "seal", "walrus", "orca", "whale",
        "eagle", "falcon", "parrot", "flamingo", "ostrich",
        "antarctica", "arctic", "iceland", "greenland",
        "zero knowledge proof", "hash function",
        "table", "chair", "building", "mountain", "river",
        "red", "blue", "mathematics", "physics", "music",
        "democracy", "freedom", "justice", "love",
    ]
    # Remove anything that overlaps with correct answers
    answer_set = {a.lower() for a in answer_variants}
    return [n for n in general_negatives if n.lower() not in answer_set]


def embed(texts: list[str], embedder: SentenceTransformer) -> np.ndarray:
    return embedder.encode(texts, normalize_embeddings=True, show_progress_bar=False)


def train(puzzle_path: str, output_dir: str = "ml/artifacts") -> str:
    random.seed(SEED)
    torch.manual_seed(SEED)
    np.random.seed(SEED)

    with open(puzzle_path) as f:
        puzzle = json.load(f)

    puzzle_id = puzzle["id"].replace("0x", "")[:8]
    answer_variants = puzzle["answer_variants"]

    print(f"Loading embedding model: {EMBED_MODEL}")
    embedder = SentenceTransformer(EMBED_MODEL)

    # ── 1. Compute full-dim embeddings ─────────────────────��──────────────────
    positives_384 = embed(answer_variants, embedder)
    negatives_text = build_negatives(puzzle["answer"], answer_variants)
    negatives_384 = embed(negatives_text, embedder)

    # Augment positives with small Gaussian noise (in 384-dim space)
    augmented = []
    for vec in positives_384:
        for _ in range(6):
            noise = np.random.normal(0, 0.02, vec.shape).astype(np.float32)
            noisy = vec + noise
            noisy = noisy / (np.linalg.norm(noisy) + 1e-8)  # re-normalize
            augmented.append(noisy)
    positives_384 = np.vstack([positives_384, np.array(augmented)])

    X_full = np.vstack([positives_384, negatives_384]).astype(np.float32)
    y = np.array(
        [1.0] * len(positives_384) + [0.0] * len(negatives_384), dtype=np.float32
    )

    # ── 2. Fit PCA (384 → PCA_DIM) then standardize to [-1, 1] ───────────────
    from sklearn.preprocessing import StandardScaler
    n_components = min(PCA_DIM, X_full.shape[0] - 1, X_full.shape[1])
    print(f"Fitting PCA: 384 → {n_components} dims on {len(X_full)} samples")
    pca = PCA(n_components=n_components, random_state=SEED)
    X_pca_raw = pca.fit_transform(X_full).astype(np.float32)
    explained = pca.explained_variance_ratio_.sum()
    print(f"  Explained variance: {explained:.1%}")

    # Standardize: zero mean, unit variance → values stay near [-3, 3]
    # This keeps EZKL lookup_range small → logrows drops significantly
    scaler = StandardScaler()
    X_pca = scaler.fit_transform(X_pca_raw).astype(np.float32)
    print(f"  PCA range before scale: [{X_pca_raw.min():.2f}, {X_pca_raw.max():.2f}]")
    print(f"  PCA range after  scale: [{X_pca.min():.2f}, {X_pca.max():.2f}]")

    # Bundle PCA + scaler together so agent applies both
    pca_bundle = {"pca": pca, "scaler": scaler}

    # Save PCA bundle (pca + scaler) for agent runtime use
    os.makedirs(output_dir, exist_ok=True)
    pca_path = os.path.join(output_dir, f"pca_{puzzle_id}.pkl")
    with open(pca_path, "wb") as f:
        pickle.dump(pca_bundle, f)
    print(f"PCA bundle saved: {pca_path}")

    # ── 3. Train MLP on PCA features ──────────────────────────────────────────
    idx = np.random.permutation(len(X_pca))
    X_pca, y = X_pca[idx], y[idx]

    dataset = TensorDataset(torch.from_numpy(X_pca), torch.from_numpy(y))
    loader = DataLoader(dataset, batch_size=16, shuffle=True)

    model = AnswerValidator(input_dim=n_components)
    # weight_decay=1e-3 keeps weights small → smaller EZKL lookup range
    optimizer = torch.optim.Adam(model.parameters(), lr=1e-3, weight_decay=1e-3)
    criterion = nn.BCELoss()

    print(f"Training LogReg ({n_components}→1, sigmoid) on {len(X_pca)} samples "
          f"({len(positives_384)} pos / {len(negatives_384)} neg)")
    for epoch in range(500):
        model.train()
        total_loss = 0.0
        for xb, yb in loader:
            optimizer.zero_grad()
            pred = model(xb).squeeze()
            loss = criterion(pred, yb)
            loss.backward()
            optimizer.step()
            model.clip_weights(max_val=1.0)
            total_loss += loss.item()
        if (epoch + 1) % 100 == 0:
            max_w = max(m.weight.abs().max().item()
                        for m in model.modules() if isinstance(m, nn.Linear))
            print(f"  Epoch {epoch+1}/500  loss={total_loss/len(loader):.4f}  max_w={max_w:.3f}")

    model.eval()
    with torch.no_grad():
        preds = model(torch.from_numpy(X_pca)).squeeze().numpy()
    acc = ((preds > 0.5) == y.astype(bool)).mean()
    print(f"Train accuracy: {acc:.3f}")

    # Save model
    model_path = os.path.join(output_dir, f"model_{puzzle_id}.pt")
    torch.save(model.state_dict(), model_path)
    print(f"Model saved: {model_path}")

    # ── 4. Sanity check (full pipeline: text → 384 → PCA → MLP) ──────────────
    test_cases = [
        (puzzle["answer"], "SHOULD PASS"),
        ("penguin bird", "SHOULD PASS"),
        ("blockchain",  "should fail"),
        ("polar bear",  "should fail"),
        ("eagle",       "should fail"),
    ]
    print("\nSanity check (text → PCA → scaler → MLP):")
    for text, label in test_cases:
        vec_384 = embed([text], embedder)
        vec_pca = pca.transform(vec_384).astype(np.float32)
        vec_scaled = scaler.transform(vec_pca).astype(np.float32)
        score = model(torch.from_numpy(vec_scaled)).item()
        ok = (score > 0.5) == (label == "SHOULD PASS")
        status = "PASS" if ok else "FAIL"
        print(f"  [{status}] '{text}' score={score:.3f}  ({label})")

    return model_path


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--puzzle", default="puzzles/puzzle_002.json")
    parser.add_argument("--output-dir", default="ml/artifacts")
    args = parser.parse_args()
    train(args.puzzle, args.output_dir)
