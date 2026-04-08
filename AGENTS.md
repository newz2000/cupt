# AGENTS.md

## Build / Test / Lint Commands

* **Build the package** (sdist & wheel):
```bash
python -m build
```

* **Linting** (flake8 + black + isort):
```bash
flake8 cupt tests
black cupt tests --check
isort cupt tests --check-only
```

* **Run all tests**:
```bash
pytest
```

* **Run a single test** (e.g. `tests/test_api.py::test_get_user`):
```bash
pytest tests/test_api.py::test_get_user
```

* **Run tests with coverage**:
```bash
pytest --cov=cupt --cov-report=term-missing
```

* **Run tests with debug output**:
```bash
pytest -vv
```

---

## Code Style Guidelines

* **Imports**
  * Standard library first, then third‑party, then local packages.  Separate groups with a blank line.
  * Use `from package import Class` when only one symbol is required.
  * Avoid `import *`.

* **Formatting**
  * 79‑character line limit for source code; allow 119 for long strings.
  * Use `black 21.9b0` as the formatter; run `black .` before committing.
  * Use `isort` to keep imports sorted (`isort .`).

* **Typing**
  * All public functions must have type annotations.
  * Use `typing.Optional`, `typing.List`, `typing.Dict`, etc.
  * In tests, use `typing.Any` when mocking complex objects.

* **Naming Conventions**
  * Modules: snake_case.
  * Classes: CamelCase.
  * Functions & variables: snake_case.
  * Constants: UPPER_SNAKE_CASE.

* **Error Handling**
  * Raise domain‑specific exceptions (`APIError`, `AuthError`).
  * Do not swallow `Exception`; only catch where you can recover.
  * Return informative error messages.

* **Docstrings**
  * Use the Google style docstring format.
  * Include parameter, return, and raise sections.

* **Logging**
  * Use `logging.getLogger(__name__)` instead of print statements.
  * Configure a root handler with level `INFO` in `cupt/__main__`.

* **Testing**
  * Organise tests mirrored to source package structure.
  * Use fixtures for common setup.
  * Mock external HTTP calls with `unittest.mock.patch`.
  * Aim for 80 %+ line/branch coverage.

---

## Cursor Rules

The `.cursor/rules/` directory may contain custom rules for code generation. If present, they should be documented here.

---

## Copilot Rules

If there is a `.github/copilot-instructions.md`, follow those guidelines when writing new code; mainly:

* Prefer built‑in `requests` session reuse.
* Avoid hard‑coded URLs – use `f"{self.base_url}/path"`.
* Keep method names succinct and action‑oriented.

---

## Usage Tips

* Use `pre-commit` hooks for linting and formatting. The repo includes a config.
* Run `pre-commit run --all-files` to enforce style before pushing.
* If a commit fails a pre‑commit check, run `python -m gitlint` for more detail.

---

## Contact

For questions, open an issue or PR in the repository.
