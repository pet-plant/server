# `mlops` — LLM execution and experiments

Every VLM / LLM call in the system goes through here, and so does every
experiment behind those calls. **Langfuse** manages the prompts.

> Status: **templates only.** Function bodies are `raise NotImplementedError`
> and the per-component contents are placeholders for their owners to fill in.
> The dependencies are installed, so a component owner can start writing.

## The stack

Pinned in `pyproject.toml` because it lives here and nowhere else:

| Package | For |
|---|---|
| `langfuse` | Prompt management, tracing, datasets, scores. Ships a LangChain callback handler, so traces come off the chain rather than being hand-rolled |
| `langchain` | Chain / agent construction. v1 bundles `langgraph`, so a component that needs a graph already has one |
| `langchain-openai` | The OpenAI-compatible integration — reaches both the on-prem VLM (vLLM, `VLM_API_BASE`) and the external text LLM (`LLM_API_BASE`) |

Both model endpoints speak the OpenAI protocol, so they differ only by base URL,
key and model id — one `ChatOpenAI` shape covers both.

## Not a bounded context

`mlops` owns no Postgres schema and no HTTP router. It is a shared library
alongside `core` that the LLM-using contexts depend on:

```
assessment ─┐
advice     ─┼─▶ mlops ─┬─▶ Langfuse  (prompts / traces / datasets / scores)
knowledge  ─┤          └─▶ VLM (on-prem, vLLM) · LLM (external, text only)
registry   ─┘
```

**The dependency is one-way.** `mlops` never imports a bounded context — its
entry points take plain values and dataclasses defined here, and the calling
context maps its own models onto them (e.g. `assessment` flattens a
`knowledge.schemas.ProbeRead` into an `mlops.assessment.ProbeInput`). Without
this rule `knowledge → mlops → knowledge` closes a cycle.

## One package per component, one owner each

Each component is **its own Langfuse project** with its own key pair, and each
package is **self-contained**: it decides how it handles prompts, calls its
model, traces and scores. There is deliberately no shared abstraction layer over
Langfuse — the four owners can work in parallel without agreeing on one, and
without a change to shared code rippling across all four.

| Package | Model | Entry point the context calls | Owner |
|---|---|---|---|
| `mlops/assessment/` | VLM | `run_probe(ProbeInput) -> ProbeVerdict` | TODO |
| `mlops/advice/` | LLM | `generate_advice(AdviceInput) -> AdviceResult` | TODO |
| `mlops/knowledge/` | LLM | `generate_probes(...) -> GenerateProbesResult` | TODO |
| `mlops/registry/` | VLM | `identify_species(...) -> SpeciesGuess` | TODO |

### The template inside each package

| File | Holds |
|---|---|
| `prompts.py` | The prompt names in that Langfuse project, and how to fetch a version. One place, so `runtime` and `experiment` agree |
| `runtime.py` | **Execution code.** Resolve the `production` prompt → call the model → parse → trace. Takes `label` / `version` / `overrides` so experiments can drive it |
| `experiment.py` | **Experiment code.** Runs `runtime`'s function over a Langfuse dataset as a dataset run. `python -m mlops.<component>.experiment` |
| `evaluators.py` | That component's scorers |

Add modules beyond these as the work needs them — an agent graph, a parser, a
retry policy. That is the owner's call.

**`experiment.py` calls `runtime.py`'s own function**, with a pinned prompt
version rather than the `production` label. Experiments and production therefore
share one code path, so a prompt that scored well cannot behave differently once
its label moves. This is why every `runtime` entry point takes `label` /
`version` / `overrides` — keep that shape.

## What is shared (and it is only this)

| Module | Holds |
|---|---|
| `settings.py` | `Component(StrEnum)` — subpackage, Langfuse project and key pair keyed by one value — plus `PRODUCTION_LABEL` and `credentials_for()` |
| `client.py` | `get_client(component)` — a Langfuse client pointed at the right project. Credential plumbing, not an abstraction over the SDK |

## How prompts are managed

Everything an in-house prompt registry would carry lives in Langfuse instead:

| Concern | Where it lives |
|---|---|
| Prompt text | Langfuse prompt version |
| Hyper-parameters (model, temperature, …) | That version's `config` JSON |
| Version identity | Langfuse version number |
| What is live | The `production` label |
| Promotion / rollback | Moving that label — old versions are never deleted |
| Eval set / run / scores | Langfuse Dataset / Dataset Run / Scores |

The request path resolves by **label**; experiments pin a **version**.

**No experiment data is written to Postgres.** If a context later needs to
correlate its own rows with a trace, the minimal move is one `langfuse_trace_id`
column on that context's table — every `runtime` result carries the id for
exactly this.

## Config

`LANGFUSE_HOST` plus a public/secret key pair per component, declared in
`core.config.Settings` and `.env.example`. `VLM_*` / `LLM_*` supply the model
endpoints.

## Adding a component

1. Add a member to `Component` in `settings.py`.
2. Add its key pair to `core.config.Settings` and `.env.example`.
3. Register it in `settings.credentials_for()`.
4. Copy an existing component package as the template.
