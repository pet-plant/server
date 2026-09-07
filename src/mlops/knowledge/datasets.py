"""Experiment datasets — files in this repository, published to Langfuse.

Owner: TODO

Same rule as prompts (:mod:`mlops.knowledge.publishing`): **the repository is the
source of truth**, Langfuse holds the runs and the scores. A dataset edited only
in the UI cannot be reviewed in a pull request, and a run six months old cannot
be re-created from it.

## Layout

One file per dataset, in ``data/knowledge/``. The **file stem is the dataset
name**, so there is no mapping to keep in sync:

```
data/knowledge/research-documents.toml   ->  Langfuse dataset "research-documents"
```

TOML rather than JSON because these are hand-written documents: multi-line
strings survive paragraphs without ``\\n`` escaping, and comments are allowed.
``tomllib`` is in the standard library, so this costs no dependency.

```toml
description = "…"

[[items]]
id = "spath"                 # stable, so a re-sync updates rather than duplicates
species_code = "spath"
scientific_name = "Spathiphyllum wallisii"
common_name = "Peace lily"
document_title = "Watering, light and common problems"
document_body = \"\"\"
…the research text…
\"\"\"
```

Every key except ``id`` is a prompt variable
(:data:`~mlops.knowledge.contract.PROMPT_VARIABLES`) and is checked against that
list, so a dataset written for an older variable set fails at load rather than
producing a run where the model never saw the document.

## Datasets belong to the component, not to an agent version

They live here rather than under ``agents/<version>/`` on purpose: v1 and v2 have
to be judged on the *same* documents or their runs are not comparable. Prompts
are per version; the questions they are asked are not.
"""

from __future__ import annotations

import tomllib
from dataclasses import dataclass
from typing import Any

from core.config import PROJECT_ROOT
from mlops.client import get_client
from mlops.knowledge.contract import PROMPT_VARIABLES
from mlops.settings import Component

COMPONENT = Component.KNOWLEDGE

#: Where dataset files live. One file per dataset, stem = dataset name.
DATA_DIR = PROJECT_ROOT / "data" / "knowledge"


@dataclass(frozen=True)
class DatasetItem:
    """One research document, as one experiment item."""

    id: str
    #: The prompt variables, exactly. What the agent's template is compiled with.
    input: dict[str, Any]


@dataclass(frozen=True)
class Dataset:
    """One dataset file, loaded."""

    name: str
    description: str
    items: list[DatasetItem]


def available() -> list[str]:
    """Every dataset name that has a file, sorted."""
    if not DATA_DIR.is_dir():
        return []
    return sorted(p.stem for p in DATA_DIR.glob("*.toml"))


def load(name: str) -> Dataset:
    """Read one dataset file and check every item against the prompt contract.

    Raises:
        FileNotFoundError: no such dataset, naming the ones that do exist.
        ValueError: an item's keys do not match :data:`PROMPT_VARIABLES`.
    """
    path = DATA_DIR / f"{name}.toml"
    if not path.is_file():
        raise FileNotFoundError(f"no dataset {name!r} in {DATA_DIR}; have {available()}")
    raw = tomllib.loads(path.read_text("utf-8"))

    expected = set(PROMPT_VARIABLES)
    items = []
    for position, entry in enumerate(raw.get("items", []), start=1):
        entry = dict(entry)
        item_id = str(entry.pop("id", "") or f"{name}-{position}")
        keys = set(entry)
        if keys != expected:
            raise ValueError(
                f"{path}: item {item_id!r} has keys {sorted(keys)}, but the prompt "
                f"contract is {sorted(expected)} "
                f"(missing {sorted(expected - keys)}, extra {sorted(keys - expected)})"
            )
        items.append(DatasetItem(id=item_id, input=entry))

    if not items:
        raise ValueError(f"{path}: no [[items]]")
    return Dataset(name=name, description=str(raw.get("description", "")).strip(), items=items)


def sync(name: str) -> Dataset:
    """Publish a dataset file to Langfuse, then return what was published.

    Idempotent through the stable item ids: re-running updates each item in
    place rather than accumulating near-duplicates, so editing one document does
    not silently strand the runs that were scored on the old wording — Langfuse
    versions the dataset instead.

    Items removed from the file are **not** deleted in Langfuse. Deleting one
    would break the runs that reference it; retire it in the UI if you mean to.
    """
    dataset = load(name)
    client = get_client(COMPONENT)
    client.create_dataset(name=dataset.name, description=dataset.description or None)
    for item in dataset.items:
        client.create_dataset_item(
            dataset_name=dataset.name,
            id=item.id,
            input=item.input,
            metadata={"source": f"data/knowledge/{dataset.name}.toml"},
        )
    client.flush()
    return dataset
