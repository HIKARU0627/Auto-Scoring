import { spawn } from "node:child_process";
import fs from "node:fs";
import http from "node:http";
import net from "node:net";
import os from "node:os";
import path from "node:path";

export const SidecarState = {
  STARTING: "STARTING",
  READY: "READY",
  FAILED: "FAILED",
  STOPPED: "STOPPED",
};

export const SidecarFailure = {
  EXECUTABLE_MISSING: "EXECUTABLE_MISSING",
  ALREADY_RUNNING: "ALREADY_RUNNING",
  EXITED_DURING_STARTUP: "EXITED_DURING_STARTUP",
  STARTUP_TIMED_OUT: "STARTUP_TIMED_OUT",
  CRASHED: "CRASHED",
};

export const ALREADY_RUNNING_EXIT_CODE = 3;

/**
 * Resolves default sidecar executable paths for current platform.
 */
export function resolveDefaultSidecarExecutable(repoRoot) {
  const isWin = process.platform === "win32";
  const exeSuffix = isWin ? ".exe" : "";
  const candidates = [
    // PyInstaller onedir bundle (built via `pnpm run package:sidecar`)
    path.join(
      repoRoot,
      "backend",
      "dist",
      "auto-scoring-sidecar",
      `auto-scoring-sidecar${exeSuffix}`,
    ),
    // venv console script
    path.join(
      repoRoot,
      "backend",
      ".venv",
      isWin ? "Scripts" : "bin",
      `auto-scoring-sidecar${exeSuffix}`,
    ),
  ];

  for (const candidate of candidates) {
    if (fs.existsSync(candidate)) {
      return candidate;
    }
  }
  return null;
}

/**
 * Checks whether a TCP port is open (listening) on loopback.
 */
export function isPortListening(port, host = "127.0.0.1", timeoutMs = 500) {
  return new Promise((resolve) => {
    const socket = new net.Socket();
    let status = false;

    socket.setTimeout(timeoutMs);
    socket.once("connect", () => {
      status = true;
      socket.destroy();
    });
    socket.once("timeout", () => {
      socket.destroy();
    });
    socket.once("error", () => {
      // Connection refused or error -> not listening
      resolve(false);
    });
    socket.once("close", () => {
      resolve(status);
    });

    socket.connect(port, host);
  });
}

/**
 * Makes an HTTP request with timeout.
 */
export function httpRequest(
  urlStr,
  { method = "GET", headers = {}, timeoutMs = 2000 } = {},
) {
  return new Promise((resolve, reject) => {
    const url = new URL(urlStr);
    const req = http.request(
      url,
      {
        method,
        headers,
        timeout: timeoutMs,
      },
      (res) => {
        let data = "";
        res.setEncoding("utf8");
        res.on("data", (chunk) => {
          data += chunk;
        });
        res.on("end", () => {
          resolve({
            statusCode: res.statusCode,
            headers: res.headers,
            body: data,
          });
        });
      },
    );

    req.on("timeout", () => {
      req.destroy(new Error(`HTTP request timed out after ${timeoutMs}ms`));
    });
    req.on("error", (err) => {
      reject(err);
    });
    req.end();
  });
}

/**
 * Supervisor that controls the Python sidecar lifecycle from Electron main process.
 */
export class SidecarSupervisor {
  constructor({
    executablePath,
    appDataDirectory,
    startupTimeoutMs = 60000,
    pollIntervalMs = 100,
  } = {}) {
    this.executablePath = executablePath;
    this.appDataDirectory = appDataDirectory;
    this.startupTimeoutMs = startupTimeoutMs;
    this.pollIntervalMs = pollIntervalMs;

    this.state = SidecarState.STARTING;
    this.failure = null;
    this.exitCode = null;
    this.connection = null;
    this.childProcess = null;
    this.generation = 0;
    this.handshakeDir = null;
  }

  async start() {
    await this._terminateCurrentProcess();
    const generation = ++this.generation;
    this.state = SidecarState.STARTING;
    this.failure = null;
    this.exitCode = null;
    this.connection = null;

    if (!this.executablePath || !fs.existsSync(this.executablePath)) {
      this._fail(generation, SidecarFailure.EXECUTABLE_MISSING);
      return;
    }

    // Create per-attempt temp directory for handshake
    this.handshakeDir = fs.mkdtempSync(
      path.join(os.tmpdir(), "auto-scoring-handshake-"),
    );
    const handshakePath = path.join(this.handshakeDir, "handshake.json");

    const args = ["--port", "0", "--handshake-file", handshakePath];
    if (this.appDataDirectory) {
      args.push("--app-data-dir", this.appDataDirectory);
    }

    let child;
    try {
      child = spawn(this.executablePath, args, {
        stdio: ["ignore", "pipe", "pipe"],
      });
    } catch {
      this._cleanHandshakeDir();
      this._fail(generation, SidecarFailure.EXECUTABLE_MISSING);
      return;
    }

    if (generation !== this.generation) {
      child.kill("SIGKILL");
      this._cleanHandshakeDir();
      return;
    }

    this.childProcess = child;

    // Drain stdout and stderr to prevent pipe buffer stalls
    child.stdout.on("data", () => {});
    child.stderr.on("data", () => {});

    let childExited = false;
    let childExitCode = null;

    child.once("exit", (code) => {
      childExited = true;
      childExitCode = code;
    });

    const deadline = Date.now() + this.startupTimeoutMs;
    let connection = null;

    while (Date.now() < deadline) {
      if (generation !== this.generation) {
        return;
      }

      if (childExited) {
        this._cleanHandshakeDir();
        const failureReason =
          childExitCode === ALREADY_RUNNING_EXIT_CODE
            ? SidecarFailure.ALREADY_RUNNING
            : SidecarFailure.EXITED_DURING_STARTUP;
        this._fail(generation, failureReason, childExitCode);
        return;
      }

      if (!connection) {
        connection = this._readHandshake(handshakePath);
      }

      if (connection) {
        const healthy = await this._probeHealth(connection);
        if (healthy) {
          // Success! Clean up handshake file and directory immediately
          this._cleanHandshakeDir();
          if (generation !== this.generation) return;

          this.connection = connection;
          this.state = SidecarState.READY;

          child.once("exit", (code) => {
            if (generation === this.generation) {
              this._fail(generation, SidecarFailure.CRASHED, code);
            }
          });
          return;
        }
      }

      await new Promise((r) => setTimeout(r, this.pollIntervalMs));
    }

    // Timed out
    this._cleanHandshakeDir();
    if (generation !== this.generation) return;

    try {
      child.kill("SIGKILL");
    } catch {}
    this._fail(generation, SidecarFailure.STARTUP_TIMED_OUT);
  }

  async shutdown({ signal = "SIGTERM", timeoutMs = 5000 } = {}) {
    this.generation++;
    this._cleanHandshakeDir();
    await this._terminateCurrentProcess(signal, timeoutMs);
    this.state = SidecarState.STOPPED;
  }

  _readHandshake(filePath) {
    if (!fs.existsSync(filePath)) {
      return null;
    }
    try {
      const content = fs.readFileSync(filePath, "utf8").trim();
      if (!content) return null;
      const parsed = JSON.parse(content);
      if (
        typeof parsed.host === "string" &&
        typeof parsed.port === "number" &&
        typeof parsed.token === "string" &&
        parsed.host.length > 0 &&
        parsed.port > 0 &&
        parsed.token.length > 0
      ) {
        return {
          host: parsed.host,
          port: parsed.port,
          token: parsed.token,
          baseUrl: `http://${parsed.host}:${parsed.port}`,
        };
      }
    } catch {
      return null;
    }
    return null;
  }

  async _probeHealth(connection) {
    try {
      const res = await httpRequest(`${connection.baseUrl}/healthz`, {
        timeoutMs: 500,
      });
      return res.statusCode === 200;
    } catch {
      return false;
    }
  }

  async probeAuthenticated() {
    if (!this.connection) {
      throw new Error("Sidecar is not ready");
    }
    return await httpRequest(`${this.connection.baseUrl}/tests`, {
      headers: {
        Authorization: `Bearer ${this.connection.token}`,
      },
      timeoutMs: 2000,
    });
  }

  _fail(generation, failure, exitCode = null) {
    if (generation !== this.generation) return;
    this.childProcess = null;
    this.failure = failure;
    this.exitCode = exitCode;
    this.state = SidecarState.FAILED;
  }

  _cleanHandshakeDir() {
    if (this.handshakeDir && fs.existsSync(this.handshakeDir)) {
      try {
        fs.rmSync(this.handshakeDir, { recursive: true, force: true });
      } catch {}
      this.handshakeDir = null;
    }
  }

  async _terminateCurrentProcess(signal = "SIGTERM", timeoutMs = 5000) {
    const child = this.childProcess;
    this.childProcess = null;
    if (!child || child.exitCode !== null) {
      return;
    }

    await new Promise((resolve) => {
      let settled = false;
      const onExit = () => {
        if (!settled) {
          settled = true;
          resolve();
        }
      };

      child.once("exit", onExit);

      try {
        child.kill(signal);
      } catch {
        onExit();
      }

      // If it doesn't terminate within timeoutMs, force kill
      setTimeout(() => {
        if (!settled) {
          try {
            child.kill("SIGKILL");
          } catch {}
        }
      }, timeoutMs);
    });
  }
}
