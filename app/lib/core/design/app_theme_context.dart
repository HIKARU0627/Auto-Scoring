import 'package:flutter/material.dart';

import 'package:auto_scoring_app/core/design/app_color_schemes.dart';
import 'package:auto_scoring_app/core/design/app_typography.dart';

/// Shorthand for the design tokens a screen reaches for constantly.
///
/// `Theme.of(context).extension<AppStatusColors>()!` at every call site is
/// noise that hides which token was actually chosen; `context.statusColors`
/// leaves the choice visible. The `!` is safe by construction: `AppTheme`
/// installs both extensions in `light()` and `dark()`, which are the only
/// themes the app and `test/app_harness.dart` ever run under, and
/// `test/app_theme_contrast_test.dart` asserts it stays that way.
extension AppThemeContext on BuildContext {
  ColorScheme get colors => Theme.of(this).colorScheme;

  TextTheme get texts => Theme.of(this).textTheme;

  /// 要確認・成功・添削記号の色。See [AppStatusColors].
  AppStatusColors get statusColors =>
      Theme.of(this).extension<AppStatusColors>()!;

  /// 設問文・認識文字・採点コメント・点数のスタイル。See [AppTextRoles].
  AppTextRoles get textRoles => Theme.of(this).extension<AppTextRoles>()!;
}
