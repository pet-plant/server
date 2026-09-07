# scripts/

Operational and one-off scripts: local bootstrap, MinIO bucket creation, seed
data, ad-hoc data fixes, diagnostics.

- Recurring batch work belongs in `src/main_worker.py`, not here.
- Anything that must be reproducible or audited belongs in a context, not here.
- **Prompts and experiments are not scripts.** Prompts live with the agent
  version that owns them (`src/mlops/<component>/agents/<version>/prompts/`),
  experiment datasets live in `data/<component>/`, and both are published from
  there by the experiment itself.
