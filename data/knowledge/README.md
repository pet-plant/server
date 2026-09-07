# data/knowledge/ — experiment datasets

One file per Langfuse dataset. **The file stem is the dataset name**, so nothing
maps names to files and nothing can drift:

```
research-documents.toml   ->  Langfuse dataset "research-documents"
```

These files are the source of truth. `mlops.knowledge.datasets.sync()` publishes
them, and every experiment run publishes before it runs — so a dataset edited
here is what the next run scores. Do not edit dataset items in the Langfuse UI:
a change made there is invisible to review and cannot be re-created.

## Adding a dataset

Copy `research-documents.toml`, rename it, and change the items. Then:

```bash
PYTHONPATH=src uv run python -m mlops.knowledge.agents.v1.experiment \
    --run-name first-look --dataset <your-file-stem>
```

`--dataset` only accepts names that have a file here, so a typo fails at the
argument rather than by creating an empty dataset in Langfuse.

## What an item must contain

Every key except `id` is a prompt variable
(`mlops.knowledge.contract.PROMPT_VARIABLES`), and the loader checks the set
exactly — an item written against an older variable list fails on load instead of
producing a run where the model never saw the document.

| Key | Is |
|---|---|
| `id` | Stable identifier. A re-sync **updates** this item; change the id and you get a second one |
| `species_code` | The internal code, `spath` |
| `scientific_name` | `Spathiphyllum wallisii` |
| `common_name` | `Peace lily` |
| `document_title` | The title of the research document |
| `document_body` | The research text, verbatim — a TOML `"""…"""` string |

`document_body` is quoted back by the agent as `evidence_quote` and matched
against this exact text, so write it as the real thing rather than as notes.

## Nothing is an expected output

There is no `expected_output` field, deliberately. Nobody can write the one
correct probe set for a document, and a metric built on a made-up answer is worse
than no metric: it would move a `production` label on evidence no one believes.
Automatic scores measure well-formedness only; a person judges the probes, and
that verdict is what the accept-rate per prompt version is built from.

## Write the awkward parts in

The most useful documents are the ones that say what is **normal** as well as
what is wrong — routine leaf ageing, cosmetic dust, a droop that is the plant's
own warning rather than damage. Those sentences are what a probe's `not_this`
guard is built from, and a dataset without them cannot tell a careful prompt from
a trigger-happy one.

## Removing an item

Deleting it here does not delete it in Langfuse, on purpose: a run that scored it
still references it. Retire it in the Langfuse UI if you mean to.
