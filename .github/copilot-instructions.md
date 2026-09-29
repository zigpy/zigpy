# GitHub Copilot Custom Instructions for zigpy

**Purpose**  
This repository-level Copilot instruction file helps code-writing agents understand the `zigpy` project and reliably produce changes that build, test, and validate with minimal trial-and-error.  
Treat this file as **authoritative**: follow the steps and checks here before performing broad repository searches.

---

## Priority Guidelines

When generating code for this repository:

- **Version Compatibility**: Always respect the exact versions of Python and libraries used in this project.
- **Codebase Patterns**: Scan the codebase for established patterns before generating code.
- **Architectural Consistency**: Maintain the layered architecture and established module boundaries.
- **Code Quality**: Prioritize maintainability, type safety, and consistency with existing patterns.
- **Testing**: Follow the established testing patterns.

---

## 1. High-Level Summary

- `zigpy` is a **hardware-independent Zigbee protocol stack** implemented as a **Python 3 library** used for building Zigbee gateway implementations that will support "radio" libraries for zigpy that abstract different Zigbee hardware implementations.
- It provides core stack logic for Zigbee (networking, addressing, device management), and contains common code implementing ZCL (Zigbee Cluster Library), ZDO (Zigbee Device Object) application state management, Zigbee OTAU (Over-The-Air Updates) handling and Zigbee OTA providers, as well as also uses associated downstream radio-specific projects such as the [zigpy-znp](https://github.com/zigpy/zigpy-znp), [bellows](https://github.com/zigpy/bellows), and [zigpy-deconz](https://github.com/zigpy/zigpy-deconz) libraries.
- It is primarily used in the **[Home Assistant’s ZHA integration](https://www.home-assistant.io/integrations/zha)** which in turn depends on the downstream [ZHA (Zigbee Home Automation) library](https://github.com/zigpy/zha), [zigpy-cli](https://github.com/zigpy/zigpy-cli), and [zha-device-handlers](https://github.com/zigpy/zha-device-handlers) libraries for its Zigbee gateway application layer implementation.
- The project is organized as a **pure Python asyncio-based library** with accompanying unit and integration tests.

---

## 2. Project Type and Technologies

- **Language:** Python 3 (asyncio, type hints, dataclasses, logging)
- **Test Framework:** `pytest`
- **Package Management:** `pip`, `setuptools`
- **Linting / Formatting:** often `flake8`, `black`, and optionally `pre-commit`
- **CI:** GitHub Actions workflows under `.github/workflows/`
- **Target Runtime:** CPython 3.11 (always check CI matrix for updates)

---

## 3. Environment Setup (Always Do This First)

1. Create and activate a clean virtual environment:
   ```bash
   python3 -m venv .venv
   source .venv/bin/activate
   python -m pip install --upgrade pip setuptools wheel
   ```

2. Install the project in editable mode:
   ```bash
   pip install -e .
   ```

3. Install development and test dependencies (if available):
   ```bash
   pip install -r requirements_test.txt
   ```
   or
   ```bash
   pip install -r requirements-dev.txt
   ```

4. Confirm installation:
   ```bash
   python -c "import zigpy; print(zigpy.__version__)"
   ```

> **Always** perform the above before building, testing, or linting.  
> Editable installs (`pip install -e .`) ensure your local code is exercised by tests.

---

## 4. Build, Test, and Lint Commands

### Clean Build
```bash
git clean -fdx
python -m venv .venv
source .venv/bin/activate
pip install -U pip setuptools wheel
pip install -e .
pip install -r requirements_test.txt || true
```

### Run Tests
```bash
pytest -q
```
- To run specific tests:
  ```bash
  pytest -k "cluster"  # Example keyword filter
  ```
- Use `pytest -vv` for verbose logs.

### Run Linters / Formatters
If a `.pre-commit-config.yaml` is present:
```bash
pip install pre-commit
pre-commit run --all-files
```

Otherwise:
```bash
flake8 zigpy tests
black --check zigpy tests
```

### Validate Locally Before PR
Run:
```bash
pytest && pre-commit run --all-files
```
This reproduces the GitHub CI checks.

---

## 5. Project Layout Overview

Layered architecture:
- The main source files implement core Zigbee components such as application support (APS), network (NWK), and ZCL layers.  
- Tests in `tests/` cover typical stack behaviors; hardware backends are mocked.

| Path | Purpose |
|------|----------|
| `zigpy/` | Main package containing Zigbee stack implementation |
| `zigpy/ota/` | Zigbee OTA (Over-The-Air) schemaes and providers, Zigbee OTAU update manager |
| `zigpy/zcl/` | Zigbee Cluster Library (ZCL) layer |
| `zigpy/zdo/` | Zigbee Device Objects (ZDO) layer |
| `zigpy/zgp/` | Zigbee Green Power Clusters and supporting ZGP Schemas |
| `zigpy/quirks/` | Support for Zigbee device exception handlers for parsing custom messages that deviate from standard ZCL |
| `zigpy/profiles/` | Zigbee profiles support. Currently includes ZHA profile (Zigbee Home Automation), and ZLL profile (Zigbee Light Link), and initial support for ZGP profile (Zigbee Green Power) |
| `zigpy/event/` | Event Base Class (simplified implementation in zigpy of Home Assistant's ZHA event base), will replace callback listeners in the future. See https://github.com/zigpy/zigpy/pull/1653 |
| `tests/` | Unit and integration tests (pytest) |
| `.github/workflows/` | CI build and test definitions |
| `requirements_test.txt` / `requirements-dev.txt` | Dev/test dependencies |
| `setup.py` / `pyproject.toml` | Build configuration |
| `README.md`, `CONTRIBUTING.md` | Overview and contribution guidelines |

---

## 6. CI / Validation Steps

GitHub Actions automatically run:
- Installation (`pip install -e .`)
- Lint (`flake8`, `black`, `pre-commit`)
- Unit tests (`pytest`)
- Type checks (if `mypy` configured)

**To replicate locally:**
1. Match the Python versions used in `.github/workflows/ci.yml`.
2. Run the same `pytest` and lint steps listed above.
3. Ensure no skipped tests depend on missing hardware; guard new hardware-specific tests with:
   ```python
   pytest.mark.skipif("ZIGPY_HW_TEST" not in os.environ, reason="Requires hardware")
   ```

---

## 7. Common Pitfalls and Workarounds

- **Missing dependencies:** Always install dev/test requirements.  
- **Editable installs:** Required for imports to work correctly during tests.  
- **Hardware-dependent tests:** Skip or mock hardware I/O to prevent CI failures.  
- **Version mismatches:** Align Python version with CI matrix.  
- **Async bugs:** Use `pytest.mark.asyncio` for async test functions.  
- **Lint failures:** Run pre-commit hooks before pushing.

---

## 8. Validation Checklist Before PR

- [ ] `pip install -e .` runs cleanly  
- [ ] `pytest` passes for all changed or affected tests  
- [ ] `pre-commit run --all-files` passes  
- [ ] If you changed APIs or behavior, include tests and doc updates  
- [ ] Confirm compatibility with all Python versions in CI matrix  
- [ ] Commit messages follow the repo’s contribution style

---

## 9. Agent Behavior Guidelines

- **Trust this file first.** Only search the repo if something here is missing or incorrect.  
- **Prefer explicit commands** listed above over inferred or experimental ones.  
- **Document failures** (stdout/stderr, Python version, OS) when submitting PRs.  
- **Respect async conventions** — many functions in `zigpy` are async and require `await`.

---

## 10. Example Prompts for Copilot / AI Agents

Use the following prompt styles to steer development:

- “You are editing a Python 3 asyncio-based Zigbee stack library. Follow `.github/copilot-instructions.md`. Write code that is type-hinted, async-safe, and covered by pytest tests.”  
- “Add a new feature or fix ensuring CI (pytest + pre-commit) passes.”  
- “Generate a pytest unit test for a Zigbee ZCL command parser. Avoid hardware dependencies.”  
- “When modifying public APIs, ensure backward compatibility and update any affected tests.”

---

## 11. Exploration Guidance

Perform repo-wide search **only** if:
- Required config files are missing from the root, or  
- a test fails unexpectedly with missing imports or dependencies.

Otherwise, rely on these documented paths and commands.

---

### Final Notes

- This document provides the canonical, repeatable workflow for developing on `zigpy`.  
- Follow it to minimize CI failures and wasted exploration.  
- If discrepancies arise between this file and the repo’s configuration (e.g., updated test deps), prefer the repository’s files and update this document in your PR.

---

### References
- zigpy GitHub repository overview and documentation  
- Community discussions about adding Copilot instructions to zigpy https://github.com/zigpy/zigpy/issues/1692
- zigbee-herdsman `.github/copilot-instructions.md` for inspiration https://github.com/Koenkk/zigbee-herdsman/blob/master/.github/copilot-instructions.md
