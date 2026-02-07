# CONTRIBUTING

Díky za contribution do GameHubu.

## 1. Lokální dev setup

## 1.1 Požadavky

- Python 3.12+
- Git
- (Windows) PowerShell 7+ doporučeno

## 1.2 Instalace

```bash
python -m venv .venv
.venv\Scripts\activate
python -m pip install -r requirements-dev.txt
```

## 1.3 Spuštění aplikace

```bash
python run.py
```

## 2. Testy a kontroly

## 2.1 Unit/property testy

```bash
python -m pytest -q tests
```

## 2.2 Plugin smoke + audit

```bash
python tester.py
python tester.py --plugins-only
python tester.py --tests-only
```

## 2.3 Kvalita kódu

```bash
python -m ruff check .
python -m ruff format .
python -m mypy
```

## 2.4 Pre-commit hooky

```bash
python -m pre_commit install
python -m pre_commit run --all-files
```

## 3. Coding style

- Dodržuj existující vrstvení: `engine / solver / ui`.
- Nová hra musí mít validní plugin metadata (`id`, `name`, `description`, `graphic_text` nebo `icon_path`).
- Lifecycle-safe widgety:
  - implementuj `on_activate`, `on_deactivate`, `dispose` pokud držíš background tasky/timery.
- Preferuj explicitní typy pro veřejné API.
- U změn v engine přidej test.

## 4. Commit / PR doporučení

- Používej stručné konvenční prefixy:
  - `feat:`
  - `fix:`
  - `refactor:`
  - `test:`
  - `docs:`
  - `chore:`
- PR by měl obsahovat:
  - co se mění a proč,
  - jak bylo ověřeno (testy / ruční check),
  - případné screenshoty při UI změně.

## 5. Release workflow (maintainers)

- Vytvoř tag:

```bash
git tag vX.Y.Z
git push origin vX.Y.Z
```

- GitHub Actions workflow `release.yml` vytvoří artefakty + checksumy a publikuje Release.
