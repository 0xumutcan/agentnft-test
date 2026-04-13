import os
from dotenv import load_dotenv

load_dotenv(dotenv_path=os.path.join(os.path.dirname(__file__), "../.env"))

ABSTRACT_RPC         = os.environ["ABSTRACT_RPC"]
PRIVATE_KEY          = os.environ["PRIVATE_KEY"]
ANTHROPIC_API_KEY    = os.environ.get("ANTHROPIC_API_KEY", "")
BASE_RPC             = os.environ.get("BASE_RPC", "https://sepolia.base.org")
PUZZLE_REGISTRY_ADDR = os.environ["PUZZLE_REGISTRY_ADDRESS"]
NFT_CONTRACT_ADDR    = os.environ["NFT_CONTRACT_ADDRESS"]

ML_ARTIFACTS_DIR     = os.path.join(os.path.dirname(__file__), "../ml/artifacts")
PUZZLES_DIR          = os.path.join(os.path.dirname(__file__), "../puzzles")
