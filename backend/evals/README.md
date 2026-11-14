# Summary agent evals

A hand-run `pydantic_evals` dataset of 10 Romanian cases for the post-call summary agent (design 2026-11-08 §9). It calls the real model on DeepInfra (`SUMMARY_MODEL`, also used as the judge), so it costs money and CI never runs it. Set `DEEPINFRA_API_KEY` in `backend/.env`, then run `uv run python -m evals.summary` from `backend/`; it prints a score table per case and evaluator.
