# PyInstaller spec for the bundled Python sidecar (Issue #24).
#
# Build it with `pnpm run package:sidecar` (never `pyinstaller <script>`
# directly -- the flags below are part of the contract). Produces the onedir
# tree `backend/dist/auto-scoring-sidecar/`, which the Windows installer
# copies next to the Flutter executable as `<install dir>/sidecar/`
# (docs/windows-distribution.md §2).
#
# onedir, not onefile (docs/technology-stack.md §4): onefile re-extracts the
# whole interpreter + OpenCV/pdfium/reportlab native libraries into a fresh
# %TEMP% directory on *every* launch, which both adds seconds to a startup the
# Flutter splash is already waiting on and hands Windows Defender a
# never-before-seen unsigned executable tree to re-scan each time. The sidecar
# is launched from a directory the installer already wrote, so there is
# nothing to gain from collapsing it into one file.
#
# Everything below that is not plain `Analysis` boilerplate exists because
# PyInstaller's static import analysis cannot see it. A missing entry here
# does not fail this build -- it fails at runtime inside the packaged
# executable, on a machine that has no Python. The CI "Package (Windows)" job
# therefore boots the built executable and drives a real handshake +
# /healthz + shutdown against it; that smoke test, not this file, is what
# actually proves this list is complete.

from pathlib import Path

from PyInstaller.utils.hooks import (
    collect_data_files,
    collect_dynamic_libs,
    collect_submodules,
)

BACKEND_ROOT = Path(SPECPATH).parent  # noqa: F821 -- SPECPATH is injected by PyInstaller

datas = [
    # Alembic reads `env.py` and `versions/*.py` as *source files* at runtime
    # (it execs them by path), so they must land in the bundle as files, not
    # as frozen modules. The destination mirrors `pyproject.toml`'s
    # `force-include` exactly, because `db/migrator.py::_migrations_root`
    # looks for `<auto_scoring package dir>/migrations` -- and under
    # PyInstaller that package dir is `sys._MEIPASS/auto_scoring`, which the
    # same code path resolves without knowing it is frozen.
    (str(BACKEND_ROOT / "migrations"), "auto_scoring/migrations"),
    (str(BACKEND_ROOT / "alembic.ini"), "auto_scoring"),
]

# Alembic's own package data (its script templates, and the `__init__` files
# its runtime discovery walks).
datas += collect_data_files("alembic")

# reportlab's bundled Type 1 fonts and character-width tables, loaded by
# filename from `reportlab/fonts/`. The *Japanese* font used for export
# comments is not here -- that one is read from the Windows system font
# directory at runtime and deliberately not redistributed
# (adapters/pdf/pdfium_pypdf_engine.py, docs/pdf-export.md §3).
datas += collect_data_files("reportlab")

# pdfium itself: `pypdfium2` is a thin ctypes binding over the `pdfium`
# shared library that ships inside the separate `pypdfium2_raw` package, plus
# a `version.json` in each that both packages read on import.
datas += collect_data_files("pypdfium2")
datas += collect_data_files("pypdfium2_raw")
binaries = collect_dynamic_libs("pypdfium2_raw")

hiddenimports = [
    # `migrations/env.py` and `adapters/ai_grading/factory.py` both reach for
    # modules by name at runtime, and the routers/adapters are only ever
    # reached through FastAPI's decorators -- collect the whole package
    # rather than trying to enumerate which of those PyInstaller happens to
    # follow statically.
    *collect_submodules("auto_scoring"),
    # Uvicorn selects its event loop, HTTP parser, WebSocket and ASGI
    # lifespan implementations through `importlib` on strings built from
    # config ("auto"), so none of these are reachable from `import uvicorn`.
    # This is the single most common way a packaged FastAPI app builds
    # cleanly and then exits at startup.
    "uvicorn.lifespan.off",
    "uvicorn.lifespan.on",
    "uvicorn.loops.asyncio",
    "uvicorn.loops.auto",
    "uvicorn.protocols.http.auto",
    "uvicorn.protocols.http.h11_impl",
    "uvicorn.protocols.websockets.auto",
    "uvicorn.protocols.websockets.websockets_impl",
    "uvicorn.protocols.websockets.wsproto_impl",
    # SQLAlchemy resolves a dialect from the URL scheme ("sqlite://") through
    # its own registry, never with a literal import.
    *collect_submodules("sqlalchemy.dialects.sqlite"),
    # Same pattern one layer down: Alembic picks the DDL implementation that
    # matches the connected dialect.
    *collect_submodules("alembic.ddl"),
    # OpenCV's Python package is a loader shim around a compiled extension;
    # naming it explicitly makes PyInstaller run its bundled cv2 hook (which
    # is what actually collects the native libraries) even though nothing
    # imports `cv2` until the first image-preprocessing call.
    "cv2",
]

analysis = Analysis(  # noqa: F821 -- PyInstaller injects its own builtins
    [str(BACKEND_ROOT / "packaging" / "sidecar_entrypoint.py")],
    pathex=[str(BACKEND_ROOT / "src")],
    binaries=binaries,
    datas=datas,
    hiddenimports=hiddenimports,
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    # Test-only and interactive dependencies that get pulled in transitively
    # and would otherwise add tens of MB to every installer for nothing.
    excludes=["IPython", "matplotlib", "pytest", "tkinter"],
    noarchive=False,
    optimize=0,
)

pyz = PYZ(analysis.pure)  # noqa: F821

exe = EXE(  # noqa: F821
    pyz,
    analysis.scripts,
    [],
    exclude_binaries=True,  # onedir: the libraries stay beside the exe
    name="auto-scoring-sidecar",
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=False,  # UPX-packed binaries are a well-known antivirus false-positive trigger
    console=True,
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
)

COLLECT(  # noqa: F821
    exe,
    analysis.binaries,
    analysis.datas,
    strip=False,
    upx=False,
    name="auto-scoring-sidecar",
)
