/// Choosing a folder of grading material and reading what is in it
/// (Issue #101).
///
/// The reviewer is handed a folder by their cram school and selects it whole;
/// the app walks it, hashes each file, and sends only that listing to the
/// sidecar to be planned. **No file content leaves this function** -- the
/// bytes are read to compute a digest and discarded.
///
/// Both operations are provided rather than called directly so widget tests
/// can drive the screen without a real folder on disk (`AGENTS.md`: inject
/// boundaries from outside).
library;

import 'dart:io';

import 'package:crypto/crypto.dart';
import 'package:file_picker/file_picker.dart' as picker;
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:path/path.dart' as p;

/// One file found under the chosen folder.
class ScannedEntry {
  const ScannedEntry({
    required this.relativePath,
    required this.absolutePath,
    required this.sizeBytes,
    required this.sha256,
  });

  /// POSIX-separated, relative to the chosen folder. This is what groups the
  /// file and what the plan echoes back.
  ///
  /// It carries the school's own course names, so it must not reach a log
  /// line or anything published.
  final String relativePath;

  /// Where to read it from when it is actually uploaded.
  final String absolutePath;

  final int sizeBytes;

  /// Content digest. Keyed on rather than the name because the same document
  /// under a different name is the same document -- it is what stops the app
  /// paying to classify content it has already classified.
  final String sha256;

  String get fileName => relativePath.split('/').last;
}

/// A chosen folder and everything under it.
class ScannedFolder {
  const ScannedFolder({required this.name, required this.entries});

  /// The folder's own name, offered as the test name when the batch is not
  /// split into child folders.
  final String name;
  final List<ScannedEntry> entries;
}

/// Files never worth listing. Excluded here rather than by a template rule so
/// no template has to carry a rule for them, and so a reviewer never has to
/// look at one on the confirmation screen.
const Set<String> _ignoredFileNames = {'.ds_store', 'thumbs.db', 'desktop.ini'};

/// Upper bound on how many files one scan will list.
///
/// A real batch is around seventy. This is far above that and far below "walk
/// a home directory the reviewer picked by accident" -- which would otherwise
/// hash every file on their disk before showing anything.
const int maxScannedFiles = 5000;

/// Raised when the chosen folder holds more than [maxScannedFiles] files.
class FolderTooLargeException implements Exception {
  const FolderTooLargeException(this.found);

  final int found;

  @override
  String toString() =>
      'このフォルダには$found件以上のファイルがあります。'
      '取り込む資料が入ったフォルダを選んでください。';
}

Future<String?> _chooseDirectoryFromNativeDialog() =>
    picker.FilePicker.getDirectoryPath();

Future<ScannedFolder> _scanDirectory(String directoryPath) async {
  final directory = Directory(directoryPath);
  final entries = <ScannedEntry>[];
  await for (final entity in directory.list(recursive: true)) {
    if (entity is! File) continue;
    final name = p.basename(entity.path);
    // A hidden file is metadata the operating system or an editor left
    // behind, never material somebody meant to hand over.
    if (name.startsWith('.') ||
        _ignoredFileNames.contains(name.toLowerCase())) {
      continue;
    }
    if (entries.length >= maxScannedFiles) {
      throw FolderTooLargeException(maxScannedFiles);
    }
    final relative = p
        .relative(entity.path, from: directoryPath)
        .replaceAll(r'\', '/');
    // Streamed, not read whole: a batch holds scanned PDFs, and materializing
    // every one of them at once to hash it would spend far more memory than
    // the digest is worth.
    final digest = await sha256.bind(entity.openRead()).first;
    entries.add(
      ScannedEntry(
        relativePath: relative,
        absolutePath: entity.path,
        sizeBytes: await entity.length(),
        sha256: digest.toString(),
      ),
    );
  }
  entries.sort((a, b) => a.relativePath.compareTo(b.relativePath));
  return ScannedFolder(name: p.basename(directoryPath), entries: entries);
}

/// Opens the native "choose a folder" dialog, or resolves to `null` if the
/// reviewer cancelled.
final chooseFolderProvider = Provider<Future<String?> Function()>(
  (ref) => _chooseDirectoryFromNativeDialog,
);

/// Walks a chosen folder and hashes what is in it.
final scanFolderProvider = Provider<Future<ScannedFolder> Function(String)>(
  (ref) => _scanDirectory,
);
