"""Dataset files are the source of truth, so loading them must be strict.

The failure worth catching is an item written against an older set of prompt
variables: it would publish cleanly and produce a run where the model never saw
the document, which reads as a bad prompt rather than as the data mistake it is.
"""

from pathlib import Path

import pytest

from mlops.knowledge import datasets
from mlops.knowledge.contract import PROMPT_VARIABLES

ITEM = """
[[items]]
id = "spath"
species_code = "spath"
scientific_name = "Spathiphyllum wallisii"
common_name = "Peace lily"
document_title = "watering"
document_body = \"\"\"
The leaves droop when it dries out.

They recover within a day of a thorough watering.
\"\"\"
"""


@pytest.fixture
def data_dir(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    monkeypatch.setattr(datasets, "DATA_DIR", tmp_path)
    return tmp_path


def test_the_file_stem_is_the_dataset_name(data_dir: Path) -> None:
    (data_dir / "edge-cases.toml").write_text('description = "d"\n' + ITEM)

    assert datasets.available() == ["edge-cases"]
    assert datasets.load("edge-cases").name == "edge-cases"


def test_paragraphs_survive_the_round_trip(data_dir: Path) -> None:
    """`document_body` is quoted back verbatim, so its shape has to be preserved."""
    (data_dir / "d.toml").write_text(ITEM)

    body = datasets.load("d").items[0].input["document_body"]

    assert body.startswith("The leaves droop")
    assert "\n\n" in body  # the blank line between paragraphs is still there


def test_an_item_missing_a_prompt_variable_is_rejected(data_dir: Path) -> None:
    (data_dir / "d.toml").write_text(ITEM.replace('common_name = "Peace lily"\n', ""))

    with pytest.raises(ValueError, match="common_name"):
        datasets.load("d")


def test_an_item_with_an_unknown_key_is_rejected(data_dir: Path) -> None:
    """An extra key is either a typo or a variable the prompt does not have."""
    (data_dir / "d.toml").write_text(ITEM + 'expected_probes = 3\n')

    with pytest.raises(ValueError, match="expected_probes"):
        datasets.load("d")


def test_an_empty_dataset_is_rejected(data_dir: Path) -> None:
    (data_dir / "d.toml").write_text('description = "nothing here"\n')

    with pytest.raises(ValueError, match="no \\[\\[items\\]\\]"):
        datasets.load("d")


def test_an_unknown_dataset_names_the_ones_that_exist(data_dir: Path) -> None:
    (data_dir / "research-documents.toml").write_text(ITEM)

    with pytest.raises(FileNotFoundError, match="research-documents"):
        datasets.load("typo")


def test_the_shipped_dataset_loads_and_matches_the_contract() -> None:
    """The real file, checked the same way the bench would check it."""
    assert "research-documents" in datasets.available()

    dataset = datasets.load("research-documents")

    assert len(dataset.items) >= 2
    assert dataset.description
    for item in dataset.items:
        assert set(item.input) == set(PROMPT_VARIABLES)
        assert item.input["document_body"].strip()
