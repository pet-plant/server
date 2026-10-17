"""Common statistical metrics, confusion matrices, and calculation utilities."""

from __future__ import annotations

import difflib
import json
import math
import re
import urllib.request
from collections import Counter
from dataclasses import dataclass
from typing import Any



@dataclass
class ConfusionMatrix:
    """Standard binary confusion matrix with safe division handling."""

    tp: int = 0
    tn: int = 0
    fp: int = 0
    fn: int = 0

    @property
    def total(self) -> int:
        return self.tp + self.tn + self.fp + self.fn

    @property
    def accuracy(self) -> float:
        if self.total == 0:
            return 1.0
        return round((self.tp + self.tn) / self.total, 4)

    @property
    def precision(self) -> float:
        predicted_positives = self.tp + self.fp
        if predicted_positives == 0:
            return 1.0 if self.fn == 0 else 0.0
        return round(self.tp / predicted_positives, 4)

    @property
    def recall(self) -> float:
        actual_positives = self.tp + self.fn
        if actual_positives == 0:
            return 1.0
        return round(self.tp / actual_positives, 4)

    @property
    def f1_score(self) -> float:
        p = self.precision
        r = self.recall
        if (p + r) == 0.0:
            return 0.0
        return round(2.0 * (p * r) / (p + r), 4)

    def to_dict(self) -> dict[str, Any]:
        return {
            "tp": self.tp,
            "tn": self.tn,
            "fp": self.fp,
            "fn": self.fn,
            "total": self.total,
            "accuracy": self.accuracy,
            "precision": self.precision,
            "recall": self.recall,
            "f1_score": self.f1_score,
        }


def calculate_macro_f1(class_f1_scores: dict[str, float]) -> float:
    """Calculate unweighted macro-average F1 score across classes."""
    if not class_f1_scores:
        return 0.0
    scores = list(class_f1_scores.values())
    return round(sum(scores) / len(scores), 4)


def calculate_iou(
    box_a: tuple[int, int, int, int] | list[int],
    box_b: tuple[int, int, int, int] | list[int],
) -> float:
    """
    Calculate Intersection over Union (IoU) for two boxes formatted as [x, y, w, h].
    """
    ax, ay, aw, ah = box_a
    bx, by, bw, bh = box_b

    x1 = max(ax, bx)
    y1 = max(ay, by)
    x2 = min(ax + aw, bx + bw)
    y2 = min(ay + ah, by + bh)

    inter_w = max(0, x2 - x1)
    inter_h = max(0, y2 - y1)
    inter_area = inter_w * inter_h

    area_a = aw * ah
    area_b = bw * bh
    union_area = area_a + area_b - inter_area

    if union_area <= 0:
        return 0.0
    return round(inter_area / union_area, 4)


def calculate_jaccard(set_a: set[Any], set_b: set[Any]) -> float:
    """Calculate Jaccard similarity coefficient between two sets."""
    if not set_a and not set_b:
        return 1.0
    intersection = len(set_a.intersection(set_b))
    union = len(set_a.union(set_b))
    if union == 0:
        return 1.0
    return round(intersection / union, 4)


def calculate_percentile(values: list[float], percentile: float) -> float:
    """Calculate p-th percentile from a list of numbers."""
    if not values:
        return 0.0
    sorted_values = sorted(values)
    k = (len(sorted_values) - 1) * (percentile / 100.0)
    f = math.floor(k)
    c = math.ceil(k)
    if f == c:
        return round(float(sorted_values[int(k)]), 2)
    d0 = sorted_values[int(f)] * (c - k)
    d1 = sorted_values[int(c)] * (k - f)
    return round(float(d0 + d1), 2)


def calculate_cosine_similarity(vec_a: list[float], vec_b: list[float]) -> float:
    """Compute cosine similarity between two float vectors in [0.0, 1.0]."""
    if not vec_a or not vec_b or len(vec_a) != len(vec_b):
        return 0.0
    dot = sum(a * b for a, b in zip(vec_a, vec_b))
    norm_a = math.sqrt(sum(a * a for a in vec_a))
    norm_b = math.sqrt(sum(b * b for b in vec_b))
    if norm_a == 0.0 or norm_b == 0.0:
        return 0.0
    return max(0.0, min(1.0, dot / (norm_a * norm_b)))


def get_ollama_embedding(
    text: str,
    host: str = "http://localhost:11434",
    model: str = "",
    timeout_seconds: float = 8.0,
) -> list[float] | None:
    """Fetch a text embedding from Ollama for the configured model."""
    if not model.strip():
        return None
    if not text.strip():
        return None
    try:
        url = f"{host.rstrip('/')}/api/embeddings"
        payload = json.dumps({"model": model, "prompt": text.strip()}).encode("utf-8")
        req = urllib.request.Request(
            url,
            data=payload,
            headers={"Content-Type": "application/json"},
        )
        with urllib.request.urlopen(req, timeout=timeout_seconds) as resp:
            data = json.loads(resp.read().decode("utf-8"))
            return data.get("embedding")
    except Exception:
        return None


def get_openai_embedding(
    text: str,
    *,
    api_base: str,
    api_key: str,
    model: str,
    timeout_seconds: float = 8.0,
) -> list[float] | None:
    """Fetch a text embedding from an OpenAI-compatible embeddings endpoint."""
    if not text.strip() or not api_base.strip() or not api_key.strip() or not model.strip():
        return None
    try:
        url = f"{api_base.rstrip('/')}/embeddings"
        payload = json.dumps({"model": model, "input": text.strip()}).encode("utf-8")
        req = urllib.request.Request(
            url,
            data=payload,
            headers={
                "Content-Type": "application/json",
                "Authorization": f"Bearer {api_key}",
            },
        )
        with urllib.request.urlopen(req, timeout=timeout_seconds) as resp:
            data = json.loads(resp.read().decode("utf-8"))
            rows = data.get("data") or []
            if not rows:
                return None
            embedding = rows[0].get("embedding")
            return embedding if isinstance(embedding, list) else None
    except Exception:
        return None


def _configured_embedding(text: str) -> tuple[list[float] | None, str]:
    """Embed ``text`` with the model named by application settings."""
    try:
        from core.config import get_settings
        from evaluation.common.config import runtime_models

        models = runtime_models(get_settings())
    except Exception:
        return None, "token_vector_fallback"
    if not models.embedding_model:
        return None, "token_vector_fallback"
    if models.embedding_provider == "ollama":
        vector = get_ollama_embedding(
            text, host=models.embedding_host, model=models.embedding_model
        )
        return vector, f"ollama_{models.embedding_model}"
    vector = get_openai_embedding(
        text,
        api_base=models.embedding_api_base,
        api_key=models.embedding_api_key,
        model=models.embedding_model,
    )
    return vector, f"openai_{models.embedding_model}"


def calculate_token_cosine(text_a: str, text_b: str) -> float:
    """Fallback token frequency cosine similarity between two texts in [0.0, 1.0]."""
    tokens_a = re.findall(r"\b\w+\b", text_a.lower())
    tokens_b = re.findall(r"\b\w+\b", text_b.lower())
    if not tokens_a and not tokens_b:
        return 1.0
    if not tokens_a or not tokens_b:
        return 0.0
    ca = Counter(tokens_a)
    cb = Counter(tokens_b)
    words = set(ca.keys()).union(set(cb.keys()))
    dot = sum(ca[w] * cb[w] for w in words)
    norm_a = math.sqrt(sum(v * v for v in ca.values()))
    norm_b = math.sqrt(sum(v * v for v in cb.values()))
    if norm_a == 0.0 or norm_b == 0.0:
        return 0.0
    return dot / (norm_a * norm_b)


def calculate_text_similarity(
    expected: str,
    actual: str,
    *,
    ollama_host: str | None = None,
    ollama_model: str | None = None,
) -> dict[str, Any]:
    """
    Calculate quantitative similarity and difference between expected and actual text responses.

    Returns percentages (0.0 to 100.0) for:
      - semantic_similarity: Cosine similarity via the configured embedding model,
        or token-cosine fallback
      - lexical_similarity: SequenceMatcher character/word alignment similarity
      - token_overlap: Jaccard similarity of word sets
      - composite_similarity: Primary similarity score
      - response_difference: Percentage difference (100.0 - composite_similarity)
      - method: Identifies the configured embedding model, or the token fallback
    """
    exp_clean = expected.strip()
    act_clean = actual.strip()

    if exp_clean == act_clean:
        return {
            "semantic_similarity": 100.0,
            "lexical_similarity": 100.0,
            "token_overlap": 100.0,
            "composite_similarity": 100.0,
            "response_difference": 0.0,
            "method": "exact_match",
        }

    if not exp_clean or not act_clean:
        return {
            "semantic_similarity": 0.0,
            "lexical_similarity": 0.0,
            "token_overlap": 0.0,
            "composite_similarity": 0.0,
            "response_difference": 100.0,
            "method": "empty_text",
        }

    # 1. Lexical SequenceMatcher similarity
    lex_sim = round(
        difflib.SequenceMatcher(None, exp_clean.lower(), act_clean.lower()).ratio() * 100.0,
        2,
    )

    # 2. Token Jaccard overlap
    words_exp = set(re.findall(r"\b\w+\b", exp_clean.lower()))
    words_act = set(re.findall(r"\b\w+\b", act_clean.lower()))
    tok_overlap = round(calculate_jaccard(words_exp, words_act) * 100.0, 2)

    # 3. Semantic similarity via the embedding model named in settings.
    # An explicit model argument is only for a caller that already resolved one.
    if ollama_model:
        host = ollama_host or "http://localhost:11434"
        emb_exp = get_ollama_embedding(exp_clean, host=host, model=ollama_model)
        emb_act = get_ollama_embedding(act_clean, host=host, model=ollama_model)
        method_name = f"ollama_{ollama_model}"
    else:
        emb_exp, method_name = _configured_embedding(exp_clean)
        emb_act, _ = _configured_embedding(act_clean)

    if emb_exp and emb_act and len(emb_exp) == len(emb_act):
        raw_sim = calculate_cosine_similarity(emb_exp, emb_act)  # in [0.0, 1.0]
        sem_sim = round(raw_sim * 100.0, 2)
        method = method_name
        comp_sim = sem_sim
        raw_comp_sim = raw_sim
    else:
        # Fallback to token frequency cosine
        raw_tok_cos = calculate_token_cosine(exp_clean, act_clean)
        sem_sim = round(raw_tok_cos * 100.0, 2)
        method = "token_vector_fallback"
        # Blend lexical and token cosine for fallback composite
        raw_comp_sim = (0.5 * (lex_sim / 100.0)) + (0.5 * raw_tok_cos)
        comp_sim = round(raw_comp_sim * 100.0, 2)

    # Formula: Difference (%) = (100 - (similarity) * 100) where similarity is in [0.0, 1.0]
    resp_diff = round(max(0.0, 100.0 - (raw_comp_sim * 100.0)), 2)

    return {
        "raw_similarity": round(raw_comp_sim, 4),
        "semantic_similarity": sem_sim,
        "lexical_similarity": lex_sim,
        "token_overlap": tok_overlap,
        "composite_similarity": comp_sim,
        "response_difference": resp_diff,
        "method": method,
    }
