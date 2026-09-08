import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';

import 'package:auto_scoring_app/api/sidecar_api_client.dart';
import 'package:auto_scoring_app/core/app_dependencies.dart';
import 'package:auto_scoring_app/core/app_routes.dart';

import 'app_harness.dart';

/// 設定画面 (Issue #101), acceptance criterion 4: the 取込の型 can be edited
/// and what is saved is what the next intake uses.
void main() {
  /// The text a pattern field is actually showing.
  String patternText(WidgetTester tester, int index) => tester
      .widget<EditableText>(
        find.descendant(
          of: find.byKey(Key('settings-rule-pattern-$index')),
          matching: find.byType(EditableText),
        ),
      )
      .controller
      .text;

  IntakeRuleModel rule({
    String pattern = '01_*',
    MaterialRole role = MaterialRole.studentAnswer,
    Requirement requirement = Requirement.required_,
    RuleScope scope = RuleScope.file,
  }) => IntakeRuleModel(
    (builder) => builder
      ..scope = scope
      ..pattern = pattern
      ..role = role
      ..requirement = requirement,
  );

  IntakeTemplateModel template({List<IntakeRuleModel>? rules}) =>
      IntakeTemplateModel(
        (builder) => builder
          ..id = 'serial-number-prefix'
          ..name = '連番の接頭辞 (既定)'
          ..splitChildDirectories = true
          ..rules.replace(rules ?? [rule()]),
      );

  testWidgets('既定の型の規則が表示される', (tester) async {
    await pumpAppAt(
      tester,
      AppRoutes.settings,
      dependencies: AppDependencies(
        listIntakeTemplates: () async => [template()],
        intakeCost: () async => null,
      ),
    );
    await tester.pumpAndSettle();

    expect(find.byKey(const Key('settings-rule-pattern-0')), findsOneWidget);
    expect(find.byKey(const Key('settings-tab-intake')), findsOneWidget);
  });

  testWidgets('規則を編集して保存すると、その内容が送られる (受入条件4)', (tester) async {
    List<IntakeTemplateModel>? saved;
    await pumpAppAt(
      tester,
      AppRoutes.settings,
      dependencies: AppDependencies(
        listIntakeTemplates: () async => [template()],
        intakeCost: () async => null,
        saveIntakeTemplates: (templates) async {
          saved = templates;
          return templates;
        },
        saveIntakeCost: (cost) async => cost,
      ),
    );
    await tester.pumpAndSettle();

    await tester.enterText(
      find.byKey(const Key('settings-rule-pattern-0')),
      'answers_*',
    );
    await tester.tap(find.byKey(const Key('settings-save')));
    await tester.pumpAndSettle();

    expect(saved, isNotNull);
    expect(saved!.single.rules.single.pattern, 'answers_*');
    expect(find.byKey(const Key('settings-saved-notice')), findsOneWidget);
  });

  testWidgets('規則を追加・削除できる', (tester) async {
    List<IntakeTemplateModel>? saved;
    await pumpAppAt(
      tester,
      AppRoutes.settings,
      dependencies: AppDependencies(
        listIntakeTemplates: () async => [template()],
        intakeCost: () async => null,
        saveIntakeTemplates: (templates) async {
          saved = templates;
          return templates;
        },
        saveIntakeCost: (cost) async => cost,
      ),
    );
    await tester.pumpAndSettle();

    // The rule list scrolls, so the "add" control below it may be off-screen
    // in a narrow test viewport.
    await tester.ensureVisible(find.byKey(const Key('settings-add-rule')));
    await tester.pumpAndSettle();
    await tester.tap(find.byKey(const Key('settings-add-rule')));
    await tester.pumpAndSettle();
    await tester.tap(find.byKey(const Key('settings-save')));
    await tester.pumpAndSettle();
    expect(saved!.single.rules, hasLength(2));

    await tester.ensureVisible(find.byKey(const Key('settings-remove-rule-1')));
    await tester.pumpAndSettle();
    await tester.tap(find.byKey(const Key('settings-remove-rule-1')));
    await tester.pumpAndSettle();
    await tester.tap(find.byKey(const Key('settings-save')));
    await tester.pumpAndSettle();
    expect(saved!.single.rules, hasLength(1));
  });

  testWidgets('単価は空欄のまま保存できる（0円と言わないため）', (tester) async {
    // Empty means "I have not told you the price", which the intake screen
    // reports as unknown. Coercing it to 0 would put a figure nobody entered
    // in front of the reviewer.
    double? savedCost = 1.0;
    var called = false;
    await pumpAppAt(
      tester,
      AppRoutes.settings,
      dependencies: AppDependencies(
        listIntakeTemplates: () async => [template()],
        intakeCost: () async => null,
        saveIntakeTemplates: (templates) async => templates,
        saveIntakeCost: (cost) async {
          called = true;
          savedCost = cost;
          return cost;
        },
      ),
    );
    await tester.pumpAndSettle();

    await tester.tap(find.byKey(const Key('settings-save')));
    await tester.pumpAndSettle();

    expect(called, isTrue);
    expect(savedCost, isNull);
  });

  testWidgets('単価が数字でなければ保存しない', (tester) async {
    var called = false;
    await pumpAppAt(
      tester,
      AppRoutes.settings,
      dependencies: AppDependencies(
        listIntakeTemplates: () async => [template()],
        intakeCost: () async => null,
        saveIntakeTemplates: (templates) async => templates,
        saveIntakeCost: (cost) async {
          called = true;
          return cost;
        },
      ),
    );
    await tester.pumpAndSettle();

    await tester.enterText(find.byKey(const Key('settings-unit-cost')), 'たかい');
    await tester.tap(find.byKey(const Key('settings-save')));
    await tester.pumpAndSettle();

    expect(called, isFalse);
    expect(find.textContaining('数字で入力してください'), findsOneWidget);
  });

  testWidgets('型を複数保存できる', (tester) async {
    List<IntakeTemplateModel>? saved;
    await pumpAppAt(
      tester,
      AppRoutes.settings,
      dependencies: AppDependencies(
        listIntakeTemplates: () async => [template()],
        intakeCost: () async => null,
        saveIntakeTemplates: (templates) async {
          saved = templates;
          return templates;
        },
        saveIntakeCost: (cost) async => cost,
      ),
    );
    await tester.pumpAndSettle();

    await tester.tap(find.byKey(const Key('settings-add-template')));
    await tester.pumpAndSettle();
    await tester.tap(find.byKey(const Key('settings-save')));
    await tester.pumpAndSettle();

    expect(saved, hasLength(2));
  });

  testWidgets('規則を削除したあと、表示と保存内容が食い違わない', (tester) async {
    // `TextFormField.initialValue` is only read when its element is first
    // built, so a row keyed by position alone kept the deleted rule's text:
    // the reviewer saw `first_*` and saved `second_*`.
    List<IntakeTemplateModel>? saved;
    await pumpAppAt(
      tester,
      AppRoutes.settings,
      dependencies: AppDependencies(
        listIntakeTemplates: () async => [
          template(
            rules: [
              rule(pattern: 'first_*'),
              rule(pattern: 'second_*', role: MaterialRole.gradingCriteria),
            ],
          ),
        ],
        intakeCost: () async => null,
        saveIntakeTemplates: (templates) async {
          saved = templates;
          return templates;
        },
        saveIntakeCost: (cost) async => cost,
      ),
    );
    await tester.pumpAndSettle();

    await tester.ensureVisible(find.byKey(const Key('settings-remove-rule-0')));
    await tester.pumpAndSettle();
    await tester.tap(find.byKey(const Key('settings-remove-rule-0')));
    await tester.pumpAndSettle();

    // Asserted on the *rendered* text, not on the widget's `initialValue`
    // property: the property is rebuilt correctly either way, and it is the
    // field's retained state that goes stale.
    expect(patternText(tester, 0), 'second_*');

    await tester.tap(find.byKey(const Key('settings-save')));
    await tester.pumpAndSettle();
    expect(saved!.single.rules.single.pattern, 'second_*');
  });

  testWidgets('型を切り替えても、前の型の規則が残らない', (tester) async {
    await pumpAppAt(
      tester,
      AppRoutes.settings,
      dependencies: AppDependencies(
        listIntakeTemplates: () async => [
          template(rules: [rule(pattern: 'alpha_*')]),
          IntakeTemplateModel(
            (builder) => builder
              ..id = 'other'
              ..name = 'もう一つの型'
              ..splitChildDirectories = true
              ..rules.replace([rule(pattern: 'beta_*')]),
          ),
        ],
        intakeCost: () async => null,
      ),
    );
    await tester.pumpAndSettle();

    expect(patternText(tester, 0), 'alpha_*');

    await tester.tap(find.byKey(const Key('settings-template-picker')));
    await tester.pumpAndSettle();
    await tester.tap(find.text('もう一つの型').last);
    await tester.pumpAndSettle();

    expect(patternText(tester, 0), 'beta_*');
  });

  testWidgets('パターンを打っている最中に入力欄が作り直されない', (tester) async {
    // The fix must not key on the pattern itself: that would rebuild the field
    // on every keystroke and take the cursor with it.
    await pumpAppAt(
      tester,
      AppRoutes.settings,
      dependencies: AppDependencies(
        listIntakeTemplates: () async => [template()],
        intakeCost: () async => null,
      ),
    );
    await tester.pumpAndSettle();

    final before = tester.state(
      find.byKey(const Key('settings-rule-pattern-0')),
    );
    await tester.enterText(
      find.byKey(const Key('settings-rule-pattern-0')),
      '01_answers_*',
    );
    await tester.pumpAndSettle();

    expect(
      tester.state(find.byKey(const Key('settings-rule-pattern-0'))),
      same(before),
    );
  });
}
