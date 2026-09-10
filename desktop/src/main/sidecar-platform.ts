import { spawn } from "node:child_process";
import * as fs from "node:fs";
import * as http from "node:http";
import * as os from "node:os";
import * as path from "node:path";

/**
 * Handle to a spawned child process narrowed to supervision requirements.
 */
export interface SidecarProcessHandle {
  readonly pid: number | undefined;
  readonly exitCode: Promise<number | null>;
  kill(signal?: NodeJS.Signals): void;
}

/**
 * Platform boundary abstractions for file, network, process, and timing operations.
 * Allows pure state-machine unit tests without touching the OS or clock.
 */
export interface SidecarPlatform {
  createHandshakeDirectory(): Promise<{ dirPath: string; filePath: string }>;
  readHandshakeFile(filePath: string): Promise<string | null>;
  deleteHandshakeDirectory(dirPath: string): Promise<void>;
  start(executable: string, args: string[]): Promise<SidecarProcessHandle>;
  probeHealth(baseUrl: string): Promise<boolean>;
  delay(ms: number): Promise<void>;
  now(): number;
  currentPid(): number;
}

/**
 * Concrete SidecarPlatform implementation using Node.js standard runtime APIs.
 */
export class NodeSidecarPlatform implements SidecarPlatform {
  async createHandshakeDirectory(): Promise<{
    dirPath: string;
    filePath: string;
  }> {
    const dirPath = fs.mkdtempSync(
      path.join(os.tmpdir(), "auto-scoring-handshake-"),
    );
    const filePath = path.join(dirPath, "handshake.json");
    return { dirPath, filePath };
  }

  async readHandshakeFile(filePath: string): Promise<string | null> {
    try {
      if (!fs.existsSync(filePath)) {
        return null;
      }
      return fs.readFileSync(filePath, "utf8");
    } catch {
      return null;
    }
  }

  async deleteHandshakeDirectory(dirPath: string): Promise<void> {
    try {
      if (fs.existsSync(dirPath)) {
        fs.rmSync(dirPath, { recursive: true, force: true });
      }
    } catch {
      // Best-effort cleanup
    }
  }

  async start(
    executable: string,
    args: string[],
  ): Promise<SidecarProcessHandle> {
    return new Promise((resolve, reject) => {
      let settled = false;

      const child = spawn(executable, args, {
        stdio: ["ignore", "pipe", "pipe"],
      });

      // UG-07: Always drain stdout and stderr to prevent pipe buffer deadlocks
      child.stdout?.on("data", () => {});
      child.stderr?.on("data", () => {});

      const exitPromise = new Promise<number | null>((resolveExit) => {
        child.once("exit", (code) => {
          resolveExit(code);
        });
        child.once("error", (err) => {
          if (!settled) {
            settled = true;
            reject(err);
          }
          resolveExit(null);
        });
      });

      child.once("spawn", () => {
        if (!settled) {
          settled = true;
          resolve({
            pid: child.pid,
            exitCode: exitPromise,
            kill: (signal = "SIGTERM") => {
              try {
                child.kill(signal);
              } catch {
                // Process may already be dead
              }
            },
          });
        }
      });

      child.once("error", (err) => {
        if (!settled) {
          settled = true;
          reject(err);
        }
      });
    });
  }

  async probeHealth(baseUrl: string): Promise<boolean> {
    return new Promise((resolve) => {
      try {
        const url = new URL("/healthz", baseUrl);
        const req = http.request(
          url,
          {
            method: "GET",
            timeout: 1000,
          },
          (res) => {
            res.resume(); // drain response body
            resolve(res.statusCode === 200);
          },
        );

        req.on("timeout", () => {
          req.destroy();
          resolve(false);
        });
        req.on("error", () => {
          resolve(false);
        });
        req.end();
      } catch {
        resolve(false);
      }
    });
  }

  async delay(ms: number): Promise<void> {
    return new Promise((resolve) => setTimeout(resolve, ms));
  }

  now(): number {
    return Date.now();
  }

  currentPid(): number {
    return process.pid;
  }
}
