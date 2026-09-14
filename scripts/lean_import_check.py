"""Lean-import audit: the base install must boot without the ML stack.

Blocks numpy/pandas/sklearn/scipy/spacy/nltk/tiktoken/torch/
sentence-transformers/openai/anthropic, then imports the full app.
Any hard ML import in backend/ fails this check. Run in CI after pip install.
"""
import sys
import os

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

BLOCKED = {"numpy", "pandas", "sklearn", "scipy", "spacy", "nltk", "tiktoken",
           "torch", "sentence_transformers", "openai", "anthropic"}


class _Blocker:
    def find_module(self, name, path=None):
        root = name.split(".")[0]
        if root in BLOCKED:
            return self
        return None

    def load_module(self, name):
        raise ImportError(f"lean-import audit: '{name}' is ML-stack (requirements-ml.txt); "
                          f"use lazy import + fallback instead")


sys.meta_path.insert(0, _Blocker())
for m in list(sys.modules):
    if m.split(".")[0] in BLOCKED:
        del sys.modules[m]

import main  # noqa: E402
from backend.modules.registry import get_registry  # noqa: E402

assert len(get_registry()) == 35
print(f"lean-import OK: app boots with zero ML-stack imports ({len(get_registry())} modules)")
