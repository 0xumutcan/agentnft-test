"""
EZKL pipeline: PyTorch model → ONNX → ZK circuit → Solidity verifier

Steps:
  1. Export model to ONNX
  2. Generate EZKL settings (calibrate k, logrows)
  3. Compile circuit
  4. Download SRS
  5. Generate proving/verifying keys
  6. Export Solidity verifier

Usage:
    python ml/ezkl_pipeline.py --puzzle puzzles/puzzle_002.json
"""

import argparse
import json
import os
import shutil

import numpy as np
import torch
import ezkl
from sentence_transformers import SentenceTransformer

from model import load_model

EMBED_MODEL = "all-MiniLM-L6-v2"


def export_onnx(model_pt_path: str, onnx_path: str, input_dim: int) -> None:
    model = load_model(model_pt_path, input_dim=input_dim)
    dummy = torch.randn(1, input_dim)
    # Use legacy exporter (dynamo=False) for EZKL compatibility
    torch.onnx.export(
        model,
        (dummy,),
        onnx_path,
        input_names=["pca_embedding"],
        output_names=["score"],
        opset_version=17,
        dynamo=False,
    )
    print(f"ONNX exported: {onnx_path}  (input_dim={input_dim})")


def make_sample_input(output_dir: str, puzzle_id_short: str) -> str:
    """
    Create calibration input: text → 384-dim embed → PCA → StandardScaler → EZKL
    Values stay near [-3, 3], keeping EZKL lookup_range small → lower logrows.
    """
    import pickle
    embedder = SentenceTransformer(EMBED_MODEL)
    pca_path = os.path.join(output_dir, f"pca_{puzzle_id_short}.pkl")
    with open(pca_path, "rb") as f:
        bundle = pickle.load(f)
    pca, scaler = bundle["pca"], bundle["scaler"]

    sample_texts = ["penguin", "flightless bird", "blockchain", "table"]
    embeddings = embedder.encode(sample_texts, normalize_embeddings=True)
    pca_vecs    = pca.transform(embeddings).astype(np.float32)
    scaled_vecs = scaler.transform(pca_vecs).astype(np.float32)

    input_data = {"input_data": [scaled_vecs[i].tolist() for i in range(len(scaled_vecs))]}
    path = os.path.join(output_dir, "sample_input.json")
    with open(path, "w") as f:
        json.dump(input_data, f)
    print(f"Sample input: {scaled_vecs.shape}  "
          f"range=[{scaled_vecs.min():.2f}, {scaled_vecs.max():.2f}]")
    return path


async def _maybe_await(result):
    """Await if coroutine, return directly otherwise (handles sync/async EZKL API changes)."""
    import inspect
    if inspect.iscoroutine(result):
        return await result
    return result


async def run_pipeline(
    puzzle_id_short: str,
    output_dir: str = "ml/artifacts",
    contracts_dir: str = "contracts/src/verifiers",
) -> None:
    onnx_path      = os.path.join(output_dir, f"model_{puzzle_id_short}.onnx")
    settings_path  = os.path.join(output_dir, f"settings_{puzzle_id_short}.json")
    compiled_path  = os.path.join(output_dir, f"circuit_{puzzle_id_short}.compiled")
    pk_path        = os.path.join(output_dir, f"pk_{puzzle_id_short}.key")
    vk_path        = os.path.join(output_dir, f"vk_{puzzle_id_short}.key")
    verifier_path  = os.path.join(output_dir, f"verifier_{puzzle_id_short}.sol")
    abi_path       = os.path.join(output_dir, f"verifier_{puzzle_id_short}.abi")
    sample_path    = os.path.join(output_dir, "sample_input.json")

    # 1. Generate EZKL settings
    print("Step 1: Generating EZKL settings...")
    res = await _maybe_await(ezkl.gen_settings(onnx_path, settings_path))
    assert res, "gen_settings failed"

    # 1b. Force lower scale to reduce lookup range → smaller logrows / pk
    # scale=7 means 2^7=128 quantization steps — sufficient for our simple binary classifier
    with open(settings_path) as f:
        s = json.load(f)
    s["run_args"]["input_scale"] = 7
    s["run_args"]["param_scale"] = 7
    with open(settings_path, "w") as f:
        json.dump(s, f, indent=2)
    print(f"  Forced input_scale=7, param_scale=7")

    # 2. Calibrate (determines optimal logrows given our fixed scale)
    print("Step 2: Calibrating settings...")
    res = await _maybe_await(ezkl.calibrate_settings(sample_path, onnx_path, settings_path, "resources"))
    assert res, "calibrate_settings failed"

    # 3. Read calibrated logrows, generate local SRS
    with open(settings_path) as f:
        s = json.load(f)
    logrows = s["run_args"]["logrows"]
    srs_path = os.path.join(output_dir, f"kzg{logrows}.srs")
    print(f"Step 3: Generating local SRS (logrows={logrows}) — research/testing setup...")
    if not os.path.exists(srs_path):
        res = await _maybe_await(ezkl.gen_srs(srs_path, logrows))
        # gen_srs returns None on success
    else:
        print(f"  SRS already exists, reusing.")

    # 4. Compile circuit
    print("Step 4: Compiling circuit...")
    res = await _maybe_await(ezkl.compile_circuit(onnx_path, compiled_path, settings_path))
    assert res, "compile_circuit failed"

    # 5. Setup (generate pk/vk)
    print("Step 5: Generating proving/verifying keys...")
    res = await _maybe_await(ezkl.setup(compiled_path, vk_path, pk_path, srs_path))
    assert res, "setup failed"

    # 6. Export Solidity verifier
    print("Step 6: Exporting Solidity verifier...")
    res = await _maybe_await(
        ezkl.create_evm_verifier(vk_path, settings_path, verifier_path, abi_path, srs_path)
    )
    assert res, "create_evm_verifier failed"

    # Copy verifier to contracts directory
    os.makedirs(contracts_dir, exist_ok=True)
    dest = os.path.join(contracts_dir, f"Halo2Verifier_{puzzle_id_short}.sol")
    shutil.copy(verifier_path, dest)
    print(f"Verifier copied to: {dest}")

    print("\nPipeline complete.")
    print(f"  Proving key  : {pk_path}")
    print(f"  Verifying key: {vk_path}")
    print(f"  Verifier.sol : {dest}")


def generate_proof(
    puzzle_id_short: str,
    embedding: np.ndarray,
    output_dir: str = "ml/artifacts",
    proof_path: str = "proof.json",
) -> tuple[bytes, list[int]]:
    """
    Generate an EZKL proof for a given embedding vector.
    Returns (proof_bytes, public_inputs_as_uint256_list).
    Called by the agent at runtime.
    """
    import asyncio

    compiled_path  = os.path.join(output_dir, f"circuit_{puzzle_id_short}.compiled")
    pk_path        = os.path.join(output_dir, f"pk_{puzzle_id_short}.key")
    settings_path  = os.path.join(output_dir, f"settings_{puzzle_id_short}.json")
    witness_path   = os.path.join(output_dir, "witness.json")
    input_path     = os.path.join(output_dir, "input_runtime.json")

    # Read logrows to find srs_path (needed for prove in some versions)
    with open(settings_path) as f:
        s = json.load(f)
    logrows = s["run_args"]["logrows"]
    srs_path = os.path.join(output_dir, f"kzg{logrows}.srs")

    # Write input
    input_data = {"input_data": [embedding.tolist()]}
    with open(input_path, "w") as f:
        json.dump(input_data, f)

    async def _prove():
        import inspect
        # Witness
        r = ezkl.gen_witness(input_path, compiled_path, witness_path)
        if inspect.iscoroutine(r):
            r = await r
        assert r, "gen_witness failed"

        # Prove
        r = ezkl.prove(witness_path, compiled_path, pk_path, proof_path, "single", srs_path=srs_path)
        if inspect.iscoroutine(r):
            r = await r
        assert r, "prove failed"

    asyncio.run(_prove())

    # Read proof
    with open(proof_path) as f:
        proof_data = json.load(f)

    proof_bytes = bytes.fromhex(proof_data["proof"].replace("0x", ""))

    # Flatten instances to uint256 list.
    # EZKL 9.x stores field elements as 64-char hex strings in little-endian byte order.
    # We must reverse the bytes before interpreting as a uint256, otherwise the value
    # exceeds the BN254 prime and the on-chain verifier rejects it.
    instances_flat = []
    for instance_row in proof_data["instances"]:
        for val in instance_row:
            if isinstance(val, str):
                hex_str = val[2:] if val.startswith("0x") else val
                if len(hex_str) == 64:
                    # 32-byte little-endian field element → big-endian uint256
                    val_int = int.from_bytes(bytes.fromhex(hex_str), byteorder='little')
                else:
                    val_int = int(hex_str, 16)
            else:
                val_int = int(val)
            instances_flat.append(val_int)

    return proof_bytes, instances_flat


if __name__ == "__main__":
    import asyncio

    parser = argparse.ArgumentParser()
    parser.add_argument("--puzzle", default="puzzles/puzzle_002.json")
    parser.add_argument("--output-dir", default="ml/artifacts")
    args = parser.parse_args()

    with open(args.puzzle) as f:
        puzzle = json.load(f)

    puzzle_id_short = puzzle["id"].replace("0x", "")[:8]
    model_pt_path   = os.path.join(args.output_dir, f"model_{puzzle_id_short}.pt")
    onnx_path       = os.path.join(args.output_dir, f"model_{puzzle_id_short}.onnx")

    # Read PCA output dim from saved PCA model
    import pickle
    pca_path = os.path.join(args.output_dir, f"pca_{puzzle_id_short}.pkl")
    with open(pca_path, "rb") as f:
        bundle = pickle.load(f)
    input_dim = bundle["pca"].n_components_

    # Export ONNX with correct input dim
    export_onnx(model_pt_path, onnx_path, input_dim=input_dim)

    # Make calibration sample (PCA-reduced)
    make_sample_input(args.output_dir, puzzle_id_short)

    # Run EZKL pipeline
    asyncio.run(run_pipeline(puzzle_id_short, args.output_dir))
