"""PyInstaller entry script for the bundled sidecar.

A one-line shim rather than pointing `Analysis` straight at
`src/auto_scoring/api/sidecar.py`: PyInstaller runs the entry script as
`__main__`, so using the real module as the entry point would load it twice
under two names (`__main__` and `auto_scoring.api.sidecar`) and give the
bundle two copies of its module-level state. It also keeps the console
script's contract (`auto_scoring.api.sidecar:main`, `pyproject.toml`
`[project.scripts]`) as the single definition of what "run the sidecar"
means, so the frozen executable and `uv run auto-scoring-sidecar` cannot
drift apart.
"""

from auto_scoring.api.sidecar import main

main()
