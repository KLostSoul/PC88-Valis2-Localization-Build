"""Command-line entry point for the direct, manual-source build."""

from __future__ import annotations

from .manual_build import main


if __name__ == "__main__":
    raise SystemExit(main())
