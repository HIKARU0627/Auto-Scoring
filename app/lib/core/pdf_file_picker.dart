import 'package:file_picker/file_picker.dart' as picker;
import 'package:flutter_riverpod/flutter_riverpod.dart';

/// A PDF chosen from the native file picker.
///
/// Kept separate from `package:file_picker`'s own `PlatformFile` so the
/// screens that ask for a PDF can be driven by a fake in widget tests without
/// touching a platform channel.
class PickedPdfFile {
  const PickedPdfFile({required this.path, required this.name});

  final String path;
  final String name;
}

Future<PickedPdfFile?> _pickPdfFromNativeDialog() async {
  final picked = await picker.FilePicker.pickFile(
    type: picker.FileType.custom,
    allowedExtensions: const ['pdf'],
  );
  if (picked?.path == null) return null;
  return PickedPdfFile(path: picked!.path!, name: picked.name);
}

/// Opens the native "choose a PDF" dialog, or resolves to `null` if the user
/// cancelled.
///
/// A provider rather than a constructor parameter because 答案取込 and テスト登録
/// are both reached through the route table (`lib/app_router.dart`), which
/// builds them from their path alone: `ProviderScope(overrides: ...)` is the
/// one seam a widget test still has. See `test/app_harness.dart`.
final pickPdfFileProvider = Provider<Future<PickedPdfFile?> Function()>(
  (ref) => _pickPdfFromNativeDialog,
);
