import 'package:flutter/material.dart';

import 'package:auto_scoring_app/core/design/app_color_schemes.dart';
import 'package:auto_scoring_app/core/design/app_typography.dart';
import 'package:auto_scoring_app/core/design/design_tokens.dart';

/// Material 3 theme for the Auto-Scoring desktop app.
///
/// The composition of the design tokens (Issue #67): the colour ramps from
/// `design/app_color_schemes.dart`, the type scale from
/// `design/app_typography.dart` and the dimensions from
/// `design/design_tokens.dart` are wired into the widgets that actually use
/// them here. Screens then read `Theme.of(context)` and the two extensions
/// rather than styling themselves -- see `design/app_theme_context.dart` for
/// the shorthand, and `docs/design-tokens.md` for the reasoning.
///
/// One rule shapes most of what follows: **separate surfaces by colour, not by
/// shadow**. Every resting component sits at elevation 0 on a step of the
/// neutral ramp. A grading screen stacks a lot of panels, and a page of soft
/// shadows is both noisier and (in dark) muddier than a page of flat planes.
///
/// `core` may depend on `api` but never on `features`.
class AppTheme {
  const AppTheme._();

  static ThemeData light() => _build(Brightness.light);

  static ThemeData dark() => _build(Brightness.dark);

  static ThemeData _build(Brightness brightness) {
    final colorScheme = appColorScheme(brightness);
    final textTheme = appTextTheme(colorScheme);
    return ThemeData(
      useMaterial3: true,
      colorScheme: colorScheme,
      textTheme: textTheme,
      scaffoldBackgroundColor: colorScheme.surface,
      extensions: [
        brightness == Brightness.light
            ? AppStatusColors.light
            : AppStatusColors.dark,
        AppTextRoles.from(textTheme),
      ],

      appBarTheme: AppBarThemeData(
        backgroundColor: colorScheme.surfaceContainer,
        foregroundColor: colorScheme.onSurface,
        elevation: AppElevation.flat,
        // Material would otherwise raise the app bar's tint as content scrolls
        // under it. The ramp already separates it from the page, and a colour
        // that changes while the reviewer scrolls is exactly the kind of
        // unasked-for movement this app avoids.
        scrolledUnderElevation: AppElevation.flat,
        centerTitle: false,
        titleTextStyle: textTheme.titleLarge,
      ),

      cardTheme: CardThemeData(
        color: colorScheme.surfaceContainerLow,
        elevation: AppElevation.flat,
        // A hairline instead of a shadow: on a settings screen of stacked
        // cards the outline is what actually says where one section ends.
        shape: RoundedRectangleBorder(
          borderRadius: AppRadius.mdAll,
          side: BorderSide(color: colorScheme.outlineVariant),
        ),
        margin: EdgeInsets.zero,
        clipBehavior: Clip.antiAlias,
      ),

      dialogTheme: DialogThemeData(
        backgroundColor: colorScheme.surfaceContainerHigh,
        elevation: AppElevation.modal,
        shape: const RoundedRectangleBorder(borderRadius: AppRadius.lgAll),
        titleTextStyle: textTheme.titleLarge,
        contentTextStyle: textTheme.bodyMedium,
      ),

      // Every button gets the same height and radius so a row of them reads as
      // one control strip -- the 添削レビュー action bar mixes filled and
      // outlined buttons and they must line up exactly.
      filledButtonTheme: FilledButtonThemeData(
        style: _buttonStyle(textTheme, colorScheme),
      ),
      outlinedButtonTheme: OutlinedButtonThemeData(
        style: _buttonStyle(textTheme, colorScheme),
      ),
      textButtonTheme: TextButtonThemeData(
        style: _buttonStyle(textTheme, colorScheme),
      ),

      inputDecorationTheme: InputDecorationThemeData(
        filled: true,
        fillColor: colorScheme.surfaceContainerLowest,
        border: const OutlineInputBorder(borderRadius: AppRadius.mdAll),
        enabledBorder: OutlineInputBorder(
          borderRadius: AppRadius.mdAll,
          borderSide: BorderSide(color: colorScheme.outlineVariant),
        ),
        focusedBorder: OutlineInputBorder(
          borderRadius: AppRadius.mdAll,
          borderSide: BorderSide(color: colorScheme.primary, width: 2),
        ),
        contentPadding: const EdgeInsets.symmetric(
          horizontal: AppSpacing.md,
          vertical: AppSpacing.md,
        ),
        labelStyle: textTheme.bodyMedium,
        // Not `bodySmall` in a lighter colour only: a validation message must
        // stay legible for someone who cannot separate it from the label by
        // colour (Issue #25).
        helperStyle: textTheme.bodySmall,
        errorStyle: textTheme.bodySmall?.copyWith(color: colorScheme.error),
      ),

      navigationRailTheme: NavigationRailThemeData(
        backgroundColor: colorScheme.surfaceContainer,
        elevation: AppElevation.flat,
        // The 添削レビュー rail is the reviewer's map of the whole submission,
        // so the selected question is marked by a filled indicator *and* a
        // weight change in its label, never by colour alone.
        indicatorColor: colorScheme.secondaryContainer,
        selectedIconTheme: IconThemeData(
          color: colorScheme.onSecondaryContainer,
          size: AppIconSize.standard,
        ),
        unselectedIconTheme: IconThemeData(
          color: colorScheme.onSurfaceVariant,
          size: AppIconSize.standard,
        ),
        selectedLabelTextStyle: textTheme.labelMedium?.copyWith(
          color: colorScheme.onSurface,
          fontWeight: FontWeight.w700,
        ),
        unselectedLabelTextStyle: textTheme.labelMedium?.copyWith(
          color: colorScheme.onSurfaceVariant,
        ),
      ),

      chipTheme: ChipThemeData(
        backgroundColor: colorScheme.surfaceContainerHigh,
        side: BorderSide(color: colorScheme.outlineVariant),
        labelStyle: textTheme.labelLarge,
        shape: const RoundedRectangleBorder(borderRadius: AppRadius.smAll),
        padding: const EdgeInsets.symmetric(
          horizontal: AppSpacing.sm,
          vertical: AppSpacing.xs,
        ),
      ),

      snackBarTheme: SnackBarThemeData(
        behavior: SnackBarBehavior.floating,
        backgroundColor: colorScheme.inverseSurface,
        contentTextStyle: textTheme.bodyMedium?.copyWith(
          color: colorScheme.onInverseSurface,
        ),
        shape: const RoundedRectangleBorder(borderRadius: AppRadius.mdAll),
        elevation: AppElevation.raised,
      ),

      listTileTheme: ListTileThemeData(
        iconColor: colorScheme.onSurfaceVariant,
        titleTextStyle: textTheme.bodyMedium,
        subtitleTextStyle: textTheme.bodySmall?.copyWith(
          color: colorScheme.onSurfaceVariant,
        ),
        shape: const RoundedRectangleBorder(borderRadius: AppRadius.smAll),
      ),

      dividerTheme: DividerThemeData(
        color: colorScheme.outlineVariant,
        thickness: AppLayout.hairline,
        space: AppLayout.sectionDivider,
      ),

      iconTheme: IconThemeData(
        color: colorScheme.onSurfaceVariant,
        size: AppIconSize.standard,
      ),

      tooltipTheme: TooltipThemeData(
        // Long enough that a pointer crossing the action bar on its way
        // somewhere else does not leave a trail of popping tooltips.
        waitDuration: AppMotion.emphasis,
        decoration: BoxDecoration(
          color: colorScheme.inverseSurface,
          borderRadius: AppRadius.smAll,
        ),
        textStyle: textTheme.bodySmall?.copyWith(
          color: colorScheme.onInverseSurface,
        ),
      ),

      progressIndicatorTheme: ProgressIndicatorThemeData(
        color: colorScheme.primary,
        linearTrackColor: colorScheme.surfaceContainerHighest,
        circularTrackColor: colorScheme.surfaceContainerHighest,
      ),
    );
  }

  /// Shared by filled/outlined/text buttons so they are interchangeable in a
  /// row without any of them changing the row's height.
  ///
  /// 無効のときの3色も一緒に当てる (Issue #88)。**上書きするのは無効のときだけ**
  /// で、有効・ホバー・フォーカス・押下は `null` を返して Material の既定へ
  /// 落とす -- `ButtonStyleButton` は解決した*値*について
  /// `widget ?? theme ?? default` を取るので、ここが状態ごとに `null` を返せば
  /// その状態だけ既定が使われる。3種類のボタンの既定を書き写さずに、無効だけを
  /// 差し替えられるのはそのためである。
  static ButtonStyle _buttonStyle(TextTheme textTheme, ColorScheme colors) {
    WidgetStateProperty<T?> whenDisabled<T>(T value) =>
        WidgetStateProperty.resolveWith(
          (states) => states.contains(WidgetState.disabled) ? value : null,
        );

    return ButtonStyle(
      textStyle: WidgetStatePropertyAll(textTheme.labelLarge),
      padding: const WidgetStatePropertyAll(
        EdgeInsets.symmetric(
          horizontal: AppSpacing.lg,
          vertical: AppSpacing.md,
        ),
      ),
      shape: const WidgetStatePropertyAll(
        RoundedRectangleBorder(borderRadius: AppRadius.mdAll),
      ),
      backgroundColor: whenDisabled(colors.disabledButtonContainer),
      foregroundColor: whenDisabled(colors.disabledButtonLabel),
      iconColor: whenDisabled(colors.disabledButtonLabel),
      // `TextButton` にも枠が付く。有効なときの見た目より目立つのは承知の上で、
      // 枠の無い無効なテキストボタンは文章と見分けが付かない -- 「押せない
      // ボタンとして判別できる」(受入条件2) を満たすのはこの線である。
      side: whenDisabled(BorderSide(color: colors.disabledButtonOutline)),
    );
  }
}
