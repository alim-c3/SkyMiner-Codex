# Contributing to SkyMiner

## Principles

- Scientific guardrails first: the system produces **candidates**, not confirmed discoveries.
- Reproducibility: prefer deterministic behavior, cached artifacts, and versioned configuration.
- Modularity: new data sources should be adapters in `src/skyminer/ingestion/`.

## Development

- Python 3.11+ recommended.
- Install editable with dev deps:
  - `pip install -e ".[dev]"`
- Run local smoke:
  - `python -m skyminer.cli smoke-test`

## Testing

- Tests are designed to run offline.
- Live-network validations must be mockable and covered via mocks.

