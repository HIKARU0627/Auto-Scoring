/// Validates one profile region's form fields before they are written back
/// onto a [RegionModel].
///
/// Extracted from `_RegionEditDialogState._save`
/// (`features/test_registration/test_settings_page.dart`, Issue #126). The
/// dialog's own comment already named the trap this guards against:
/// `double.tryParse('NaN')` returns a non-null `double.nan`, and every
/// comparison against it (`<`, `>`, `>=`) is false -- so without the explicit
/// `isFinite` check, an out-of-range coordinate typed as literally "NaN"
/// would sail through validation and reach the server (Issue #16 review
/// round 5). That is exactly the class of defect a widget test drives past
/// without noticing, so it gets a direct one instead.
library;

import 'package:auto_scoring_app/api/sidecar_api_client.dart';

/// The outcome of [validateRegionEdit]: either the region to save, or the
/// message to show instead of saving it. Never both.
typedef RegionEditValidation = ({RegionModel? region, String? error});

/// Validates the raw form fields of a region-edit dialog against [original],
/// returning either the rebuilt region or an error message.
///
/// Field-by-field, in the same order the dialog checked them in, so the
/// first problem found is the one reported.
RegionEditValidation validateRegionEdit({
  required RegionModel original,
  required RegionKind kind,
  required String labelText,
  required String pageText,
  required String x0Text,
  required String y0Text,
  required String x1Text,
  required String y1Text,
  required String contentText,
}) {
  final page = int.tryParse(pageText);
  if (page == null || page < 1) {
    return (region: null, error: 'ページ番号は1以上の整数で入力してください');
  }
  final x0 = double.tryParse(x0Text);
  final y0 = double.tryParse(y0Text);
  final x1 = double.tryParse(x1Text);
  final y1 = double.tryParse(y1Text);
  if (x0 == null ||
      y0 == null ||
      x1 == null ||
      y1 == null ||
      !x0.isFinite ||
      !y0.isFinite ||
      !x1.isFinite ||
      !y1.isFinite ||
      x0 < 0 ||
      y0 < 0 ||
      x1 > 1 ||
      y1 > 1 ||
      x0 >= x1 ||
      y0 >= y1) {
    return (region: null, error: '座標は0〜1の範囲で、右下が左上より大きくなるように入力してください');
  }
  final label = labelText.trim();
  if (label.isEmpty) {
    return (region: null, error: '設問番号を入力してください');
  }
  final text = contentText.trim();
  return (
    region: original.rebuild(
      (b) => b
        ..kind = kind
        ..label = label
        ..pageIndex = page - 1
        ..text = text.isEmpty ? null : text
        ..bbox.x0 = x0
        ..bbox.y0 = y0
        ..bbox.x1 = x1
        ..bbox.y1 = y1,
    ),
    error: null,
  );
}
