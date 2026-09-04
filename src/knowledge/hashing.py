"""Content hashing for change-detection between a document and its metrics."""

import hashlib


def content_hash(body: str) -> str:
    """SHA-256 (hex) of the research text exactly as fed to the LLM.

    Stored on ``research_document`` and snapshotted onto ``metric_set`` at
    generation time, so a metric set can be compared against the text it was
    produced from without relying on timestamps.
    """
    return hashlib.sha256(body.encode("utf-8")).hexdigest()
