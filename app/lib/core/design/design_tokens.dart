/// Dimension, elevation and motion tokens (Issue #67).
///
/// Every spacing, corner radius, icon size and animation duration a screen
/// uses comes from here, so that changing the feel of the app is a change to
/// this file rather than a sweep through `features/`. Colour and type live
/// next door in `app_color_schemes.dart` / `app_typography.dart`; all three
/// are assembled into `ThemeData` by `core/app_theme.dart`.
///
/// The rationale for the values themselves is in `docs/design-tokens.md`.
library;

import 'package:flutter/material.dart';

/// The 4px spacing scale. Nothing in `features/` should write a raw pixel gap.
///
/// The steps are deliberately few: a grading session shows one dense working
/// surface, and six choices are enough to keep related things grouped and
/// unrelated things apart without every screen inventing its own rhythm.
abstract final class AppSpacing {
  /// 4 -- inside a single line of content (icon to its label).
  static const double xs = 4;

  /// 8 -- between tightly related items (a label and the value under it).
  static const double sm = 8;

  /// 12 -- between controls in a row, and inside a compact banner.
  static const double md = 12;

  /// 16 -- between fields in a form, and inside a card.
  static const double lg = 16;

  /// 24 -- between sections of a screen, and around a page's content.
  static const double xl = 24;

  /// 32 -- above/below a lone centred element (the startup splash).
  static const double xxl = 32;

  /// Around the content of a full screen.
  static const EdgeInsets page = EdgeInsets.all(xl);

  /// Inside a `Card` that holds a section of a screen.
  static const EdgeInsets card = EdgeInsets.all(lg);

  /// Inside a compact `Card` that holds one line (status/error banners).
  static const EdgeInsets banner = EdgeInsets.all(md);

  /// A scrolling panel that holds a column of sections (添削レビューの
  /// Inspector, テスト設定画面のリスト).
  ///
  /// The same value as [card] today, and named separately on purpose: a panel
  /// is the container, a card is one section inside it, and the day they need
  /// to differ should be one edit here rather than a hunt for which `lg` meant
  /// which.
  static const EdgeInsets panel = EdgeInsets.all(lg);

  /// The 添削レビュー action bar: wider than tall, so the buttons sit in a
  /// band rather than a box.
  static const EdgeInsets actionBar = EdgeInsets.symmetric(
    horizontal: lg,
    vertical: md,
  );
}

/// Corner radii. Deliberately modest: this is a dense information tool, and
/// large radii cost horizontal space in every nested container.
abstract final class AppRadius {
  /// 4 -- chips, small inline surfaces.
  static const double sm = 4;

  /// 8 -- cards, buttons, text fields. The default.
  static const double md = 8;

  /// 12 -- dialogs, the one place a rounder shape reads as "on top".
  static const double lg = 12;

  static const BorderRadius smAll = BorderRadius.all(Radius.circular(sm));
  static const BorderRadius mdAll = BorderRadius.all(Radius.circular(md));
  static const BorderRadius lgAll = BorderRadius.all(Radius.circular(lg));
}

/// Elevation steps. Only three, because a flat, low-glare surface is the
/// point -- shadows are for things that genuinely float over the work.
abstract final class AppElevation {
  /// Cards and the app bar: separated by colour (`surfaceContainer`), not by
  /// a shadow.
  static const double flat = 0;

  /// Genuinely floating over the content: the 添削レビュー action bar, which
  /// scrolling content passes under.
  static const double raised = 3;

  /// Modal surfaces (dialogs, menus).
  static const double modal = 6;
}

/// Icon sizes. Material's own default is 24; the smaller steps are for icons
/// that sit inline with text and must not out-weigh it.
abstract final class AppIconSize {
  /// 16 -- inline with `labelLarge`/`bodyMedium` text.
  static const double inline = 16;

  /// 18 -- a chip avatar, or a badge leading its own line of text.
  static const double dense = 18;

  /// 24 -- Material's default; buttons and list tiles.
  static const double standard = 24;

  /// 40 -- an empty/error state inside a panel.
  static const double display = 40;

  /// 48 -- a full-screen error state.
  static const double hero = 48;
}

/// Fixed layout dimensions that are neither spacing nor type.
///
/// These are widths a design decision fixes, not numbers a screen invents:
/// the reading measure of a form, the width of the Inspector, and the point
/// at which 添削レビュー stops putting the Inspector beside the PDF.
abstract final class AppLayout {
  /// Below this width 添削レビュー stacks the Inspector under the PDF viewer
  /// instead of beside it (Issue #21 acceptance: desktopの標準/狭幅表示).
  static const double narrowBreakpoint = 900;

  /// The 添削レビュー Inspector, when it sits beside the PDF.
  ///
  /// Widened from 360 (Issue #85). The panel holds the whole of what 承認 is a
  /// decision about -- 認識文字・点数・根拠・コメント・基準ごとの判定 -- and
  /// every line those wrap onto is a line further down that the reviewer has
  /// to scroll to reach. The viewer beside it loses width it was not using: a
  /// single question's answer region does not need 800px.
  static const double inspectorWidth = 440;

  /// A form's reading measure. Wider than this and the eye loses the start of
  /// the next line on a maximised desktop window.
  static const double formMaxWidth = 640;

  /// A centred message (the sidecar error screen). Narrower than a form: it is
  /// prose, not fields.
  static const double messageMaxWidth = 480;

  /// ホーム画面の内容幅. Wider than a form because its cards carry a progress
  /// bar and a row of state counts side by side, and narrower than the window
  /// because a maximised desktop would otherwise stretch one card across the
  /// whole screen and leave the eye travelling from a test's name to its
  /// buttons (Issue #68).
  static const double dashboardMaxWidth = 800;

  /// An `AlertDialog`'s content, so a progress row and a path both get the
  /// same dialog width instead of one sized to its text.
  static const double dialogContentWidth = 360;

  /// A `Divider`/`VerticalDivider` that separates two panes: the widget's
  /// `width`/`height` is its *total* extent including padding, so 1 means a
  /// hairline with nothing around it.
  static const double hairline = 1;

  /// One node in the 設問依存DAG panel (Issue #64). Wide enough for
  /// 設問番号 plus the longest state label (`AI処理中`, `問12 待ち`) on two
  /// lines at `labelLarge`/`labelSmall`, and no wider: the diagram's whole
  /// value is seeing several layers at once.
  static const double dagNodeWidth = 116;
  static const double dagNodeHeight = 64;

  /// The 設問依存DAG panel's height when expanded, as **exactly three node
  /// rows** plus the diagram's own padding and gaps (`DagMetrics`' defaults:
  /// [AppSpacing.lg] around, [AppSpacing.md] between). Written as that sum
  /// rather than as 248 so it stays a whole number of rows if the node size
  /// changes -- a band that ends mid-node reads as broken rather than as
  /// scrollable.
  ///
  /// Three rows because that is a plausible number of questions to be
  /// running in parallel; beyond it the diagram scrolls, and the panel never
  /// costs the PDF viewer more than this fixed band.
  static const double dagPanelHeight =
      AppSpacing.lg * 2 + dagNodeHeight * 3 + AppSpacing.md * 2;

  /// The share of the pane it shares with the PDF viewer that the 進捗パネル
  /// may actually take (Issue #85).
  ///
  /// [dagPanelHeight] on its own is a band of a *fixed* size, and a fixed
  /// band is only affordable on a tall window: at 1280x720 it cost 45% of the
  /// screen, and what it pushed below the fold was 根拠・コメント・基準ごとの
  /// 判定 -- the things 承認 is a decision *about* -- while 承認して次へ stayed
  /// visible the whole time. Progress is context; the decision material is the
  /// work. So the band gets a share of the height there is rather than a
  /// constant, and it is the part that yields when the window is short.
  static const double dagPanelMaxHeightFraction = 0.3;

  /// How many times its own width a gap between two DAG layers may grow to
  /// when the diagram is handed more width than it needs (Issue #85).
  ///
  /// A three-layer graph is about 480px wide, so in a full-width band it sat
  /// in the left three fifths with nothing to its right. Spending the slack on
  /// the gaps between layers is spending it on the one thing the diagram
  /// exists to show -- 上流が完了して下流が動き出す, which is drawn *in* those
  /// gaps. Capped, because past this an arrow stops reading as a connection
  /// and starts reading as two unrelated groups; the panel centres whatever
  /// width is still left over. A multiple rather than a pixel ceiling, so it
  /// still means the same thing if the gap itself is ever retuned.
  static const double dagColumnGapSpreadLimit = 3;

  /// The hairline that says a node is actively running. Two pixels, because
  /// it is the only thing on this screen allowed to move continuously and it
  /// should be findable without being loud (`docs/design-tokens.md` §5).
  static const double activityBarHeight = 2;

  /// A `Divider` used as a section break inside a scrolling column. Unlike
  /// [hairline] this is the rule *plus* the space it reserves above and below
  /// it, which is why it is a spacing step rather than 1.
  static const double sectionDivider = AppSpacing.xl;

  /// The 修正コメント band pinned under the 添削レビュー Inspector's scrolling
  /// 判断材料: the field itself plus the rule and padding around it.
  ///
  /// It is a fixed-height child, so the Inspector's share of a stacked narrow
  /// layout has to be at least this or the column overflows by the
  /// difference. 40% of a short pane is not: Issue #80 put a 「AI採点を開始」
  /// notice above that pane, and 40% of what was left came to less than this
  /// band (Issue #85).
  static const double reviewNoteBandHeight = 88;
}

/// Motion tokens.
///
/// Grading is a long, screen-staring task, so the rule this app follows is:
/// **nothing moves on its own**. Motion exists to say that a state just
/// changed -- "the job finished", "this needs a human" -- and then stops.
/// There is no idle animation, no looping emphasis, and no transition long
/// enough to wait on.
///
/// Issue #67 defines these and applies them in one place (`AppErrorBanner`);
/// per-screen application is deliberately left to later issues so that the
/// vocabulary is settled first.
///
/// The 設問依存DAG panel (Issue #64) is the first of those, and holds the one
/// documented exception to "nothing moves on its own": a node whose job is
/// `RUNNING` carries a continuously-moving hairline
/// ([AppLayout.activityBarHeight]), because "this one is working right now"
/// is not a state change that can be announced once and then stopped. It is
/// bounded on purpose -- only the running nodes, only a low-contrast 2px bar,
/// and it disappears the moment the job leaves `RUNNING`. See
/// `docs/design-tokens.md` §5.
abstract final class AppMotion {
  /// 150ms -- a control changing state under the pointer/keyboard. Short
  /// enough to feel like a response rather than an animation.
  static const Duration stateChange = Duration(milliseconds: 150);

  /// 250ms -- something appearing that the reviewer did not ask for and must
  /// notice: an error, a 要確認 banner. The upper bound; nothing is slower.
  static const Duration emphasis = Duration(milliseconds: 250);

  /// The default curve for a state change: fast out, settles gently.
  static const Curve standard = Easing.standard;

  /// For something entering the screen -- it decelerates into place, which
  /// reads as "arrived" rather than "flew past".
  static const Curve enter = Easing.emphasizedDecelerate;
}
