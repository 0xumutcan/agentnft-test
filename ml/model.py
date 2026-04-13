"""
Puzzle answer validator MLP.

Pipeline:
  sentence-transformers  →  384-dim embedding  (off-circuit, agent side)
  PCA (sklearn)          →  32-dim projection  (off-circuit, agent side)
  AnswerValidator MLP    →  scalar [0,1]        (ZK circuit — EZKL proves this)

Reducing input from 384 → 32 dims drops proving key from ~500MB to ~8MB.
PCA transform is deterministic and public — does not weaken ZK guarantees.
"""

import torch
import torch.nn as nn

PCA_DIM = 8    # 8-dim PCA → tiny circuit, ~10MB pk


class AnswerValidator(nn.Module):
    """
    Logistic regression over PCA features.

    Why so simple?
    - Single Linear layer → only 1 dot product in the ZK circuit
    - No ReLU/Tanh → no non-linearity lookup tables (biggest circuit cost)
    - Sigmoid only at output → 1 small lookup table
    - Result: logrows drops to ~12, pk ~15-30MB
    - Accuracy sufficient for binary semantic classification

    Circuit size comparison:
      MLP (384→64→32→1, ReLU) : logrows=16, pk=500MB
      MLP (32→16→8→1, Tanh)   : logrows=15, pk=250MB
      LogReg (8→1, Sigmoid)   : logrows=12, pk=~15MB  ← this
    """
    def __init__(self, input_dim: int = PCA_DIM):
        super().__init__()
        self.net = nn.Sequential(
            nn.Linear(input_dim, 1),
            nn.Sigmoid(),
        )

    def clip_weights(self, max_val: float = 1.0):
        with torch.no_grad():
            for m in self.modules():
                if isinstance(m, nn.Linear):
                    m.weight.clamp_(-max_val, max_val)
                    m.bias.clamp_(-max_val, max_val)

    def forward(self, x: torch.Tensor) -> torch.Tensor:
        return self.net(x)


def load_model(path: str, input_dim: int = PCA_DIM) -> AnswerValidator:
    model = AnswerValidator(input_dim)
    model.load_state_dict(torch.load(path, map_location="cpu", weights_only=True))
    model.eval()
    return model
