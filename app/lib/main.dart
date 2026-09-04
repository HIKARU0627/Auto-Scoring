import 'package:flutter/material.dart';

import 'package:auto_scoring_app/core/app_dependencies.dart';
import 'package:auto_scoring_app/core/app_theme.dart';
import 'package:auto_scoring_app/features/home/home_page.dart';

void main() {
  runApp(const AutoScoringApp());
}

/// Application root. This is the composition root, so it is allowed to wire
/// `core` and `features` together.
class AutoScoringApp extends StatelessWidget {
  const AutoScoringApp({
    super.key,
    this.dependencies = const AppDependencies(),
  });

  final AppDependencies dependencies;

  @override
  Widget build(BuildContext context) {
    return MaterialApp(
      title: 'Auto-Scoring',
      theme: AppTheme.light(),
      darkTheme: AppTheme.dark(),
      home: HomePage(dependencies: dependencies),
    );
  }
}
