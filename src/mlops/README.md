# `mlops` — LLM execution and experiments

Every VLM / LLM call in the system goes through here, and so does every
experiment behind those calls. **Langfuse** manages the prompts.

> Status: `mlops/knowledge/` is **implemented** — the probe-generation agent, its
> validation, its human-review score and its experiment runner. The other three
> packages are still **templates**: function bodies are `raise NotImplementedError`
> and the contents are placeholders for their owners. Read `knowledge/` as the
> worked example of the shape the others follow.

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
| `mlops/knowledge/` | LLM | `generate_probes(GenerateProbesInput) -> GenerateProbesResult` | TODO |
| `mlops/registry/` | VLM | `identify_species(...) -> SpeciesGuess` | TODO |

### The template inside each package

`knowledge/` is the worked example, and its shape is the one to copy:

| Path | Holds |
|---|---|
| `contract.py` | The I/O types and the `ProbeAgent` protocol every version implements |
| `registry.py` | Which versions exist; `get_agent(version)` — the caller's one choice |
| `publishing.py` | Prompt files → Langfuse versions, idempotently, **never labelled** |
| `agents/<v>/agent.py` | One interchangeable implementation |
| `agents/<v>/prompts/<name>/` | Its prompt text and config, as files |
| `agents/<v>/experiment.py` | Its bench. `python -m mlops.<component>.agents.<v>.experiment` |
| `evaluators.py` | Scorers over the contract's result type — shared across versions |

Add modules beyond these as the work needs them. That is the owner's call.

### Two levers, at different speeds

| Change | Where | Deploy |
|---|---|---|
| Prompt text of a live version | edit the file → run the experiment → move `production` in Langfuse | **no** |
| Which agent structure runs | `DEFAULT_VERSION` in `registry.py` | yes |

Agent versions each own a **namespace** of prompt names
(`knowledge/v1/generate-probes`, `knowledge/v2/draft`), so every version has its
own independent `production` label. Promoting v2's prompt cannot move what v1
runs on — which is what makes keeping old versions around safe.

### Validate before you return

`knowledge/` sets the pattern the others should follow: the output model is
Pydantic, it is handed to the LLM as a JSON schema through
`with_structured_output`, and it is validated again on the way back. A failure
becomes a **repair message** — the model sees its own answer's errors and fixes
them — and a set that never validates raises rather than returning. There is no
"mostly valid" path out of a runtime module.

Three layers, each catching what the one before it cannot:

| Layer | Catches |
|---|---|
| JSON schema in the request | Missing fields, wrong types |
| Pydantic validators | Domain rules: slug format, unique identifiers, ordered durations |
| A grounding check against the source | Hallucination — output that cites text the input does not contain |

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

## Evaluation: what a machine can score, and what it cannot

Not every component has an automatic quality metric, and pretending otherwise is
worse than admitting it — a scorer nobody believes still moves a `production`
label. `knowledge` is the clear case: whether a generated probe is botanically
right is a human judgement, so it is scored by a human.

| | Automatic | Human |
|---|---|---|
| What it measures | Well-formedness: did it validate, how many repair rounds, coverage | Quality: is this right, is it usable |
| Where it runs | `evaluators.py`, every dataset run | A person reviewing, in the authoring UI or a Langfuse annotation queue |
| What it gates | Whether a version is a candidate at all | Whether it ships |

For `knowledge`, the review surface is the one people already use: a superuser
approving or rejecting a draft probe set in the `knowledge` API writes the same
Langfuse score (`probe_set_human_review`) that an annotation queue would. The
verdict is durable in Postgres first; the copy in Langfuse is best-effort and
never fails the reviewer's request. Over time it answers the question that
matters — *what fraction of what prompt v7 produced did people accept?*

**No experiment data is written to Postgres.** If a context later needs to
correlate its own rows with a trace, the minimal move is one `langfuse_trace_id`
column on that context's table — every `runtime` result carries the id for
exactly this.

## Config

`LANGFUSE_HOST` plus a public/secret key pair per component, declared in
`core.config.Settings` and `.env.example`. `VLM_*` / `LLM_*` supply the model
endpoints and their credentials.

**No model name lives in the environment.** Which model a prompt runs on is part
of that prompt version's `config`, so it is versioned with the text it was tuned
against, and the model a past run used is recoverable from the version it names.
An env-level default would quietly reintroduce a second source: a prompt missing
`model` would still run, on whatever the deployment happened to say, and two runs
of "v7" could differ by machine — which is exactly what makes comparing versions
meaningless. A prompt config with no `model` raises instead.

### What `knowledge` needs in Langfuse

A chat prompt named **`knowledge/generate-probes`** with the `production` label,
compiled with exactly these variables (`prompts.GENERATE_PROBES_VARIABLES`):

`species_code`, `scientific_name`, `common_name`, `document_title`, `document_body`

Its `config` carries the hyper-parameters — `model`, `temperature`, `max_tokens`,
`max_attempts` (the repair budget), and anything else is passed through to the
client. A dataset named `knowledge-research-documents` backs the experiment
runner; its items have no `expected_output`, because nobody can write the one
correct probe set for a document.

### Where prompt text lives

**In this repository**, under `agents/<version>/prompts/`, and published from
there by `publishing.sync()`. Prompts are not written in the Langfuse UI: a
prompt change is a diff someone reviews, its history sits with the code that
depends on it, and a Langfuse project can be rebuilt from scratch.

Langfuse owns what a repository cannot — the version registry, the traces and
dataset runs each version produced, the human scores on them, and the
`production` label that decides what is live.

Publishing is **idempotent and never deploys**: an unchanged prompt is not
republished (so version numbers count decisions, not invocations), and a new
version arrives unlabelled. It goes live only when a person moves `production`
after reading the run.

## Bringing up a component's Langfuse project

Nothing here works until the project exists and its keys are in `.env`. Only the
first step is manual — Langfuse Cloud has no API for creating a project, so the
project and its key pair are made in the web UI. (Self-hosted Langfuse can do
this headlessly with its `LANGFUSE_INIT_*` variables at container start; see the
Langfuse self-hosting docs.)

1. **In the Langfuse UI**, create a project named after the component
   (`knowledge`), then *Settings → API keys* → create one. One project per
   component is the whole design — sharing one project across components mixes
   their traces and loses the per-component accept-rate.
2. **In `.env`**, set `LANGFUSE_HOST` to your region and the component's key
   pair. The SDK's own `LANGFUSE_PUBLIC_KEY` / `LANGFUSE_SECRET_KEY` /
   `LANGFUSE_BASE_URL` are **not** read by this project; the per-component names
   in `.env.example` are.
3. **Run an experiment.** It publishes the prompt files and scores them:
   `uv run python -m mlops.knowledge.agents.v1.experiment --run-name v1-baseline`
4. **Read the run** in Langfuse and judge the probes yourself.
5. **Promote** — move the `production` label onto the version you accepted.

### Experiments need no database

Steps 3–5 touch Postgres, MinIO and the web process not at all — prompts,
datasets, runs, traces and scores all live in Langfuse. Two API keys and a laptop
are the whole requirement, with nothing from `compose.yaml` running.

That is a property worth keeping, and it is easy to break with one convenience
import: `tests/mlops/test_no_database.py` fails if importing the experiment CLI
ever pulls in `core.db`, SQLAlchemy or a bounded context.

## Adding a component

1. Add a member to `Component` in `settings.py`.
2. Add its key pair to `core.config.Settings` and `.env.example`.
3. Register it in `settings.credentials_for()`.
4. Copy an existing component package as the template.
5. Create its Langfuse project and keys, as above.
