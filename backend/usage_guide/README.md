# Usage Guide

Tutorials for submitting optimization jobs to the Skynet service. For service operators, see the [main README](../README.md).

## Prerequisites
- The Skynet service running (locally via `python main.py` or deployed)
- Python environment with `dspy` and `requests` installed

### Quick Setup
```bash
cd backend/usage_guide
python -m venv .venv
source .venv/bin/activate
pip install -e .
```

The `pyproject.toml` in this folder declares the notebook deps (`dspy`,
`pandas`, `openpyxl`, `requests`, `jupyter`); installing with `-e .` keeps
the kernel in sync without dragging in the full backend service.

### Environment Variables

| Name | Purpose | Default |
|------|---------|---------|
| `DSPY_SERVICE_URL` | Skynet API base URL | `http://localhost:8000` |
| `DSPY_LM_BASE_URL` | LLM gateway base URL (use this for self-hosted endpoints) | `https://api.openai.com/v1` |
| `LM_API_KEY` | Bearer token for the LLM gateway | — (required) |
| `OPENAI_API_KEY` | Legacy fallback name; honored if `LM_API_KEY` is unset | — |

For self-hosted gateways (vLLM, Ollama, internal proxies), set
`DSPY_LM_BASE_URL` to the gateway URL and `LM_API_KEY` to whatever token the
gateway expects (any non-empty string works for endpoints that don't
authenticate per-user).

### Air-Gap / On-Prem Install

The notebooks have no `!pip install` magics — install once via the local
`pyproject.toml`. To resolve packages from an internal Artifactory mirror
instead of public PyPI, see the snippet at the top of `pyproject.toml`
(pip.conf, `PIP_INDEX_URL`, or a `[[tool.uv.index]]` block).

## Notebooks

| # | Notebook | Dataset | What it teaches |
|---|----------|---------|-----------------|
| 1 | [01_quickstart.ipynb](01_quickstart.ipynb) | `math_problems.json` (math) | End-to-end: submit, monitor, results, load & test optimized program |
| 2 | [02_grid_search.ipynb](02_grid_search.ipynb) | `wikidata_qa.json` (general QA) | Compare model pairs via grid search, analyze per-pair results |
| 3 | [03_creative_tasks.ipynb](03_creative_tasks.ipynb) | `nasa_missions.json` (multi-output) | Multi-field signatures, LLM-as-judge metrics, code validation, serve API |
| 4 | [04_advanced.ipynb](04_advanced.ipynb) | `uspto_patents.json` (multi-input + multi-label) | Multi-input fusion + multi-label outputs, composite Jaccard / macro-F1 metrics |
| 5 | [05_gepa_showcase.ipynb](05_gepa_showcase.ipynb) | `logic_puzzles.json` (constraint reasoning) | Structured reasoning, GEPA-driven prompt optimisation on a hard task |

Start with notebook 1. Each notebook builds on new concepts — not just different data.

## Shared Client

All notebooks import from `skynet_client.py`:
- **`DSPyServiceClient`** — HTTP client for every API endpoint
- **`JobMonitor`** — real-time progress polling with formatted output
- **`serialize_source`** — serialize DSPy signatures and metrics to source code strings

## Datasets

All five datasets are fully permissive — self-generated or distilled from public-domain factual sources. See [`data/SOURCES.md`](../../data/SOURCES.md) for licensing details and per-file provenance.

| File | Rows | Task | Structure |
|------|------|------|-----------|
| `data/math_problems.json` | 100 | Math word problems | question → answer (numeric) |
| `data/wikidata_qa.json` | 100 | General-domain factual QA | question → answer |
| `data/nasa_missions.json` | 100 | Multi-output structured prediction | name + description → year + type + destination + status |
| `data/uspto_patents.json` | 100 | Multi-input + multi-label classification | title + abstract → category + subcategories + inventors + decade |
| `data/logic_puzzles.json` | 100 | Constraint-satisfaction reasoning | entities + attributes + clues → solution |

Datasets live at the repo root in `data/`. From a notebook:
```python
with open(Path("../../data/math_problems.json")) as f:
    dataset = json.load(f)
```

Full interactive API docs: `http://localhost:8000/reference`

## Hebrew Walkthrough

For a deeper, narrative walkthrough in Hebrew (covering the same client API,
metric design, and grid-search workflow), see
[`docs/dspy_client_guide_hebrew.pdf`](docs/dspy_client_guide_hebrew.pdf).
