import { describe, expect, it } from "vitest";
import {
  SIDECAR_ALREADY_RUNNING_EXIT_CODE,
  SIDECAR_STARTUP_TIMEOUT_MS,
  SidecarSupervisor,
} from "../src/main/sidecar-supervisor";
import type {
  SidecarPlatform,
  SidecarProcessHandle,
} from "../src/main/sidecar-platform";

interface SpawnCall {
  readonly executable: string;
  readonly args: string[];
}

class FakeProcessHandle implements SidecarProcessHandle {
  readonly pid = 99999;
  private _resolveExit!: (code: number | null) => void;
  readonly exitCode = new Promise<number | null>((resolve) => {
    this._resolveExit = resolve;
  });

  killed = false;
  killSignal: string | null = null;

  kill(signal: NodeJS.Signals = "SIGTERM"): void {
    this.killed = true;
    this.killSignal = signal;
    this._resolveExit(-1);
  }

  exitProcess(code: number): void {
    this._resolveExit(code);
  }
}

class FakeSidecarPlatform implements SidecarPlatform {
  currentTime = 1_000_000;
  healthy = false;
  pollCount = 0;
  onPoll?: (poll: number) => void;

  createdDirs: string[] = [];
  deletedDirs: string[] = [];
  handshakeContents: string | null = null;
  spawns: SpawnCall[] = [];
  spawnError: Error | null = null;
  lastHandle?: FakeProcessHandle;

  async createHandshakeDirectory(): Promise<{
    dirPath: string;
    filePath: string;
  }> {
    const dirPath = `/tmp/fake-handshake-${this.createdDirs.length}`;
    this.createdDirs.push(dirPath);
    return { dirPath, filePath: `${dirPath}/handshake.json` };
  }

  async readHandshakeFile(_filePath: string): Promise<string | null> {
    return this.handshakeContents;
  }

  async deleteHandshakeDirectory(dirPath: string): Promise<void> {
    this.deletedDirs.push(dirPath);
  }

  async start(
    executable: string,
    args: string[],
  ): Promise<SidecarProcessHandle> {
    if (this.spawnError) {
      throw this.spawnError;
    }
    this.spawns.push({ executable, args });
    const handle = new FakeProcessHandle();
    this.lastHandle = handle;
    return handle;
  }

  async probeHealth(_baseUrl: string): Promise<boolean> {
    return this.healthy;
  }

  async delay(ms: number): Promise<void> {
    this.currentTime += ms;
    this.pollCount++;
    this.onPoll?.(this.pollCount);
  }

  now(): number {
    return this.currentTime;
  }

  currentPid(): number {
    return 12345;
  }

  writeHandshake(port = 51234, token = "test-token-value"): void {
    this.handshakeContents = JSON.stringify({
      host: "127.0.0.1",
      port,
      token,
    });
  }
}

describe("SidecarSupervisor unit tests", () => {
  it("reaches ready once the handshake parses and health check passes (INV-030)", async () => {
    const platform = new FakeSidecarPlatform();
    platform.onPoll = (poll) => {
      if (poll === 2) {
        platform.writeHandshake(51234, "secret-token-abc");
      }
      if (poll >= 4) {
        platform.healthy = true;
      }
    };

    const supervisor = new SidecarSupervisor({
      platform,
      executablePath: "/opt/sidecar",
    });

    await supervisor.start();

    expect(supervisor.status.kind).toBe("ready");
    if (supervisor.status.kind === "ready") {
      expect(supervisor.status.connection.host).toBe("127.0.0.1");
      expect(supervisor.status.connection.port).toBe(51234);
      expect(supervisor.status.connection).not.toHaveProperty("token");
    }
    if (supervisor.internalStatus.kind === "ready") {
      expect(supervisor.internalStatus.connection.token).toBe(
        "secret-token-abc",
      );
    }
  });

  it("passes --port 0, --handshake-file, and --parent-pid (UG-01)", async () => {
    const platform = new FakeSidecarPlatform();
    platform.healthy = true;
    platform.onPoll = () => platform.writeHandshake();

    const supervisor = new SidecarSupervisor({
      platform,
      executablePath: "/opt/sidecar",
    });

    await supervisor.start();

    expect(platform.spawns.length).toBe(1);
    const spawnCall = platform.spawns[0]!;
    expect(spawnCall.executable).toBe("/opt/sidecar");
    expect(spawnCall.args).toContain("--port");
    expect(spawnCall.args).toContain("0");
    expect(spawnCall.args).toContain("--handshake-file");
    expect(spawnCall.args).toContain("--parent-pid");
    expect(spawnCall.args).toContain("12345");
  });

  it("omits --app-data-dir unless configured, and passes it when configured (UG-06)", async () => {
    const platform1 = new FakeSidecarPlatform();
    platform1.healthy = true;
    platform1.onPoll = () => platform1.writeHandshake();

    const supervisorDefault = new SidecarSupervisor({
      platform: platform1,
      executablePath: "/opt/sidecar",
    });
    await supervisorDefault.start();
    expect(platform1.spawns[0]!.args).not.toContain("--app-data-dir");

    const platform2 = new FakeSidecarPlatform();
    platform2.healthy = true;
    platform2.onPoll = () => platform2.writeHandshake();

    const supervisorCustom = new SidecarSupervisor({
      platform: platform2,
      executablePath: "/opt/sidecar",
      appDataDirectory: "/custom/data",
    });
    await supervisorCustom.start();
    expect(platform2.spawns[0]!.args).toContain("--app-data-dir");
    expect(platform2.spawns[0]!.args).toContain("/custom/data");
  });

  describe("handshake reading retries (INV-037)", () => {
    const invalidPayloads = [
      ["empty file", ""],
      ["whitespace only", "   \n\t  "],
      ["truncated JSON", '{"host": "127.0.0.1", "po'],
      ["JSON array instead of object", '["127.0.0.1", 1234]'],
      ["missing token", '{"host": "127.0.0.1", "port": 1234}'],
      ["empty token", '{"host": "127.0.0.1", "port": 1234, "token": ""}'],
      [
        "port not a number",
        '{"host": "127.0.0.1", "port": "1234", "token": "t"}',
      ],
    ] as const;

    for (const [description, invalidContent] of invalidPayloads) {
      it(`retries past ${description}`, async () => {
        const platform = new FakeSidecarPlatform();
        platform.handshakeContents = invalidContent;

        platform.onPoll = (poll) => {
          if (poll === 3) {
            platform.writeHandshake(4321, "valid-token");
            platform.healthy = true;
          }
        };

        const supervisor = new SidecarSupervisor({
          platform,
          executablePath: "/opt/sidecar",
        });

        await supervisor.start();
        expect(supervisor.status.kind).toBe("ready");
        if (supervisor.internalStatus.kind === "ready") {
          expect(supervisor.internalStatus.connection.port).toBe(4321);
          expect(supervisor.internalStatus.connection.token).toBe(
            "valid-token",
          );
        }
      });
    }
  });

  it("deletes the handshake directory after token is read (INV-038)", async () => {
    const platform = new FakeSidecarPlatform();
    platform.healthy = true;
    platform.onPoll = () => platform.writeHandshake();

    const supervisor = new SidecarSupervisor({
      platform,
      executablePath: "/opt/sidecar",
    });

    await supervisor.start();

    expect(supervisor.status.kind).toBe("ready");
    expect(platform.deletedDirs).toEqual(platform.createdDirs);
  });

  it("fails without spawning when executable is null (INV-035)", async () => {
    const platform = new FakeSidecarPlatform();
    const supervisor = new SidecarSupervisor({
      platform,
      executablePath: null,
    });

    await supervisor.start();

    expect(supervisor.status.kind).toBe("failed");
    if (supervisor.status.kind === "failed") {
      expect(supervisor.status.failure).toBe("executableMissing");
    }
    expect(platform.spawns.length).toBe(0);
  });

  it("reports a spawn error as executableMissing (INV-035)", async () => {
    const platform = new FakeSidecarPlatform();
    platform.spawnError = new Error("spawn ENOENT");

    const supervisor = new SidecarSupervisor({
      platform,
      executablePath: "/bad/path",
    });

    await supervisor.start();

    expect(supervisor.status.kind).toBe("failed");
    if (supervisor.status.kind === "failed") {
      expect(supervisor.status.failure).toBe("executableMissing");
    }
    expect(platform.deletedDirs).toEqual(platform.createdDirs);
  });

  it("reports an immediate exit without waiting out the timeout (INV-039)", async () => {
    const platform = new FakeSidecarPlatform();
    platform.onPoll = (poll) => {
      if (poll === 1) {
        platform.lastHandle?.exitProcess(1);
      }
    };

    const supervisor = new SidecarSupervisor({
      platform,
      executablePath: "/opt/sidecar",
    });

    const startTime = platform.currentTime;
    await supervisor.start();

    expect(supervisor.status.kind).toBe("failed");
    if (supervisor.status.kind === "failed") {
      expect(supervisor.status.failure).toBe("exitedDuringStartup");
      expect(supervisor.status.exitCode).toBe(1);
    }
    expect(platform.currentTime - startTime).toBeLessThan(5000);
  });

  it("reports exit code 3 as alreadyRunning (INV-034, INV-040)", async () => {
    const platform = new FakeSidecarPlatform();
    platform.onPoll = (poll) => {
      if (poll === 1) {
        platform.lastHandle?.exitProcess(SIDECAR_ALREADY_RUNNING_EXIT_CODE);
      }
    };

    const supervisor = new SidecarSupervisor({
      platform,
      executablePath: "/opt/sidecar",
    });

    await supervisor.start();

    expect(supervisor.status.kind).toBe("failed");
    if (supervisor.status.kind === "failed") {
      expect(supervisor.status.failure).toBe("alreadyRunning");
      expect(supervisor.status.exitCode).toBe(3);
    }
  });

  it("times out and kills sidecar when health probe never passes (UG-08)", async () => {
    const platform = new FakeSidecarPlatform();
    platform.onPoll = () => platform.writeHandshake(); // writes valid handshake but healthy is never true

    const supervisor = new SidecarSupervisor({
      platform,
      executablePath: "/opt/sidecar",
    });

    const startTime = platform.currentTime;
    await supervisor.start();

    expect(supervisor.status.kind).toBe("failed");
    if (supervisor.status.kind === "failed") {
      expect(supervisor.status.failure).toBe("startupTimedOut");
    }
    expect(platform.lastHandle?.killed).toBe(true);
    expect(platform.currentTime - startTime).toBeGreaterThanOrEqual(
      SIDECAR_STARTUP_TIMEOUT_MS,
    );
    expect(platform.deletedDirs).toEqual(platform.createdDirs);
  });

  it("reports exit after ready as crashed (INV-041)", async () => {
    const platform = new FakeSidecarPlatform();
    platform.healthy = true;
    platform.onPoll = () => platform.writeHandshake();

    const supervisor = new SidecarSupervisor({
      platform,
      executablePath: "/opt/sidecar",
    });

    await supervisor.start();
    expect(supervisor.status.kind).toBe("ready");

    platform.lastHandle?.exitProcess(137);
    await new Promise((resolve) => setTimeout(resolve, 0));

    expect(supervisor.status.kind).toBe("failed");
    if (supervisor.status.kind === "failed") {
      expect(supervisor.status.failure).toBe("crashed");
      expect(supervisor.status.exitCode).toBe(137);
    }
  });

  it("shutdown kills the child and does not report crash (INV-031, INV-041)", async () => {
    const platform = new FakeSidecarPlatform();
    platform.healthy = true;
    platform.onPoll = () => platform.writeHandshake();

    const supervisor = new SidecarSupervisor({
      platform,
      executablePath: "/opt/sidecar",
    });

    await supervisor.start();
    expect(supervisor.status.kind).toBe("ready");

    await supervisor.shutdown();
    expect(supervisor.status.kind).toBe("stopped");
    expect(platform.lastHandle?.killed).toBe(true);
  });

  it("restart terminates existing process and starts new attempt (INV-032)", async () => {
    const platform = new FakeSidecarPlatform();
    platform.healthy = true;
    platform.onPoll = () => platform.writeHandshake(50001, "token-1");

    const supervisor = new SidecarSupervisor({
      platform,
      executablePath: "/opt/sidecar",
    });

    await supervisor.start();
    expect(supervisor.status.kind).toBe("ready");
    const firstHandle = platform.lastHandle!;

    platform.writeHandshake(50002, "token-2");
    await supervisor.restart();

    expect(firstHandle.killed).toBe(true);
    expect(supervisor.status.kind).toBe("ready");
    if (supervisor.internalStatus.kind === "ready") {
      expect(supervisor.internalStatus.connection.port).toBe(50002);
      expect(supervisor.internalStatus.connection.token).toBe("token-2");
    }
    expect(platform.spawns.length).toBe(2);
  });

  it("failed state never exposes bearer token (INV-036)", async () => {
    const platform = new FakeSidecarPlatform();
    platform.onPoll = (poll) => {
      if (poll === 1) {
        platform.writeHandshake(50000, "super-secret-token");
        platform.lastHandle?.exitProcess(1);
      }
    };

    const supervisor = new SidecarSupervisor({
      platform,
      executablePath: "/opt/sidecar",
    });

    await supervisor.start();

    expect(supervisor.status.kind).toBe("failed");
    const json = JSON.stringify(supervisor.status);
    expect(json).not.toContain("super-secret-token");
  });
});
