# CHANGELOG

All notable changes to this project are documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/)
and this project follows [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

- No unreleased changes yet.

## [0.6.0] - 2026-02-08

### Added

- GPU/CPU background runtime split modules:
  - `hub/widgets/background_gpu.py`
  - `hub/widgets/background_fallback.py`
  - `hub/animations/background_effects.py`
  - `hub/diagnostics/gpu_probe_runner.py`

### Changed

- Major gameplay and UI refinements across games:
  - `2048`
  - `Mastermind`
  - `Piškvorky`
  - `Slitherlink`
  - `Sudoku`
- Hub card/background rendering and dialog styling consistency.
- Print dialog controls updated for reliable `+ / -` quantity stepping.
- Top menu `Quit` action kept in code but disabled by default (commented).

### Fixed

- Dialog styling issues on some systems where spinbox arrows rendered as empty or white blocks.
- Printing workflow now consistently uses Qt-styled dialogs for visual parity.

## [0.5.0] - 2026-02-07

### Added

- Cross-platform release packaging:
  - `scripts/build_windows.ps1`
  - `scripts/build_linux.sh`
- GitHub Releases automation (`.github/workflows/release.yml`) with artifact publishing.
- SHA256 checksum generation for release artifacts.
- Reproducible lockfile flow:
  - `requirements-build.in`
  - `requirements-lock.txt` (with hashes)

### Changed

- `build_exe.ps1` now delegates to the canonical Windows build script.

### Fixed

- Windows build metadata helper now supports empty fallback value for git status.

## [0.4.0] - 2026-02-07

### Added

- Quality gates with `ruff`, `mypy`, `pre-commit`.
- Property-based tests for puzzle generator consistency (`tests/test_generators_property.py`).

### Changed

- README documentation for tooling and quality workflow.

## [0.3.0] - 2026-02-07

### Added

- Safe one-file build script for packaging all modules.

## [0.2.0] - 2026-02-07

### Added

- Unified engine/solver/ui layer structure across games.
- Solver contract normalization and auditable solver pipeline split.
- Hardened plugin API and lifecycle handling in hub.
- Shared worker abstraction for async background operations.
- Engine test coverage expansion and auto-discovery tester flow.

## [0.1.0] - 2026-02-06

### Added

- Initial GameHub release with multiple puzzle games.
- Plugin-based game loading architecture.
- Print/PDF support for Sudoku, KenKen, Slitherlink.
- Core docs for rules, controls, and AI/solver behavior.
