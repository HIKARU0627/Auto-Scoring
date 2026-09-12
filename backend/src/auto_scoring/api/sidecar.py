"""Runnable entry point for the local sidecar.

Binds FastAPI to the loopback interface on a dynamic port, mints a per-session
bearer token, and hands the ``{host, port, token}`` tuple to its parent process
over an explicit handshake file.

Design decisions live in ``docs/technology-stack.md`` §1.1-§1.2 and
``docs/sidecar-api.md``:

* The listen address is hard-wired to ``127.0.0.1`` so the API is never exposed
  on a LAN interface.
* If the requested port is taken the sidecar falls back to any free port, so a
  second instance (or an unrelated process holding the port) does not block
  startup.
* The token is written only to the handshake channel. A logging filter
  removes it, and this host's configuration values, from every record that
  reaches the log -- but only where they appear *verbatim*
  (`api.secret_redaction` documents that limit). What a library does to a
  value before printing it is outside that filter's reach, so libraries do
  not get to print at INFO here at all: see `_VERBOSE_LOGGERS`.
* The handshake is written *after* ``create_app`` succeeds, so a handshake file
  never advertises a ``host:port`` this process will not go on to serve
  (``docs/windows-distribution.md`` §4).
"""

from __future__ import annotations

import argparse
import importlib
import json
import logging
import logging.handlers
import os
import shutil
import socket
import sys
from collections.abc import Callable, Mapping, Sequence
from pathlib import Path
from typing import TypedDict

import uvicorn

from auto_scoring.adapters.ai.unconfigured_provider import UnconfiguredAIProvider
from auto_scoring.adapters.ai_classification.factory import create_material_classifier
from auto_scoring.adapters.ai_grading._google_adc import AdcCredentialsError, AdcTokenSource
from auto_scoring.adapters.ai_grading.factory import create_ai_provider
from auto_scoring.adapters.answer_area_detection.factory import create_answer_area_detector
from auto_scoring.adapters.credentials.api_keys import ApiKeySettings
from auto_scoring.adapters.credentials.store import (
    CREDENTIAL_STORE_TIMEOUT_SECONDS,
    acquire_credential_store,
    create_credential_store,
)
from auto_scoring.adapters.criteria_extraction.extractor import UnconfiguredCriteriaExtractor
from auto_scoring.adapters.criteria_extraction.factory import create_criteria_extractor
from auto_scoring.adapters.data_root_lock import DataRootLockedError
from auto_scoring.adapters.ocr.factory import create_ocr_provider
from auto_scoring.adapters.ocr.unconfigured_provider import UnconfiguredOCRProvider
from auto_scoring.adapters.parent_watchdog import (
    DETECTION_BUDGET_SECONDS,
    start_parent_watchdog,
)
from auto_scoring.api.app import (
    build_ai_provider,
    build_answer_area_detector,
    build_criteria_extractor,
    build_ocr_provider,
    create_app,
)
from auto_scoring.api.auth import generate_token
from auto_scoring.api.secret_redaction import SecretRegistry, configuration_secrets, redact
from auto_scoring.domain.answer_area_detection import UnconfiguredAnswerAreaDetector

LOOPBACK = "127.0.0.1"
"""The only interface the sidecar ever binds. Keeps the API off the LAN."""

ALREADY_RUNNING_EXIT_CODE = 3
"""Exit code for "another live process already owns this app-data root".

Its own code, distinct from the generic ``1`` any other startup failure exits
with, because it is the one startup failure the *user* can act on: the
supervisor that spawned this process turns it into "Auto-Scoring はすでに
起動しています" instead of a generic crash screen
(``app/lib/core/sidecar_supervisor.dart``, ``docs/windows-distribution.md`` §5).
"""

STARTUP_FAILED_EXIT_CODE = 1
"""Exit code for any *other* startup or serving failure.

Distinct from `ALREADY_RUNNING_EXIT_CODE` so the supervisor can tell the one
failure the user can act on apart from the ones only a log can explain. It is
plain ``1`` because that is what an uncaught exception would already have
produced -- the point of the constant is that the failure now reaches the log
on its way out (`run`), not that the number changed.

`app/lib/core/sidecar_supervisor.dart` needs no branch of its own for this:
every non-3 exit already becomes `exitedDuringStartup` (or `crashed`, after
the sidecar has served), and both of those screens point the user at
`sidecar.log` -- which is now where the reason actually is.
"""

APP_NAME = "Auto-Scoring"
"""Directory name this app owns under the OS's per-user data location."""

LOG_DIRECTORY_NAME = "logs"
LOG_FILENAME = "sidecar.log"
LOG_MAX_BYTES = 5 * 1024 * 1024
LOG_BACKUP_COUNT = 3
"""Log rotation: 5 MiB per file, 3 kept, so the log is bounded at 20 MiB.

Bounded because nothing else ever prunes it: the sidecar runs on a teacher's
own machine with no operator and no log shipper, and simplified-design-
specification.md §28 wants a durable record of AI/OCR/PDF successes and
failures across sessions. Size-based rather than time-based since usage is
bursty (a whole class of answers in one afternoon, then nothing for a week).
"""


#: The only logger trees this process lets speak at INFO. Everything else --
#: any library now or later, `httpx` and `httpcore` above all -- stays at the
#: root level below, which is WARNING.
#:
#: Deny by default, because the alternative lost three times running (review
#: rounds 1-3). httpx logs every request URL at INFO, and the Vertex adapter
#: builds that URL out of ``AUTO_SCORING_VERTEX_PROJECT`` /
#: ``AUTO_SCORING_GEMINI_MODEL`` / ``AUTO_SCORING_VERTEX_LOCATION``, so a key
#: pasted into any of them was written to a log that outlives the session.
#: Masking the value out of that line cannot be made to hold: httpx lowercases
#: the host, so an uppercase character in the value already defeated an exact
#: match (round 3), and percent-encoding or truncation would defeat the next
#: attempt. **A URL this app never needed in its log is not worth a game of
#: catch-up: it is not logged at all.**
#:
#: What replaces it is *not* the URL rendered more carefully -- it is a
#: diagnosis assembled from parts that cannot carry configuration
#: (`domain.ai_provider.ProviderAttempt`: the adapter's literal id, the
#: exception class, the HTTP status number). A successful grade is
#: attributed by `GradeResult`'s reproducibility triple (Issue #20); a
#: *failed* one has no `GradeResult` at all, which is why the same record
#: also goes to `Job.last_error` and to a WARNING from
#: `adapters.ai_grading.fallback_provider` for each link a chain fell
#: through. Saying only "the triple covers it" was wrong, and review round 4
#: caught it: on a fully-failed chain there is no triple to read.
#:
#: That covers those three parts, for the failures the port declares. It is
#: not a claim that every failure is diagnosable.
#:
#: ``uvicorn`` stays because its access log is this app's *own* loopback
#: routes (no configuration in the path, and the bearer token travels in a
#: header the filter scrubs); ``alembic`` because first-launch migration
#: progress is the slowest, least observable part of startup.
_VERBOSE_LOGGERS = ("auto_scoring", "uvicorn", "alembic")


class Handshake(TypedDict):
    """The single JSON line the parent process reads to reach the sidecar."""

    host: str
    port: int
    token: str


def _bind_socket(requested: int, host: str = LOOPBACK) -> socket.socket:
    """Bind and return an open socket on a bindable port -- held open (not
    yet listening) until the caller hands it straight to uvicorn.

    ``0`` means "any free port". A non-zero ``requested`` port that cannot be
    bound (already in use) falls back to any free port rather than failing
    startup.

    This used to be a plain ``resolve_port() -> int``: bind a throwaway probe
    socket, read the port number the OS assigned it, close the probe, and
    hand back just the number for the *caller* to bind again later. That left
    a real gap between "a free port was found" and "the real server is
    listening on it" -- during which the OS was free to hand that exact
    number to something else. Observed in practice on Windows: the longer
    ``create_app()`` (schema migrations) took to run in that gap, the more
    often asyncio's own event loop -- started moments later, inside this same
    process, to actually serve the app -- ended up binding its own internal
    sockets to the just-freed port first, silently shifting the real server
    onto the *next* port instead, while the handshake file had already been
    written with the original one. A client trusting the handshake would
    then reach nothing at all. Returning the still-open, already-bound
    socket instead of a bare number closes that gap entirely: nothing else
    can ever claim this exact port between here and ``run()`` handing the
    same socket object to uvicorn.
    """
    sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    try:
        sock.bind((host, requested))
    except OSError:
        sock.close()
        sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        sock.bind((host, 0))
    return sock


class _RedactingFilter(logging.Filter):
    """Replaces every known secret with ``***`` in every log record.

    The log half of `api.secret_redaction`'s gate: the session token plus
    this host's configuration values (review round 2 -- a value reaches the
    log through code that never calls a logger of ours, such as httpx's
    INFO-level request URL).
    """

    def __init__(self, registry: SecretRegistry) -> None:
        super().__init__()
        self._registry = registry

    def filter(self, record: logging.LogRecord) -> bool:
        # Read per record, not captured once: a key entered on the settings
        # screen becomes a secret while this process runs, and the whole
        # point of the registry is that the filter installed at startup
        # covers it from the moment it is saved (Issue #96).
        secrets = self._registry.secrets()
        message = record.getMessage()
        scrubbed = redact(message, secrets)
        if scrubbed != message:
            record.msg = scrubbed
            record.args = ()

        # The formatted message is not the only thing a handler writes. Since
        # `run` started logging startup failures with `logger.exception`, every
        # record can carry a traceback too, and that text never passes through
        # `getMessage()` -- a filter that only scrubbed the message would let a
        # token through in an exception's own string (`create_app` is called
        # with it, and any library that echoes an argument back into an error
        # message would put it there).
        #
        # Formatting it here rather than leaving it to each handler's Formatter
        # is what makes the scrub stick: `Formatter.format` reuses a non-None
        # `exc_text` instead of re-deriving it, so every handler downstream of
        # this filter writes the redacted copy.
        if record.exc_info is not None:
            if record.exc_text is None:
                record.exc_text = logging.Formatter().formatException(record.exc_info)
            record.exc_text = redact(record.exc_text, secrets)
        return True


def install_log_redaction(
    token: str,
    log_directory: Path | None = None,
    *,
    secrets: Sequence[str] = (),
    registry: SecretRegistry | None = None,
) -> None:
    """Route logging through handlers that all scrub ``token`` and ``secrets``.

    ``secrets`` is this host's configuration values (`configuration_secrets`)
    -- the single gate described there. Empty by default so a caller that
    only wants the session token scrubbed, and every test that installs
    logging, says nothing about the machine's environment.

    ``registry`` is what makes the gate hold for a value this process only
    learns about later -- an API key entered on the settings screen (Issue
    #96). Pass the same `SecretRegistry` the settings endpoints add to and
    every handler picks up each new key immediately; omit it and this
    function makes a private one holding exactly ``token`` and ``secrets``,
    which is the old behaviour.

    Always to stderr; additionally to a rotating file under ``log_directory``
    when one is given. The file is what makes the log useful in a
    distribution at all -- the Flutter supervisor drains the sidecar's stderr
    to keep its pipe from filling up, so on an installed machine stderr goes
    nowhere and a crash would otherwise leave nothing to look at
    (docs/windows-distribution.md §5).

    Every handler gets its own copy of the redaction filter rather than the
    filter being attached to the root logger: a filter on a *logger* only
    applies to records logged directly through it, not to records that
    propagate up from child loggers -- which is every record that matters
    here (``uvicorn.access``, ``alembic.runtime.migration``).
    """
    formatter = logging.Formatter("%(asctime)s %(levelname)s %(name)s: %(message)s")
    handlers: list[logging.Handler] = [logging.StreamHandler()]

    file_log_error: OSError | None = None
    if log_directory is not None:
        # Best effort. A log directory that cannot be created (app-data on a
        # read-only volume, a permissions problem, a full disk) is a real
        # failure, but it is not one worth refusing to start over -- and
        # certainly not by raising *here*, before `run`'s handler is in place,
        # where it would escape as exactly the unlogged traceback this whole
        # arrangement exists to prevent. Carry on with stderr only and say so.
        try:
            log_directory.mkdir(parents=True, exist_ok=True)
            handlers.append(
                logging.handlers.RotatingFileHandler(
                    log_directory / LOG_FILENAME,
                    maxBytes=LOG_MAX_BYTES,
                    backupCount=LOG_BACKUP_COUNT,
                    encoding="utf-8",
                )
            )
        except OSError as error:
            file_log_error = error

    scrubbed = registry if registry is not None else SecretRegistry()
    scrubbed.update((token, *secrets))
    for handler in handlers:
        handler.setFormatter(formatter)
        # A filter instance per handler, not one shared -- logging holds
        # filters per handler and this keeps each handler independent. They
        # do share the registry, which is the object that is *meant* to
        # change.
        handler.addFilter(_RedactingFilter(scrubbed))

    root = logging.getLogger()
    root.handlers = handlers
    # WARNING at the root, INFO only for _VERBOSE_LOGGERS: see that constant
    # for why a library's INFO output is refused rather than filtered. A
    # child logger set to INFO still reaches these handlers -- propagation
    # does not re-check the root logger's own level.
    root.setLevel(logging.WARNING)
    for name in _VERBOSE_LOGGERS:
        logging.getLogger(name).setLevel(logging.INFO)

    if file_log_error is not None:
        # Logged only once the handlers are installed, so it is itself visible.
        logging.getLogger(__name__).warning(
            "no file log at %s (%s); logging to stderr only",
            log_directory,
            file_log_error,
        )


def _emit_handshake(handshake: Handshake, destination: Path) -> None:
    line = json.dumps(handshake) + "\n"
    destination.write_text(line, encoding="utf-8")


def default_app_data_dir(
    environment: Mapping[str, str] | None = None,
    platform: str | None = None,
) -> Path:
    """The per-user ``app-data/`` root this sidecar owns when no
    ``--app-data-dir`` is given (simplified-design-spec.md §23).

    Final location, decided by Issue #24 -- it replaces the provisional
    ``cwd()/app-data`` this default used to be. ``cwd()`` was unusable in a
    distribution: the working directory of a process launched from a Start
    menu shortcut, from Explorer, or by the Flutter app is whatever the
    launcher happened to set, so the same installed app would have found (or
    silently created) a *different* database depending on how it was started,
    and installing under ``C:\Program Files`` would have put it somewhere the
    user cannot write at all.

    Per-user, not per-machine, and outside the install directory, because the
    data is one teacher's answer PDFs and grades (§26), an uninstall must be
    able to leave it behind (docs/windows-distribution.md §6), and a
    non-elevated user must be able to write it.

    ``environment``/``platform`` default to this process's own and exist so
    tests can resolve any OS's layout from any host.
    """
    env = os.environ if environment is None else environment
    system = sys.platform if platform is None else platform

    if system == "win32":
        # LOCALAPPDATA, not APPDATA: this is machine-local working data
        # (a SQLite database and hundreds of MB of PDFs and page images),
        # exactly what Microsoft reserves LocalAppData for. APPDATA roams
        # to a domain controller on managed networks, which for this data
        # would be both slow and a copy of personal information onto a
        # server the user did not choose (§26).
        local = env.get("LOCALAPPDATA")
        base = Path(local) if local else Path.home() / "AppData" / "Local"
        return base / APP_NAME / "app-data"

    if system == "darwin":
        return Path.home() / "Library" / "Application Support" / APP_NAME / "app-data"

    # POSIX (developer machines and CI Linux runners): the XDG base directory
    # spec's data location. Not the Windows-cased APP_NAME -- lowercase and
    # hyphenated is the convention there.
    data_home = env.get("XDG_DATA_HOME")
    base = Path(data_home) if data_home else Path.home() / ".local" / "share"
    return base / "auto-scoring" / "app-data"


#: Modules whose import is what actually loads a native library: OpenCV's
#: compiled extension, pdfium via `pypdfium2`, and reportlab's C accelerator.
#: Nothing imports them until the first answer PDF is processed, so a bundle
#: missing one of them boots, serves `/healthz`, and only fails much later --
#: in front of a user, on a machine with no Python to debug it on. `--self-test`
#: exists to pull that failure forward into the packaging build.
_NATIVE_BACKED_MODULES = (
    "auto_scoring.adapters.image.opencv_preprocessor",
    "auto_scoring.adapters.pdf.pdfium_pypdf_engine",
)


def self_test() -> int:
    """Import every native-backed module and report the outcome on stdout.

    The packaging counterpart of `pnpm run build:backend`'s
    ``import auto_scoring`` check: that one proves the *source tree* imports,
    this one proves the *frozen bundle* does. Run against the built
    executable by the CI "Package (Windows)" job before it uploads anything
    (docs/windows-distribution.md §7).
    """
    for name in _NATIVE_BACKED_MODULES:
        module = importlib.import_module(name)
        print(f"ok {name} ({module.__name__})")
    print(f"self-test passed: {len(_NATIVE_BACKED_MODULES)} native-backed modules")
    return 0


def _parse_args(argv: Sequence[str] | None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(prog="auto-scoring-sidecar")
    parser.add_argument(
        "--port",
        type=int,
        default=0,
        help="Requested port; 0 (default) or an unavailable port picks a free one.",
    )
    parser.add_argument(
        "--handshake-file",
        type=Path,
        default=None,
        help="File to write the {host, port, token} JSON line to.",
    )
    parser.add_argument(
        "--self-test",
        action="store_true",
        help=(
            "Import every native-backed dependency and exit, without binding a "
            "port or touching app-data. Verifies a packaged build is complete."
        ),
    )
    parser.add_argument(
        "--app-data-dir",
        type=Path,
        default=default_app_data_dir(),
        help=(
            "app-data/ root (simplified-design-spec.md §23): database, source "
            "PDFs, generated images. Persists across restarts. Defaults to the "
            "OS's per-user data location (docs/windows-distribution.md §3): "
            "%%LOCALAPPDATA%%\\Auto-Scoring\\app-data on Windows."
        ),
    )
    parser.add_argument(
        "--parent-pid",
        type=int,
        default=None,
        help=(
            "Exit within "
            f"{DETECTION_BUDGET_SECONDS:.0f}s of the process with this id exiting. "
            "Off unless given: pytest and a hand-started sidecar have no "
            "supervisor to outlive (docs/windows-distribution.md §5.3)."
        ),
    )
    args = parser.parse_args(argv)
    # Required for a real run, meaningless for --self-test (which starts no
    # server for anyone to hand a host:port to).
    if not args.self_test and args.handshake_file is None:
        parser.error("--handshake-file is required")
    if args.parent_pid is not None and args.parent_pid <= 0:
        # 0 and negative numbers are process *group* selectors to the POSIX
        # signal API, not process ids, and neither is ever a parent to watch.
        parser.error("--parent-pid must be a positive process id")
    return args


def run(argv: Sequence[str] | None = None) -> int:
    """Start the sidecar. Returns the process exit code."""
    args = _parse_args(argv)
    if args.self_test:
        return self_test()

    token = generate_token()

    # Bound (and held open) before anything else in this function -- see
    # _bind_socket's docstring for why: create_app() below runs schema
    # migrations and can take a while, and the socket must stay reserved for
    # the whole of that, not just for the instant this line runs.
    sock = _bind_socket(args.port)
    port = int(sock.getsockname()[1])

    # The user's own API key, read back from the OS credential store, layered
    # over this process's environment (Issue #96). One dict, built once, and
    # handed to every `build_*` call below -- `os.environ` itself is never
    # written to, so nothing this process spawns inherits a key it was not
    # given (`adapters.credentials.api_keys`, docs/sidecar-api.md section 6).
    #
    # A host with no usable credential store -- every Linux development
    # machine here, and CI -- gets an environment identical to the one it
    # would have had, and starts exactly as before.
    #
    # The two host probes (Issue #386) are wired here, in the composition root
    # that has exactly one real host to read: whether ADC resolves for the
    # configured project (Vertex AI) and whether the Codex CLI is installed.
    # Both are cached -- the settings endpoint asks on every screen load, and
    # resolving ADC is not free. A failure is cached as `False` rather than
    # re-raised, because the question is "is it available", not "hand me a
    # token"; the verify button does the live check.
    adc_available: dict[str | None, bool] = {}

    def vertex_auth_available(project_id: str | None) -> bool:
        if project_id not in adc_available:
            try:
                AdcTokenSource(project_id=project_id)
                adc_available[project_id] = True
            except AdcCredentialsError:
                adc_available[project_id] = False
        return adc_available[project_id]

    configured_codex = os.environ.get("AUTO_SCORING_CODEX_EXECUTABLE", "").strip() or "codex"

    def codex_available() -> bool:
        return shutil.which(configured_codex) is not None or Path(configured_codex).is_file()

    # Bounded (Issue #429). A backend that never answers -- measured here as
    # `import keyring` never returning on a Linux host with a D-Bus session --
    # must not hold startup past CREDENTIAL_STORE_TIMEOUT_SECONDS, or the
    # server never binds and the supervisor can only report `startupTimedOut`.
    # The fallback is the same UnavailableCredentialStore the design already
    # has for "this host has no store": the server starts, reads the
    # environment as before, and the reason reaches both sidecar.log and the
    # settings screen (`store_unavailable_reason`).
    credential_store = acquire_credential_store(
        create_credential_store,
        timeout_seconds=CREDENTIAL_STORE_TIMEOUT_SECONDS,
    )
    credential_settings = ApiKeySettings(
        credential_store,
        os.environ,
        vertex_auth_available=vertex_auth_available,
        codex_available=codex_available,
    )
    environment = credential_settings.effective_environment()

    # Logging is installed before create_app, so the file log captures the
    # slowest and least observable part of startup: the first launch's full
    # Alembic migration run. The cost is that a *second* instance -- one
    # that is about to be refused the data-root lock below -- appends its
    # single error line to the same file as the live instance. Harmless at
    # one line, and the alternative (logging to a file only once the lock is
    # held) would drop exactly the records worth keeping.
    #
    # It scrubs this host's configuration values, not just the session
    # token: the Vertex adapter builds AUTO_SCORING_VERTEX_PROJECT and
    # AUTO_SCORING_GEMINI_MODEL into every request URL, and httpx logs that
    # URL at INFO -- so a key pasted into the wrong variable reached this
    # file log through a path that has nothing to do with our own log calls
    # (review round 2). Gating the log itself covers that path and the ones
    # nobody has found yet.
    #
    # Over `environment`, not `os.environ`: a key that came from the
    # credential store is a configuration value like any other. The registry
    # is what keeps that true for a key saved *after* this line runs -- the
    # settings endpoints add to it, and the filter reads it per record.
    secret_registry = SecretRegistry(configuration_secrets(environment))
    install_log_redaction(
        token,
        args.app_data_dir / LOG_DIRECTORY_NAME,
        registry=secret_registry,
    )
    # Never a value: `describe_sources` renders slot ids and the words
    # "credential_store" / "environment" / "default" only. It answers the
    # question a support conversation actually starts with -- "is it using
    # the key I typed in, or the one in my .env.local?" (Issue #96).
    logging.getLogger(__name__).info("%s", credential_settings.describe_sources())
    # Only after logging is installed, so this reaches sidecar.log. The
    # sentence is the same one `GET /settings/api-keys` carries as
    # `store_unavailable_reason`, so the log and the screen agree about why
    # saving a key is not on offer. Not an error: an unusable store is a
    # supported configuration, and the app starts either way (Issue #429).
    store_reason = credential_store.unavailable_reason()
    if store_reason is not None:
        logging.getLogger(__name__).warning(
            "OS credential store is unavailable on this host: %s", store_reason
        )

    # Before create_app, so the watchdog also covers the first launch's full
    # migration run -- the slowest part of startup, and a stretch during
    # which this process already holds the data-root lock the next launch
    # needs. After logging is installed, so its one line reaches sidecar.log.
    #
    # Only when a supervisor asked for it (Issue #211 requirement 2): a
    # sidecar started by pytest or by hand has no parent whose death should
    # end it, and a default-on watchdog would make those launches kill
    # themselves. The data-root lock stays the backstop for every case this
    # misses (`adapters.parent_watchdog`).
    if args.parent_pid is not None:
        start_parent_watchdog(args.parent_pid)

    # data_root only, no session_factory: create_app() builds the database
    # itself (migrations, engine, the startup repair sweep) rather than this
    # function duplicating that -- see create_app()'s docstring for why
    # session_factory is reserved for callers (Issue #26's tests) that need
    # to hand in an already-migrated database instead.
    #
    # The one place that reads this host's AI-grading configuration (Issue
    # #97). `create_app` deliberately does not: a decision taken from
    # `os.environ` inside it would be inherited by every test that builds an
    # app, and would then differ between a developer machine with a `gcloud`
    # login and a CI runner without one (docs/quality-gates.md). Here, in the
    # composition root, there is exactly one real environment to read.
    #
    # `build_ai_provider` never raises: a host with no usable credentials
    # still gets an app that imports answers, serves review and exports PDFs,
    # and says on every screen that grading is unavailable.
    shared_token_source = shared_adc_token_source()
    ai_provider = build_ai_provider(
        environment,
        factory=lambda env: create_ai_provider(env, token_source_factory=shared_token_source),
    )
    missing_key_reason = credential_settings.missing_api_key_reason()
    if isinstance(ai_provider, UnconfiguredAIProvider) and missing_key_reason is not None:
        # A freshly installed copy has no environment variables, so the
        # factory's message -- which names them -- tells the user nothing
        # they can act on. Replaced only when nothing at all is configured:
        # a developer machine that names a transport and got the credentials
        # wrong keeps the specific message, which is the useful one there.
        ai_provider = UnconfiguredAIProvider(missing_key_reason)
    if isinstance(ai_provider, UnconfiguredAIProvider):
        # Warning, not error: the sidecar is about to serve normally. The
        # reason names variables and prerequisites, never their values
        # (`api.app.build_ai_provider`), so it is safe in a log file that
        # outlives the session.
        logging.getLogger(__name__).warning(
            "AI grading is unavailable on this host: %s", ai_provider.reason
        )

    # Built here for the same reason as the grading provider above: one real
    # environment, read once, in the composition root. It never raises
    # either -- a host with no image-capable transport still gets the 配点と
    # 採点基準 screen, where every value can be typed in by hand (Issue #95
    # decision 8).
    criteria_extractor = build_criteria_extractor(
        environment,
        factory=lambda env: create_criteria_extractor(
            env, token_source_factory=shared_token_source
        ),
    )
    if isinstance(criteria_extractor, UnconfiguredCriteriaExtractor):
        logging.getLogger(__name__).warning(
            "採点基準の自動抽出 is unavailable on this host: %s", criteria_extractor.reason
        )

    # Same contract, same reason it is read here and not inside `create_app`
    # (Issue #105). A host with no image-capable provider still gets a working
    # テスト設定 screen; only the 自動検出 button is off, and it says why.
    answer_area_detector = build_answer_area_detector(
        environment,
        factory=lambda env: create_answer_area_detector(
            env, token_source_factory=shared_token_source
        ),
    )
    if isinstance(answer_area_detector, UnconfiguredAnswerAreaDetector):
        logging.getLogger(__name__).warning(
            "answer-area detection is unavailable on this host: %s", answer_area_detector.reason
        )

    # The OCR half of the same per-question job (Issue #114). Until this
    # line existed, `create_app` was never passed an `ocr_provider` at all,
    # so every shipped install silently ran the placeholder adapter: text
    # always empty, Recognition Confidence always 0.0, and therefore every
    # question `usable=False` and every dependent question `BLOCKED` until a
    # human pressed /resume on it one at a time. Grading itself was fine --
    # the provider is multimodal and reads the crop directly -- which is why
    # the gap survived so long: scores and comments came out, only the chain
    # stopped moving. Adding the adapter without this line would have
    # changed nothing about what ships.
    #
    # Reuses `shared_adc_token_source` for the fourth time: Document AI
    # authenticates with the same ADC credentials as the three Vertex AI
    # callers above, and resolving them costs ~300ms each.
    ocr_provider = build_ocr_provider(
        environment,
        factory=lambda env: create_ocr_provider(env, token_source_factory=shared_token_source),
    )
    if isinstance(ocr_provider, UnconfiguredOCRProvider):
        # Warning, not error, and emphatically not a startup failure: design
        # section 24 keeps grading running without OCR. What is lost is the
        # cross-check against the grading AI's own reading and text-anchored
        # annotation positions (section 8.1.5), so this line is how the
        # operator finds out verification is weaker on this machine.
        logging.getLogger(__name__).warning(
            "OCR is unavailable on this host: %s", ocr_provider.reason
        )

    try:
        app = create_app(
            api_token=token,
            data_root=args.app_data_dir,
            ocr_provider=ocr_provider,
            ai_provider=ai_provider,
            criteria_extractor=criteria_extractor,
            answer_area_detector=answer_area_detector,
            # Bound to the layered environment for the same reason as the
            # four providers above: without it, a user who entered a key
            # would get grading but not the 取込 screen's role suggestions,
            # and nothing on screen would explain the difference. Still
            # built per request (`api.app.create_app`), so fixing ADC
            # still needs no restart.
            material_classifier_factory=lambda: create_material_classifier(environment),
            credential_settings=credential_settings,
            secret_registry=secret_registry,
        )
    except DataRootLockedError as error:
        # The one startup failure with a name the user understands, so it
        # gets an exit code of its own rather than an anonymous traceback.
        # Nothing is logged at ERROR beyond the message itself: it already
        # names the directory, and the supervisor renders the explanation.
        sock.close()
        logging.getLogger(__name__).error("%s", error)
        return ALREADY_RUNNING_EXIT_CODE
    except Exception:
        # Anything else: a corrupt database, a migration that fails, a
        # permissions problem on app-data. Logged here rather than left to
        # propagate, because Python's default excepthook writes the traceback
        # straight to stderr without going through `logging` -- so it never
        # reached the rotating file log installed a few lines above, and the
        # Flutter supervisor drains the sidecar's stderr to keep its pipe from
        # filling up (`app/lib/core/sidecar_platform_io.dart`). The reason for
        # the failure was being discarded at both ends, while the error screen
        # told the user to go read `sidecar.log` (Issue #24 review round 2).
        sock.close()
        logging.getLogger(__name__).exception("sidecar startup failed")
        return STARTUP_FAILED_EXIT_CODE

    # Only now, once this process is certain it will go on to serve: an
    # earlier write (the original placement) meant every failure between it
    # and `Server.run` -- a locked data root, a failed migration, a corrupt
    # database -- still left behind a handshake file naming a host:port that
    # nothing would ever answer on, which a supervisor reading it can only
    # tell apart from a slow start by waiting out its whole timeout.
    _emit_handshake(
        Handshake(host=LOOPBACK, port=port, token=token),
        args.handshake_file,
    )

    config = uvicorn.Config(
        app,
        host=LOOPBACK,
        port=port,
        log_config=None,
        access_log=True,
    )
    # sockets=[sock], not host=/port= alone: uvicorn would otherwise bind a
    # *new* socket to config.port itself, reopening exactly the gap
    # _bind_socket exists to close.
    try:
        uvicorn.Server(config).run(sockets=[sock])
    except Exception:
        # Same reasoning as the startup handler above: after this point the
        # supervisor reports a `crashed` sidecar and sends the user to the
        # log, so the log has to say why. uvicorn owns the socket by now and
        # closes it as it unwinds.
        logging.getLogger(__name__).exception("sidecar stopped serving")
        return STARTUP_FAILED_EXIT_CODE
    return 0


def shared_adc_token_source(
    build: Callable[[str | None], AdcTokenSource] = lambda project_id: AdcTokenSource(
        project_id=project_id
    ),
) -> Callable[[str | None], AdcTokenSource]:
    """One ADC resolution, reused by everything in this process that needs it.

    Grading, 採点基準 extraction, answer-area detection and OCR all
    authenticate with the same credentials, and resolving them is not free --
    measured at ~300ms per call on a host with a `gcloud` login. There are
    four consumers now (Issues #103, #105 and #114 each added one), so
    without this the sidecar paid that four times at startup for no benefit.
    This lives in the composition root because that is the one place that
    knows they all exist; no factory should have to know about the others.

    Document AI is not Vertex AI, but it takes the same
    ``cloud-platform``-scoped ADC token, so it shares this cache rather than
    resolving a second, identical one.

    Keyed by project id, because `AUTO_SCORING_VERTEX_PROJECT` can point the
    two at different projects in principle, and a cache that ignored that
    would hand back credentials for the wrong one.

    **Failures are deliberately not cached.** `AdcCredentialsError` is raised
    afresh on every call, so each factory classifies a missing login exactly
    as it would with a token source of its own.
    """
    resolved: dict[str | None, AdcTokenSource] = {}

    def factory(project_id: str | None) -> AdcTokenSource:
        if project_id not in resolved:
            resolved[project_id] = build(project_id)
        return resolved[project_id]

    return factory


def main() -> None:
    raise SystemExit(run())


if __name__ == "__main__":
    main()
