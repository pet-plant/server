"""Agent v1: one prompt, one shot, a repair loop.

Owner: TODO · Langfuse prompts: ``knowledge/v1/*``

Self-contained on purpose. Nothing here may import another agent version, and
nothing outside may import into this package past :data:`AGENT` — two versions
coexist precisely so that changing one cannot disturb the other.
"""

from mlops.knowledge.agents.v1.agent import AGENT, GENERATE_PROBES, VERSION

__all__ = ["AGENT", "GENERATE_PROBES", "VERSION"]
