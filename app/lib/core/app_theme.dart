import 'package:flutter/material.dart';

/// Material 3 theme for the Auto-Scoring desktop app.
///
/// `core` may depend on `api` but never on `features`.
class AppTheme {
  const AppTheme._();

  static const Color _seed = Color(0xFF1565C0);

  static ThemeData light() => ThemeData(
    colorScheme: ColorScheme.fromSeed(seedColor: _seed),
    useMaterial3: true,
  );

  static ThemeData dark() => ThemeData(
    colorScheme: ColorScheme.fromSeed(
      seedColor: _seed,
      brightness: Brightness.dark,
    ),
    useMaterial3: true,
  );
}
