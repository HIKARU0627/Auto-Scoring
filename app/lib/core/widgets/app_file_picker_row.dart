import 'package:flutter/material.dart';

import 'package:auto_scoring_app/core/design/design_tokens.dart';

/// 「PDFを選ぶボタン + 選んだファイル名」の1行。
///
/// 資料取込画面 (採点基準/答案/添削資料) and テスト設定画面 both need it, and
/// both had built it by hand with slightly different gaps.
///
/// The file name is shown next to the button rather than replacing its label,
/// so the control that opens the picker keeps saying what it picks even after
/// something has been picked.
class AppFilePickerRow extends StatelessWidget {
  const AppFilePickerRow({
    super.key,
    this.buttonKey,
    required this.buttonLabel,
    required this.fileName,
    required this.onPressed,
    this.emptyLabel = '未選択',
  });

  /// Goes on the button rather than the row, because the button is what a
  /// widget test taps -- the row's centre is in the file-name text.
  final Key? buttonKey;

  final String buttonLabel;

  /// `null` until the reviewer picks a file; [emptyLabel] stands in.
  final String? fileName;

  /// `null` disables the button (a submit is in flight).
  final VoidCallback? onPressed;

  final String emptyLabel;

  @override
  Widget build(BuildContext context) {
    return Row(
      children: [
        OutlinedButton.icon(
          key: buttonKey,
          onPressed: onPressed,
          icon: const Icon(Icons.picture_as_pdf),
          label: Text(buttonLabel),
        ),
        const SizedBox(width: AppSpacing.md),
        Expanded(
          child: Text(
            fileName ?? emptyLabel,
            // A long Windows file name must not push the button off screen.
            overflow: TextOverflow.ellipsis,
          ),
        ),
      ],
    );
  }
}
