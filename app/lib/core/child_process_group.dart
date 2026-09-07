/// Ties the sidecar's lifetime to this app's, so it cannot outlive us.
///
/// [SidecarSupervisor] already kills the sidecar on a clean exit, but "clean"
/// is exactly what a crash, a `taskkill`, or End Task in Task Manager is not:
/// none of them run any Dart code, and the orphaned sidecar would keep its
/// loopback port and its exclusive lock on `app-data/` -- so the next launch
/// would fail with "already running" and the user would have no way to tell
/// why (Issue #24: 二重起動・crash・通常終了後にport/processが残らない).
///
/// Windows solves this with a Job Object: a kernel object that owns a set of
/// processes and, with `JOB_OBJECT_LIMIT_KILL_ON_JOB_CLOSE`, terminates all of
/// them when its last handle closes. The OS closes every handle a process
/// holds when that process dies, however it dies -- so the guarantee costs
/// nothing at exit and survives paths no exit handler would.
library;

import 'dart:ffi';
import 'dart:io';

import 'package:ffi/ffi.dart';

/// Enrols child processes so the OS cleans them up if this process does not.
abstract interface class ChildProcessGroup {
  /// Adopts the process with [pid]. Best-effort: a failure is not fatal,
  /// because [SidecarSupervisor.shutdown]'s explicit kill still covers the
  /// ordinary exit path.
  void adopt(int pid);

  /// The right implementation for the host: a Job Object on Windows, and a
  /// no-op everywhere else.
  ///
  /// A no-op rather than a POSIX process group because Windows is the only
  /// platform this app is distributed for (`docs/technology-stack.md` §7-1);
  /// on a developer's Linux or macOS machine the supervisor's explicit kill
  /// is the whole story, and the "leftover process after a crash" this
  /// prevents is a Windows-installer concern. macOS/Linux distribution --
  /// where a `setsid` process group would be the equivalent -- is explicitly
  /// out of scope for this issue.
  factory ChildProcessGroup.forCurrentPlatform() {
    if (!Platform.isWindows) return const _UnsupportedChildProcessGroup();
    return WindowsJobObject();
  }
}

class _UnsupportedChildProcessGroup implements ChildProcessGroup {
  const _UnsupportedChildProcessGroup();

  @override
  void adopt(int pid) {}
}

/// `JOBOBJECTINFOCLASS.JobObjectExtendedLimitInformation`.
const int _jobObjectExtendedLimitInformation = 9;

/// `JOB_OBJECT_LIMIT_KILL_ON_JOB_CLOSE`: terminate every process in the job
/// when the last handle to it closes.
const int _jobObjectLimitKillOnJobClose = 0x00002000;

/// `PROCESS_TERMINATE | PROCESS_SET_QUOTA` -- the exact rights
/// `AssignProcessToJobObject` requires on the process handle, and nothing
/// more.
const int _processAccessRights = 0x0001 | 0x0100;

/// `sizeof(JOBOBJECT_EXTENDED_LIMIT_INFORMATION)`, and the offset of the one
/// field we set inside it.
///
/// The struct is allocated as raw bytes rather than declared as three nested
/// `ffi.Struct`s (`JOBOBJECT_BASIC_LIMIT_INFORMATION`, `IO_COUNTERS`, and the
/// four trailing `SIZE_T`s) because every field but `LimitFlags` is left at
/// zero, and zeroed memory is exactly what "no limit" means for all of them.
/// The layout is the stable Win32 x64/arm64 ABI:
///
/// ```text
///   0  PerProcessUserTimeLimit   LARGE_INTEGER  8
///   8  PerJobUserTimeLimit       LARGE_INTEGER  8
///  16  LimitFlags                DWORD          4   <- the only field we set
///  20  (padding to 8-byte align)                4
///  24  MinimumWorkingSetSize     SIZE_T         8
///  32  MaximumWorkingSetSize     SIZE_T         8
///  40  ActiveProcessLimit        DWORD          4
///  44  (padding)                                4
///  48  Affinity                  ULONG_PTR      8
///  56  PriorityClass             DWORD          4
///  60  SchedulingClass           DWORD          4
///  64  IoInfo                    IO_COUNTERS   48
/// 112  ProcessMemoryLimit        SIZE_T         8
/// 120  JobMemoryLimit            SIZE_T         8
/// 128  PeakProcessMemoryUsed     SIZE_T         8
/// 136  PeakJobMemoryUsed         SIZE_T         8
///                                        total 144
/// ```
const int _extendedLimitInformationSize = 144;
const int _limitFlagsOffset = 16;

typedef _CreateJobObjectNative =
    IntPtr Function(Pointer<Void> attributes, Pointer<Utf16> name);
typedef _CreateJobObject =
    int Function(Pointer<Void> attributes, Pointer<Utf16> name);

typedef _SetInformationJobObjectNative =
    Int32 Function(
      IntPtr job,
      Int32 infoClass,
      Pointer<Void> info,
      Uint32 length,
    );
typedef _SetInformationJobObject =
    int Function(int job, int infoClass, Pointer<Void> info, int length);

typedef _OpenProcessNative =
    IntPtr Function(Uint32 access, Int32 inheritHandle, Uint32 pid);
typedef _OpenProcess = int Function(int access, int inheritHandle, int pid);

typedef _AssignProcessToJobObjectNative =
    Int32 Function(IntPtr job, IntPtr process);
typedef _AssignProcessToJobObject = int Function(int job, int process);

typedef _CloseHandleNative = Int32 Function(IntPtr handle);
typedef _CloseHandle = int Function(int handle);

/// A `kill on close` Job Object, created once and held open for the life of
/// the app.
///
/// Only ever constructed on Windows ([ChildProcessGroup.forCurrentPlatform]);
/// the `kernel32.dll` lookups below would throw anywhere else. The class is
/// still compiled and analysed on every platform, which is what keeps
/// `flutter analyze` and `flutter test` on Linux honest about it.
class WindowsJobObject implements ChildProcessGroup {
  WindowsJobObject() : this._(DynamicLibrary.open('kernel32.dll'));

  WindowsJobObject._(DynamicLibrary kernel32)
    : _createJobObject = kernel32
          .lookupFunction<_CreateJobObjectNative, _CreateJobObject>(
            'CreateJobObjectW',
          ),
      _setInformationJobObject = kernel32
          .lookupFunction<
            _SetInformationJobObjectNative,
            _SetInformationJobObject
          >('SetInformationJobObject'),
      _openProcess = kernel32.lookupFunction<_OpenProcessNative, _OpenProcess>(
        'OpenProcess',
      ),
      _assignProcessToJobObject = kernel32
          .lookupFunction<
            _AssignProcessToJobObjectNative,
            _AssignProcessToJobObject
          >('AssignProcessToJobObject'),
      _closeHandle = kernel32.lookupFunction<_CloseHandleNative, _CloseHandle>(
        'CloseHandle',
      );

  final _CreateJobObject _createJobObject;
  final _SetInformationJobObject _setInformationJobObject;
  final _OpenProcess _openProcess;
  final _AssignProcessToJobObject _assignProcessToJobObject;
  final _CloseHandle _closeHandle;

  /// Created on first use and then never closed: closing it is precisely what
  /// kills the children, so the only handle-close that should ever happen is
  /// the implicit one when this process exits.
  ///
  /// Unnamed (`nullptr` name), so it is private to this process rather than
  /// something a second instance could open by name and join.
  int? _job;

  int? _ensureJob() {
    final existing = _job;
    if (existing != null) return existing;

    final job = _createJobObject(nullptr, nullptr);
    if (job == 0) return null;

    final info = calloc<Uint8>(_extendedLimitInformationSize);
    try {
      info.cast<Uint32>()[_limitFlagsOffset ~/ 4] =
          _jobObjectLimitKillOnJobClose;
      final ok = _setInformationJobObject(
        job,
        _jobObjectExtendedLimitInformation,
        info.cast<Void>(),
        _extendedLimitInformationSize,
      );
      if (ok == 0) {
        // Without the kill-on-close limit the job would adopt children and
        // then let them survive us, which is worse than not having one: it
        // would look like the guarantee holds.
        _closeHandle(job);
        return null;
      }
    } finally {
      calloc.free(info);
    }

    return _job = job;
  }

  @override
  void adopt(int pid) {
    final job = _ensureJob();
    if (job == null) return;

    // A pid alone is not enough -- the job APIs work on handles -- and the
    // handle is closed again immediately: the *job* now holds its own
    // reference to the process, so ours has done its job.
    final process = _openProcess(_processAccessRights, 0, pid);
    if (process == 0) return;
    try {
      _assignProcessToJobObject(job, process);
    } finally {
      _closeHandle(process);
    }
  }
}
