# GAUA-17 GaugeFlow Social OS

Local software project for running a weekly Social OS cycle at GaugeFlow: validate initiative graph integrity, score team health signals, generate capacity-aware ritual planning, and export execution artifacts.

## Implemented Scope
- Domain model for members, initiatives, signal events, ritual slots, and weekly plan allocations.
- Validation for ownership, dependency existence, and cycle detection.
- Team health scoring engine from structured social signals.
- Priority and planning engine that allocates initiatives into ritual slots while enforcing slot and owner capacity.
- Exporters for CSV (initiative backlog), Markdown (operating summary), and JSON (weekly plan payload).
- CLI workflow for validate, health scoring, planning, critical-chain analysis, and artifact export.
- Unit tests for validation, planning constraints, scoring bounds, and exports.

## Project Layout
- `pyproject.toml`: package metadata and CLI entrypoint.
- `src/gaugeflow_social_os/models.py`: dataclass domain models.
- `src/gaugeflow_social_os/data.py`: seed GAUA-17 dataset.
- `src/gaugeflow_social_os/engine.py`: validation, scoring, prioritization, planning, critical chain.
- `src/gaugeflow_social_os/exporters.py`: CSV/Markdown/JSON exports.
- `src/gaugeflow_social_os/cli.py`: command-line interface.
- `tests/test_social_os_engine.py`: engine/unit behavior tests.
- `tests/test_social_os_exporters.py`: export tests.

## Quick Start
```bash
PYTHONPATH=src python3 -m gaugeflow_social_os.cli validate
PYTHONPATH=src python3 -m gaugeflow_social_os.cli health
PYTHONPATH=src python3 -m gaugeflow_social_os.cli plan
PYTHONPATH=src python3 -m gaugeflow_social_os.cli critical-chain
PYTHONPATH=src python3 -m gaugeflow_social_os.cli export --outdir outputs
```

## Run Tests
```bash
python3 -m unittest discover -s tests -v
```

## Note
Legacy GAUA-10 `qms_plan` package remains in the workspace and its tests still run under the same test command.
