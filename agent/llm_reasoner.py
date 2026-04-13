"""
llm_reasoner.py — Uses Claude to reason over collected clues and produce an answer.
"""

import anthropic
from config import ANTHROPIC_API_KEY
from clue_reader import Clue, TYPE_TEXT, TYPE_HINT, TYPE_ELIMINATION, TYPE_CONTEXT

client = anthropic.Anthropic(api_key=ANTHROPIC_API_KEY)

SYSTEM_PROMPT = """You are an autonomous on-chain puzzle-solving agent.
Your task is to analyze clues retrieved from an Abstract L2 blockchain and
deduce a single answer: one word or short concept.

Rules:
- The answer is ONE concept, word, or short phrase.
- Clues were intentionally designed to guide you semantically — not trick you.
- Think step by step. Use elimination clues to rule out candidates.
- Your final answer will be converted to an embedding and validated by a zkML model.
  Synonyms and close paraphrases are acceptable — exact match is not required.
- Output ONLY your reasoning followed by: ANSWER: <your answer>
"""

def build_prompt(clues: list[Clue]) -> str:
    sections = {
        "TEXT":        [],
        "HINT":        [],
        "ELIMINATION": [],
        "CONTEXT":     [],
    }
    for clue in clues:
        if clue.type_name in sections and clue.text:
            sections[clue.type_name].append(f"  [{clue.index}] {clue.text}")

    parts = ["=== PUZZLE CLUES (retrieved from blockchain) ===\n"]
    for section, lines in sections.items():
        if lines:
            parts.append(f"[{section} CLUES]")
            parts.extend(lines)
            parts.append("")

    parts.append("Analyze all clues. Reason step by step. Then state your answer.")
    return "\n".join(parts)


def reason(clues: list[Clue]) -> str:
    """
    Send clues to Claude, extract the final answer.
    Returns the answer string (e.g. "penguin").
    """
    prompt = build_prompt(clues)

    message = client.messages.create(
        model="claude-opus-4-5",
        max_tokens=512,
        messages=[{"role": "user", "content": prompt}],
        system=SYSTEM_PROMPT,
    )

    response_text = message.content[0].text
    print(f"\n[LLM reasoning]\n{response_text}\n")

    # Extract answer
    for line in reversed(response_text.splitlines()):
        line = line.strip()
        if line.upper().startswith("ANSWER:"):
            answer = line.split(":", 1)[1].strip().lower()
            print(f"[LLM] Extracted answer: '{answer}'")
            return answer

    raise ValueError(f"Could not extract ANSWER from LLM response:\n{response_text}")
