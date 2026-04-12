# Usage Guide

Tutorials for submitting optimization jobs to the Skynet service. For service operators, see the [main README](../README.md).

## Prerequisites
- The Skynet service running (locally via `uv run python main.py` or deployed)
- Python environment with `dspy` and `requests` installed

### Quick Setup with `uv`
```bash
cd backend/usage_guide
uv venv .venv
source .venv/bin/activate
uv pip install -r pyproject.toml
```

## Notebooks

| # | Notebook | Dataset | What it teaches |
|---|----------|---------|-----------------|
| 1 | [01_quickstart.ipynb](01_quickstart.ipynb) | GSM8K (math) | End-to-end: submit, monitor, results, load & test optimized program |
| 2 | [02_grid_search.ipynb](02_grid_search.ipynb) | HotPotQA (multi-hop QA) | Compare model pairs via grid search, analyze per-pair results |
| 3 | [03_creative_tasks.ipynb](03_creative_tasks.ipynb) | TMDB Movies (taglines) | Multi-field signatures, LLM-as-judge metrics, code validation, serve API |

Start with notebook 1. Each notebook builds on new concepts — not just different data.

## Shared Client

All notebooks import from `skynet_client.py`:
- **`DSPyServiceClient`** — HTTP client for every API endpoint
- **`JobMonitor`** — real-time progress polling with formatted output
- **`serialize_source`** — serialize DSPy signatures and metrics to source code strings

## Datasets

| File | Rows | Task | Structure |
|------|------|------|-----------|
| `data/gsm8k.json` | 100 | Math reasoning | question → answer |
| `data/hotpotqa.json` | 100 | Multi-hop QA | question → answer |
| `data/tmdb_movies_150.json` | 150 | Tagline generation | overview + keywords + genres → tagline |

Datasets live at the repo root in `data/`. From a notebook:
```python
with open(Path("../../data/gsm8k.json")) as f:
    dataset = json.load(f)
```

Full interactive API docs: `http://localhost:8000/reference`
