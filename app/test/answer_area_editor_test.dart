import 'package:auto_scoring_app/api/sidecar_api_client.dart';
import 'package:auto_scoring_app/core/app_theme.dart';
import 'package:auto_scoring_app/features/test_registration/answer_area_editor.dart';
import 'package:flutter/gestures.dart';
import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';

/// The 回答欄 overlay editor (Issue #105).
///
/// Every fixture is synthetic. The real answer sheets this was measured
/// against are a cram school's copyrighted material and none of it -- pages,
/// crops, question numbers, subject names -- appears in this repository.
///
/// [AnswerAreaEditor.pdfBytes] is left `null` throughout: the widget then
/// draws each page as an outline at the right shape, which is both what a
/// reviewer sees before uploading a sheet and what lets these tests run
/// without PDFium rendering a real document.
RegionModel _region({
  required String regionId,
  String label = '問1',
  RegionKind kind = RegionKind.answerArea,
  int pageIndex = 0,
  double x0 = 0.1,
  double y0 = 0.1,
  double x1 = 0.5,
  double y1 = 0.3,
  String? text,
}) {
  return RegionModel(
    (b) => b
      ..regionId = regionId
      ..kind = kind
      ..pageIndex = pageIndex
      ..label = label
      ..confirmed = false
      ..text = text
      ..bbox.x0 = x0
      ..bbox.y0 = y0
      ..bbox.x1 = x1
      ..bbox.y1 = y1,
  );
}

PageFormatModel _page() => PageFormatModel(
  (b) => b
    ..widthPt = 595
    ..heightPt = 842,
);

/// Pumps the editor and returns the last region list it emitted.
Future<List<RegionModel> Function()> _pumpEditor(
  WidgetTester tester, {
  required List<RegionModel> regions,
  List<String> questionNumbers = const ['問1', '問2'],
  List<String> undetected = const [],
  List<String> absent = const [],
  List<List<String>> conflicts = const [],
  int pages = 1,
  bool readOnly = false,
  void Function(int index)? onEditNumerically,
}) async {
  tester.view.physicalSize = const Size(1400, 2400);
  tester.view.devicePixelRatio = 1.0;
  addTearDown(tester.view.resetPhysicalSize);
  addTearDown(tester.view.resetDevicePixelRatio);

  var current = regions;
  await tester.pumpWidget(
    MaterialApp(
      theme: AppTheme.light(),
      home: StatefulBuilder(
        builder: (context, setState) => Scaffold(
          body: SingleChildScrollView(
            child: AnswerAreaEditor(
              pages: [for (var i = 0; i < pages; i++) _page()],
              regions: current,
              questionNumbers: questionNumbers,
              undetectedQuestionNumbers: undetected,
              absentQuestionNumbers: absent,
              readingOrderConflicts: conflicts,
              readOnly: readOnly,
              onEditNumerically: onEditNumerically,
              onRegionsChanged: (next) => setState(() => current = next),
            ),
          ),
        ),
      ),
    ),
  );
  await tester.pumpAndSettle();
  return () => current;
}

/// A pointer press, a stream of small moves, and a release -- a real drag.
///
/// Not `WidgetTester.drag`: with its default slop the first 20 logical pixels
/// of travel are consumed before any delta is reported, and with the slop
/// disabled it sends the whole journey as one move event, which no real
/// pointer does. Both make an assertion about *where* a box ended up a
/// statement about the harness rather than about this widget.
///
/// Many small steps rather than a few large ones for the same reason: a drag
/// recognizer spends its first move event deciding the gesture is a drag, so
/// coarse steps lose a coarse amount of travel. A real mouse emits moves a
/// pixel or two apart, where that loss is invisible.
Future<void> _dragBy(
  WidgetTester tester,
  Offset globalStart,
  Offset offset, {
  int steps = 24,
}) async {
  final gesture = await tester.startGesture(
    globalStart,
    kind: PointerDeviceKind.mouse,
  );
  await tester.pump();
  for (var i = 0; i < steps; i++) {
    await gesture.moveBy(offset / steps.toDouble());
    await tester.pump();
  }
  await gesture.up();
  await tester.pumpAndSettle();
}

void main() {
  _missingQuestionGroups();
  _readingOrderWarning();
  group('showing what was and was not found', () {
    testWidgets('lists every question the detection did not find', (
      tester,
    ) async {
      await _pumpEditor(
        tester,
        regions: [_region(regionId: 'a0')],
        undetected: const ['問2', '問3'],
      );

      expect(find.byKey(const Key('answer-area-undetected')), findsOneWidget);
      expect(
        find.byKey(const Key('answer-area-undetected-問2')),
        findsOneWidget,
      );
      expect(
        find.byKey(const Key('answer-area-undetected-問3')),
        findsOneWidget,
      );
    });

    testWidgets('says an undetected question can still be confirmed', (
      tester,
    ) async {
      // Issue #105 deliberately does not block on this (unlike Issue #103's
      // unknown 配点): the question grades against the whole page and lands
      // on the review screen. The screen has to say that, or a reviewer
      // reads the warning as "you are stuck".
      await _pumpEditor(
        tester,
        regions: [_region(regionId: 'a0')],
        undetected: const ['問2'],
      );
      expect(find.textContaining('このまま確定もできますが'), findsOneWidget);
    });

    testWidgets('says so when every question has an area', (tester) async {
      await _pumpEditor(
        tester,
        regions: [
          _region(regionId: 'a0'),
          _region(regionId: 'a1', label: '問2'),
        ],
      );
      expect(find.byKey(const Key('answer-area-all-detected')), findsOneWidget);
    });

    testWidgets('says why nothing can be assigned before 配点 is confirmed', (
      tester,
    ) async {
      await _pumpEditor(tester, regions: const [], questionNumbers: const []);
      expect(find.byKey(const Key('answer-area-no-questions')), findsOneWidget);
    });

    testWidgets('shows the note a merged or unattributed box carries', (
      tester,
    ) async {
      await _pumpEditor(
        tester,
        regions: [_region(regionId: 'a0', text: '検出された枠 3 個を 1 つにまとめました。')],
      );
      expect(find.textContaining('3 個を 1 つにまとめました'), findsOneWidget);
    });

    testWidgets('claims nothing about how accurate the detection was', (
      tester,
    ) async {
      // The same discipline Issues #101 and #103 fixed for their own screens:
      // this app has never measured detection accuracy (the real material has
      // one answer per subject, so there is no second answer of the same test
      // to measure reuse against), so no screen may imply it.
      await _pumpEditor(
        tester,
        regions: [_region(regionId: 'a0')],
        undetected: const ['問2'],
      );
      for (final claim in ['精度', '正確', '自動で完了', 'すべて検出']) {
        expect(find.textContaining(claim), findsNothing, reason: claim);
      }
    });
  });

  group('a box with no question', () {
    testWidgets('is labelled as unassigned rather than shown as a question', (
      tester,
    ) async {
      await _pumpEditor(
        tester,
        regions: [_region(regionId: 'a0', label: unassignedQuestionLabel)],
      );
      expect(find.text(unassignedQuestionDisplayLabel), findsWidgets);
      // Never the raw sentinel: it is an internal value, not something a
      // reviewer should have to recognize.
      expect(find.text(unassignedQuestionLabel), findsNothing);
    });

    testWidgets('is listed before the boxes that are already assigned', (
      tester,
    ) async {
      // It is the only thing here that stops the profile being confirmed, so
      // it must not be somewhere down a long list.
      await _pumpEditor(
        tester,
        regions: [
          _region(regionId: 'a0'),
          _region(regionId: 'a1', label: unassignedQuestionLabel),
        ],
      );
      final rows = tester.widgetList<Card>(find.byType(Card)).toList();
      expect((rows.first.key as ValueKey<String>).value, 'answer-area-row-1');
    });

    testWidgets('a label matching no current question reads as unassigned', (
      tester,
    ) async {
      // A test whose 配点 was re-confirmed with different numbers leaves
      // regions pointing at questions that no longer exist. Showing the stale
      // label would say the box is attached to something; it is not.
      await _pumpEditor(
        tester,
        regions: [_region(regionId: 'a0', label: '問9')],
      );
      final dropdown = tester.widget<DropdownButton<String>>(
        find.byKey(const Key('answer-area-question-0')),
      );
      expect(dropdown.value, unassignedQuestionLabel);
    });
  });

  group('editing', () {
    testWidgets('assigning a question is a choice, not a text field', (
      tester,
    ) async {
      // Issue #105 acceptance 3: the candidates are the confirmed question
      // set, so a reviewer cannot invent a number that matches no allocation.
      final regions = await _pumpEditor(
        tester,
        regions: [_region(regionId: 'a0', label: unassignedQuestionLabel)],
      );

      await tester.tap(find.byKey(const Key('answer-area-question-0')));
      await tester.pumpAndSettle();
      await tester.tap(find.text('問2').last);
      await tester.pumpAndSettle();

      expect(regions().single.label, '問2');
      expect(find.byType(TextField), findsNothing);
    });

    testWidgets('the dropdown offers exactly the confirmed questions', (
      tester,
    ) async {
      await _pumpEditor(
        tester,
        regions: [_region(regionId: 'a0')],
        questionNumbers: const ['問1', '問2', '問3'],
      );
      final dropdown = tester.widget<DropdownButton<String>>(
        find.byKey(const Key('answer-area-question-0')),
      );
      expect(dropdown.items!.map((item) => item.value).toList(), [
        '問1',
        '問2',
        '問3',
        unassignedQuestionLabel,
      ]);
    });

    testWidgets('deleting removes the box', (tester) async {
      final regions = await _pumpEditor(
        tester,
        regions: [
          _region(regionId: 'a0'),
          _region(regionId: 'a1', label: '問2'),
        ],
      );

      await tester.tap(find.byKey(const Key('answer-area-delete-0')));
      await tester.pumpAndSettle();

      expect(regions().map((r) => r.regionId).toList(), ['a1']);
    });

    testWidgets('dragging on an empty page draws a new answer area', (
      tester,
    ) async {
      // Issue #105 acceptance 2 and 6: a box a reviewer draws by hand and a
      // box the AI proposed are the same thing, made the same way, on the
      // same screen.
      final regions = await _pumpEditor(
        tester,
        regions: const [],
        undetected: const ['問1', '問2'],
      );

      final surface = find.byKey(const Key('answer-area-draw-surface-0'));
      final topLeft = tester.getTopLeft(surface);
      final size = tester.getSize(surface);
      await _dragBy(
        tester,
        topLeft + Offset(size.width * 0.2, size.height * 0.2),
        Offset(size.width * 0.4, size.height * 0.3),
      );
      await tester.pumpAndSettle();

      expect(regions(), hasLength(1));
      final drawn = regions().single;
      expect(drawn.kind, RegionKind.answerArea);
      expect(drawn.bbox.x0, closeTo(0.2, 0.02));
      expect(drawn.bbox.y1, closeTo(0.5, 0.02));
    });

    testWidgets('a drawn box goes to the first question still missing one', (
      tester,
    ) async {
      // The common action is "問2 was missed, draw it", and making that one
      // drag with nothing else to set is the whole point of the default.
      final regions = await _pumpEditor(
        tester,
        regions: [_region(regionId: 'a0')],
        undetected: const ['問2'],
      );

      final surface = find.byKey(const Key('answer-area-draw-surface-0'));
      final topLeft = tester.getTopLeft(surface);
      final size = tester.getSize(surface);
      await _dragBy(
        tester,
        topLeft + Offset(size.width * 0.5, size.height * 0.6),
        Offset(size.width * 0.2, size.height * 0.1),
      );
      await tester.pumpAndSettle();

      expect(regions().last.label, '問2');
    });

    testWidgets('a drawn box is unassigned when nothing is missing one', (
      tester,
    ) async {
      // Better an explicit "someone must say which" than silently attaching
      // the box to a question that already has one.
      final regions = await _pumpEditor(
        tester,
        regions: [
          _region(regionId: 'a0'),
          _region(regionId: 'a1', label: '問2'),
        ],
      );

      final surface = find.byKey(const Key('answer-area-draw-surface-0'));
      final topLeft = tester.getTopLeft(surface);
      final size = tester.getSize(surface);
      await _dragBy(
        tester,
        topLeft + Offset(size.width * 0.6, size.height * 0.6),
        Offset(size.width * 0.2, size.height * 0.1),
      );
      await tester.pumpAndSettle();

      expect(regions().last.label, unassignedQuestionLabel);
    });

    testWidgets('a tap is not a box', (tester) async {
      final regions = await _pumpEditor(tester, regions: const []);
      await tester.tap(find.byKey(const Key('answer-area-draw-surface-0')));
      await tester.pumpAndSettle();
      expect(regions(), isEmpty);
    });

    testWidgets('a drawn box never collides with a detected one\'s id', (
      tester,
    ) async {
      // Two regions sharing an id would make the selection and the numeric
      // dialog address the wrong box -- and the sidecar rejects the profile
      // outright.
      final regions = await _pumpEditor(
        tester,
        regions: [_region(regionId: 'answer-area-0')],
      );

      final surface = find.byKey(const Key('answer-area-draw-surface-0'));
      final topLeft = tester.getTopLeft(surface);
      final size = tester.getSize(surface);
      await _dragBy(
        tester,
        topLeft + Offset(size.width * 0.6, size.height * 0.6),
        Offset(size.width * 0.2, size.height * 0.1),
      );
      await tester.pumpAndSettle();

      final ids = regions().map((r) => r.regionId).toList();
      expect(ids.toSet(), hasLength(ids.length));
    });

    testWidgets('dragging a selected box moves it', (tester) async {
      final regions = await _pumpEditor(
        tester,
        regions: [_region(regionId: 'a0')],
      );

      final box = find.byKey(const Key('answer-area-box-0'));
      await tester.tap(box);
      await tester.pumpAndSettle();
      final surfaceSize = tester.getSize(
        find.byKey(const Key('answer-area-draw-surface-0')),
      );
      await _dragBy(
        tester,
        tester.getCenter(box),
        Offset(surfaceSize.width * 0.1, 0),
      );
      await tester.pumpAndSettle();

      expect(regions().single.bbox.x0, closeTo(0.2, 0.02));
      // Moving keeps the size; only the resize handle changes it.
      expect(
        regions().single.bbox.x1 - regions().single.bbox.x0,
        closeTo(0.4, 0.02),
      );
    });

    testWidgets('a box cannot be dragged off the page', (tester) async {
      final regions = await _pumpEditor(
        tester,
        regions: [_region(regionId: 'a0')],
      );
      final box = find.byKey(const Key('answer-area-box-0'));
      await tester.tap(box);
      await tester.pumpAndSettle();
      final surfaceSize = tester.getSize(
        find.byKey(const Key('answer-area-draw-surface-0')),
      );
      await _dragBy(
        tester,
        tester.getCenter(box),
        Offset(-surfaceSize.width, 0),
      );
      await tester.pumpAndSettle();

      expect(regions().single.bbox.x0, greaterThanOrEqualTo(0.0));
      expect(regions().single.bbox.x1, lessThanOrEqualTo(1.0));
    });

    testWidgets('the resize handle changes the size, not the position', (
      tester,
    ) async {
      final regions = await _pumpEditor(
        tester,
        regions: [_region(regionId: 'a0')],
      );
      await tester.tap(find.byKey(const Key('answer-area-box-0')));
      await tester.pumpAndSettle();

      final surfaceSize = tester.getSize(
        find.byKey(const Key('answer-area-draw-surface-0')),
      );
      await _dragBy(
        tester,
        tester.getCenter(find.byKey(const Key('answer-area-resize-0'))),
        Offset(surfaceSize.width * 0.1, 0),
      );

      expect(regions().single.bbox.x0, closeTo(0.1, 0.02));
      expect(regions().single.bbox.x1, closeTo(0.6, 0.02));
    });

    testWidgets('a box you just drew is selected, so it can be adjusted', (
      tester,
    ) async {
      // Otherwise the reviewer draws a rectangle and has to hunt for it and
      // click it before nudging an edge -- and the drawn rectangle is almost
      // never right the first time.
      await _pumpEditor(tester, regions: const [], undetected: const ['問1']);

      final surface = find.byKey(const Key('answer-area-draw-surface-0'));
      final topLeft = tester.getTopLeft(surface);
      final size = tester.getSize(surface);
      await _dragBy(
        tester,
        topLeft + Offset(size.width * 0.2, size.height * 0.2),
        Offset(size.width * 0.4, size.height * 0.3),
      );

      // The resize handle only exists on the selected box.
      expect(find.byKey(const Key('answer-area-resize-0')), findsOneWidget);
    });

    testWidgets('deleting clears the selection instead of moving it', (
      tester,
    ) async {
      final regions = await _pumpEditor(
        tester,
        regions: [
          _region(regionId: 'a0'),
          _region(regionId: 'a1', label: '問2', y0: 0.5, y1: 0.7),
        ],
      );

      await tester.tap(find.byKey(const Key('answer-area-box-1')));
      await tester.pumpAndSettle();
      expect(find.byKey(const Key('answer-area-resize-1')), findsOneWidget);

      await tester.tap(find.byKey(const Key('answer-area-delete-0')));
      await tester.pumpAndSettle();

      expect(regions(), hasLength(1));
      // Index 0 is now the surviving box -- it must not inherit the ring.
      expect(find.byKey(const Key('answer-area-resize-0')), findsNothing);
    });

    testWidgets('every field stays reachable by typing numbers', (
      tester,
    ) async {
      // Drawing needs a pointer; positioning must not. The numeric dialog the
      // settings screen already owns is offered per row so a box can be
      // placed entirely from the keyboard.
      int? edited;
      await _pumpEditor(
        tester,
        regions: [_region(regionId: 'a0')],
        onEditNumerically: (index) => edited = index,
      );
      await tester.tap(find.byKey(const Key('answer-area-edit-0')));
      await tester.pumpAndSettle();
      expect(edited, 0);
    });
  });

  group('a confirmed profile', () {
    testWidgets('draws everything and changes nothing', (tester) async {
      final regions = await _pumpEditor(
        tester,
        regions: [_region(regionId: 'a0')],
        readOnly: true,
      );

      expect(find.byKey(const Key('answer-area-box-0')), findsOneWidget);
      expect(find.byKey(const Key('answer-area-draw-surface-0')), findsNothing);
      final delete = tester.widget<IconButton>(
        find.byKey(const Key('answer-area-delete-0')),
      );
      expect(delete.onPressed, isNull);
      final dropdown = tester.widget<DropdownButton<String>>(
        find.byKey(const Key('answer-area-question-0')),
      );
      expect(dropdown.onChanged, isNull);
      expect(regions(), hasLength(1));
    });
  });

  group('multi-page sheets', () {
    testWidgets('draws one surface per page and keeps boxes on their own', (
      tester,
    ) async {
      // Measured: a sheet is not one question per page, and a question can
      // sit on any page of it.
      await _pumpEditor(
        tester,
        regions: [
          _region(regionId: 'a0'),
          _region(regionId: 'a1', label: '問2', pageIndex: 1),
        ],
        pages: 2,
      );

      expect(
        find.byKey(const Key('answer-area-draw-surface-0')),
        findsOneWidget,
      );
      expect(
        find.byKey(const Key('answer-area-draw-surface-1')),
        findsOneWidget,
      );
      expect(find.textContaining('回答欄・1ページ'), findsOneWidget);
      expect(find.textContaining('回答欄・2ページ'), findsOneWidget);
    });
  });
}

void _missingQuestionGroups() {
  group('missing questions are split by cause (Issue #164)', () {
    testWidgets('a question with no box on the paper is listed apart from one '
        'the run failed to find', (tester) async {
      await _pumpEditor(
        tester,
        regions: const [],
        questionNumbers: const ['問1', '問2'],
        undetected: const ['問1'],
        absent: const ['問2'],
      );

      expect(find.byKey(const Key('answer-area-undetected-group')), findsOne);
      expect(find.byKey(const Key('answer-area-absent-group')), findsOne);
      expect(find.byKey(const Key('answer-area-undetected-問1')), findsOne);
      expect(find.byKey(const Key('answer-area-absent-問2')), findsOne);
    });

    testWidgets('only the group that applies is shown', (tester) async {
      await _pumpEditor(
        tester,
        regions: const [],
        questionNumbers: const ['問1', '問2'],
        absent: const ['問1', '問2'],
      );

      expect(
        find.byKey(const Key('answer-area-undetected-group')),
        findsNothing,
      );
      expect(find.byKey(const Key('answer-area-absent-group')), findsOne);
    });

    testWidgets('the all-clear needs both groups empty', (tester) async {
      // Before the split this said "every question has an answer area" while
      // the response was still naming questions that had none -- the exact
      // confusion Issue #164 was opened about, on the screen.
      await _pumpEditor(
        tester,
        regions: const [],
        questionNumbers: const ['問1'],
        absent: const ['問1'],
      );

      expect(find.byKey(const Key('answer-area-all-detected')), findsNothing);
    });

    testWidgets(
      'the absent group says what was found, not what the paper has',
      (tester) async {
        // Issue #167. Measured on the real material, the claim is right far
        // more often than not -- but one subject's smallest answer box has an
        // outline the scan breaks, so it is never a candidate and the question
        // can only be reported absent. A reviewer told that as a fact goes to
        // the 採点基準, finds nothing, and has lost the time.
        await _pumpEditor(
          tester,
          regions: const [],
          questionNumbers: const ['問1'],
          absent: const ['問1'],
        );

        final text = tester
            .widgetList<Text>(
              find.descendant(
                of: find.byKey(const Key('answer-area-absent-group')),
                matching: find.byType(Text),
              ),
            )
            .map((t) => t.data ?? '')
            .join();
        expect(text, contains('見つけられなかった'));
        expect(text, isNot(contains('判定された')));
        expect(text, isNot(contains('回答欄が無い')));
      },
    );

    testWidgets('no measured ratio is printed on the screen', (tester) async {
      // A ratio is a property of one set of teaching material at one moment.
      // On the screen it would go stale with nobody noticing; the likelihood
      // is carried by the order of the two actions instead. The numbers live
      // in docs/answer-area-detection.md with the date they were taken.
      await _pumpEditor(
        tester,
        regions: const [],
        questionNumbers: const ['問1', '問2'],
        undetected: const ['問1'],
        absent: const ['問2'],
      );

      final text = tester
          .widgetList<Text>(find.byType(Text))
          .map((t) => t.data ?? '')
          .join();
      expect(RegExp(r'\d+\s*件中').hasMatch(text), isFalse);
      expect(RegExp(r'\d+\s*%').hasMatch(text), isFalse);
      expect(text, isNot(contains('実測')));
    });

    testWidgets('the way out sits directly above the chips it applies to', (
      tester,
    ) async {
      // Softening the opening promotes "draw it yourself" from a footnote to
      // the other real possibility. Left at the end of the paragraph it is
      // read last, or not at all.
      await _pumpEditor(
        tester,
        regions: const [],
        questionNumbers: const ['問1'],
        absent: const ['問1'],
      );

      final action = find.byKey(const Key('answer-area-absent-action'));
      expect(action, findsOne);
      expect(
        tester.getTopLeft(action).dy,
        lessThan(
          tester.getTopLeft(find.byKey(const Key('answer-area-absent-問1'))).dy,
        ),
      );
      expect(tester.widget<Text>(action).data, contains('枠を引いて'));
    });

    testWidgets(
      'drawing goes to an absent question when nothing is undetected',
      (tester) async {
        // On one measured subject every question with no box is in the absent
        // group. Leaving the draw target on 「割り当てなし」 there would make the
        // way out one click longer than the screen says it is.
        await _pumpEditor(
          tester,
          regions: const [],
          questionNumbers: const ['問1', '問2'],
          absent: const ['問2'],
        );

        final dropdown = tester.widget<DropdownButton<String>>(
          find.byKey(const Key('answer-area-draw-target')),
        );
        expect(dropdown.value, '問2');
      },
    );

    testWidgets('a question reported absent can still have its box drawn', (
      tester,
    ) async {
      // The reviewer can see the page and the model is not always right.
      await _pumpEditor(
        tester,
        regions: const [],
        questionNumbers: const ['問1'],
        absent: const ['問1'],
      );

      await tester.tap(find.byKey(const Key('answer-area-absent-問1')));
      await tester.pumpAndSettle();

      final dropdown = tester.widget<DropdownButton<String>>(
        find.byKey(const Key('answer-area-draw-target')),
      );
      expect(dropdown.value, '問1');
    });
  });
}

void _readingOrderWarning() {
  group('reading order disagrees with the question numbers (Issue #171)', () {
    // Two vertical answer columns at the positions measured on a real
    // right-to-left sheet: 問一's column is the one further right.
    List<RegionModel> twoColumns() => [
      _region(
        regionId: 'r-1',
        label: '問一',
        x0: 0.639,
        y0: 0.270,
        x1: 0.703,
        y1: 0.720,
      ),
      _region(
        regionId: 'r-2',
        label: '問二',
        x0: 0.798,
        y0: 0.270,
        x1: 0.843,
        y1: 0.671,
      ),
    ];

    testWidgets('nothing is shown when the order agrees', (tester) async {
      await _pumpEditor(
        tester,
        regions: twoColumns(),
        questionNumbers: const ['問一', '問二'],
      );

      expect(find.byKey(const Key('answer-area-reading-order')), findsNothing);
    });

    testWidgets('the suspicious pair is named', (tester) async {
      // The one failure that looks like success: both questions have a box,
      // so the banner above says every question has one, while each has the
      // other's answer.
      await _pumpEditor(
        tester,
        regions: twoColumns(),
        questionNumbers: const ['問一', '問二'],
        conflicts: const [
          ['問一', '問二'],
        ],
      );

      expect(find.byKey(const Key('answer-area-reading-order')), findsOne);
      expect(find.text('問一 と 問二'), findsOne);
      expect(find.byKey(const Key('answer-area-all-detected')), findsOne);
    });

    testWidgets('swapping moves the questions, not the rectangles', (
      tester,
    ) async {
      // The rectangles are the half detection got right -- they sit exactly
      // on the printed columns. Only the attribution is in doubt.
      final read = await _pumpEditor(
        tester,
        regions: twoColumns(),
        questionNumbers: const ['問一', '問二'],
        conflicts: const [
          ['問一', '問二'],
        ],
      );

      await tester.tap(find.byKey(const Key('answer-area-swap-問一-問二')));
      await tester.pumpAndSettle();

      final after = read();
      expect(after.map((r) => r.label).toList(), ['問二', '問一']);
      expect(after[0].bbox.x0, closeTo(0.639, 1e-9));
      expect(after[1].bbox.x0, closeTo(0.798, 1e-9));
    });

    testWidgets('a confirmed profile offers no swap', (tester) async {
      await _pumpEditor(
        tester,
        regions: twoColumns(),
        questionNumbers: const ['問一', '問二'],
        conflicts: const [
          ['問一', '問二'],
        ],
        readOnly: true,
      );

      final button = tester.widget<TextButton>(
        find.ancestor(
          of: find.text('回答欄を入れ替える'),
          matching: find.byType(TextButton),
        ),
      );
      expect(button.onPressed, isNull);
    });
  });
}
