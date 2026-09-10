import type {
  SidecarConnectionInfo,
  SidecarFailure,
  SidecarStatus,
} from "../shared/bridge";
import {
  NodeSidecarPlatform,
  type SidecarPlatform,
  type SidecarProcessHandle,
} from "./sidecar-platform";

/**
 * Startup timeout for the sidecar process (UG-08).
 * 60 seconds allows for initial database migration and Windows Defender scans.
 */
export const SIDECAR_STARTUP_TIMEOUT_MS = 60_000;

/** Polling interval for handshake and health check probes. */
export const SIDECAR_POLL_INTERVAL_MS = 250;

/**
 * Exit code indicating another instance holds the app-data lock (INV-040).
 * Matches `auto_scoring.api.sidecar.ALREADY_RUNNING_EXIT_CODE`.
 */
export const SIDECAR_ALREADY_RUNNING_EXIT_CODE = 3;

export interface SidecarSupervisorOptions {
  readonly platform?: SidecarPlatform | undefined;
  readonly executablePath?: string | null | undefined;
  readonly appDataDirectory?: string | null | undefined;
  readonly startupTimeoutMs?: number | undefined;
  readonly pollIntervalMs?: number | undefined;
  readonly onStatusChange?: ((status: SidecarStatus) => void) | undefined;
}

/**
 * Supervises the Python sidecar process lifecycle from the Electron main process.
 */
export class SidecarSupervisor {
  private readonly _platform: SidecarPlatform;
  private readonly _executablePath: string | null;
  private readonly _appDataDirectory: string | null;
  private readonly _startupTimeoutMs: number;
  private readonly _pollIntervalMs: number;
  private readonly _onStatusChange:
    ((status: SidecarStatus) => void) | undefined;

  private _status: SidecarStatus = { kind: "starting" };
  private _processHandle: SidecarProcessHandle | null = null;
  private _generation = 0;

  constructor(options: SidecarSupervisorOptions = {}) {
    this._platform = options.platform ?? new NodeSidecarPlatform();
    this._executablePath = options.executablePath ?? null;
    this._appDataDirectory = options.appDataDirectory ?? null;
    this._startupTimeoutMs =
      options.startupTimeoutMs ?? SIDECAR_STARTUP_TIMEOUT_MS;
    this._pollIntervalMs = options.pollIntervalMs ?? SIDECAR_POLL_INTERVAL_MS;
    this._onStatusChange = options.onStatusChange;
  }

  get status(): SidecarStatus {
    return this._status;
  }

  get processHandle(): SidecarProcessHandle | null {
    return this._processHandle;
  }

  /**
   * Starts or restarts the sidecar process (INV-032).
   */
  async start(): Promise<void> {
    await this._terminateCurrentProcess();
    const generation = ++this._generation;
    this._setStatus({ kind: "starting" });

    if (!this._executablePath) {
      this._fail(generation, "executableMissing", null);
      return;
    }

    const { dirPath, filePath } =
      await this._platform.createHandshakeDirectory();

    const args = [
      "--port",
      "0",
      "--handshake-file",
      filePath,
      // UG-01: Pass parent pid to trigger Python parent watchdog
      "--parent-pid",
      String(this._platform.currentPid()),
    ];

    // UG-06: Only pass --app-data-dir when explicitly configured (e.g. in tests)
    if (this._appDataDirectory) {
      args.push("--app-data-dir", this._appDataDirectory);
    }

    let handle: SidecarProcessHandle;
    try {
      handle = await this._platform.start(this._executablePath, args);
    } catch {
      await this._platform.deleteHandshakeDirectory(dirPath);
      this._fail(generation, "executableMissing", null);
      return;
    }

    if (generation !== this._generation) {
      handle.kill("SIGKILL");
      await this._platform.deleteHandshakeDirectory(dirPath);
      return;
    }

    this._processHandle = handle;

    let childExited = false;
    let childExitCode: number | null = null;
    void handle.exitCode.then((code) => {
      childExited = true;
      childExitCode = code;
    });

    const deadline = this._platform.now() + this._startupTimeoutMs;
    let connection: SidecarConnectionInfo | null = null;

    while (this._platform.now() < deadline) {
      if (generation !== this._generation) {
        await this._platform.deleteHandshakeDirectory(dirPath);
        return;
      }

      // INV-039: Report immediate exit without waiting out the timeout
      if (childExited) {
        await this._platform.deleteHandshakeDirectory(dirPath);
        const failure: SidecarFailure =
          childExitCode === SIDECAR_ALREADY_RUNNING_EXIT_CODE
            ? "alreadyRunning"
            : "exitedDuringStartup";
        this._fail(generation, failure, childExitCode);
        return;
      }

      // INV-037: Retry reading handshake file until valid JSON is received
      if (!connection) {
        connection = await this._readConnection(filePath);
      }

      if (connection) {
        const baseUrl = `http://${connection.host}:${connection.port}`;
        const healthy = await this._platform.probeHealth(baseUrl);
        if (healthy) {
          // INV-038: Delete handshake directory immediately after successful read & health
          await this._platform.deleteHandshakeDirectory(dirPath);
          if (generation !== this._generation) {
            return;
          }

          this._setStatus({ kind: "ready", connection });

          // INV-041: Monitor crash after ready; ignored if generation changed
          void handle.exitCode.then((code) => {
            if (generation === this._generation) {
              this._fail(generation, "crashed", code);
            }
          });
          return;
        }
      }

      await this._platform.delay(this._pollIntervalMs);
    }

    // Startup timed out
    await this._platform.deleteHandshakeDirectory(dirPath);
    if (generation !== this._generation) {
      return;
    }

    try {
      handle.kill("SIGKILL");
      await handle.exitCode;
    } catch {
      // Best-effort
    }

    this._fail(generation, "startupTimedOut", null);
  }

  /**
   * Alias for start to cleanly restart the sidecar.
   */
  async restart(): Promise<void> {
    return this.start();
  }

  /**
   * Shuts down the sidecar on app exit (INV-031).
   */
  async shutdown(): Promise<void> {
    this._generation++;
    await this._terminateCurrentProcess();
    this._setStatus({ kind: "stopped" });
  }

  private async _readConnection(
    filePath: string,
  ): Promise<SidecarConnectionInfo | null> {
    const raw = await this._platform.readHandshakeFile(filePath);
    if (!raw || raw.trim().length === 0) {
      return null;
    }

    try {
      const parsed = JSON.parse(raw.trim()) as unknown;
      if (
        typeof parsed === "object" &&
        parsed !== null &&
        "host" in parsed &&
        "port" in parsed &&
        "token" in parsed
      ) {
        const host = (parsed as { host: unknown }).host;
        const port = (parsed as { port: unknown }).port;
        const token = (parsed as { token: unknown }).token;
        if (
          typeof host === "string" &&
          typeof port === "number" &&
          typeof token === "string" &&
          host.length > 0 &&
          port > 0 &&
          token.length > 0
        ) {
          return { host, port, token };
        }
      }
    } catch {
      return null;
    }

    return null;
  }

  private _setStatus(status: SidecarStatus): void {
    this._status = status;
    this._onStatusChange?.(status);
  }

  private _fail(
    generation: number,
    failure: SidecarFailure,
    exitCode: number | null,
  ): void {
    if (generation !== this._generation) {
      return;
    }
    this._processHandle = null;
    this._setStatus({ kind: "failed", failure, exitCode });
  }

  private async _terminateCurrentProcess(timeoutMs = 5000): Promise<void> {
    const handle = this._processHandle;
    this._processHandle = null;
    if (!handle) {
      return;
    }

    let settled = false;
    await new Promise<void>((resolve) => {
      const timer = setTimeout(() => {
        if (!settled) {
          settled = true;
          try {
            handle.kill("SIGKILL");
          } catch {
            // Ignore
          }
          resolve();
        }
      }, timeoutMs);

      void handle.exitCode.finally(() => {
        if (!settled) {
          settled = true;
          clearTimeout(timer);
          resolve();
        }
      });

      try {
        handle.kill("SIGTERM");
      } catch {
        if (!settled) {
          settled = true;
          clearTimeout(timer);
          resolve();
        }
      }
    });
  }
}
