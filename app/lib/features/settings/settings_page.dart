import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';

import 'package:auto_scoring_app/api/sidecar_api_client.dart';
import 'package:auto_scoring_app/core/app_dependencies.dart';
import 'package:auto_scoring_app/core/design/design_tokens.dart';
import 'package:auto_scoring_app/core/material_role_labels.dart';
import 'package:auto_scoring_app/core/widgets/app_error_banner.dart';
import 'package:auto_scoring_app/core/widgets/back_or_home_button.dart';
import 'package:auto_scoring_app/features/settings/api_key_tab.dart';

/// 設定画面 (Issue #101, Issue #96).
///
/// **One settings screen, with tabs.** Issue #101 filled in 取込の型 and
/// Issue #96 added API キー beside it rather than as a second screen -- for
/// the person using this, settings are one place.
///
/// The two do not share a *storage* location, and that is deliberate: a
/// template is a folder layout and lives as plain JSON under `app-data/`,
/// while an API key belongs in the OS credential store (Issue #96's
/// decision). Sitting next to each other on screen does not make them the
/// same kind of thing.
///
/// Only 取込の型 is built here. `ApiKeyTab` owns its own state and its own
/// rules about what may be shown, which is the point: a tab that must never
/// render the value it manages should not share a State object with one that
/// renders everything it holds.
class SettingsPage extends ConsumerStatefulWidget {
  const SettingsPage({super.key});

  @override
  ConsumerState<SettingsPage> createState() => _SettingsPageState();
}

class _SettingsPageState extends ConsumerState<SettingsPage> {
  late final AppDependencies _dependencies;

  List<IntakeTemplateModel> _templates = const [];
  int _selected = 0;

  /// Bumped on every *structural* change to the rule list (add, remove,
  /// reorder, template switch) and never on a keystroke -- see the row key in
  /// `_buildRuleList`. Typing must not rebuild the field the reviewer is
  /// typing into.
  int _rulesRevision = 0;
  final _costController = TextEditingController();
  bool _loading = true;
  bool _saving = false;
  String? _error;
  String? _savedNotice;

  @override
  void initState() {
    super.initState();
    _dependencies = ref.read(appDependenciesProvider);
    _load();
  }

  @override
  void dispose() {
    _costController.dispose();
    super.dispose();
  }

  Future<void> _load() async {
    try {
      final templates = await _dependencies.listIntakeTemplates();
      final cost = await _dependencies.intakeCost();
      if (!mounted) return;
      setState(() {
        _templates = templates;
        // Clamped, not trusted: `_selected` is a position, and a reload can
        // return a shorter list than the one it was chosen against. An index
        // past the end throws on `_templates[_selected]`, and a
        // `DropdownButtonFormField` whose value has no matching item asserts
        // -- the same shape as the two routing dropdowns on the intake screen.
        _selected = _selected.clamp(
          0,
          templates.isEmpty ? 0 : templates.length - 1,
        );
        _costController.text = cost?.toString() ?? '';
        _loading = false;
      });
    } on SidecarApiException catch (error) {
      if (!mounted) return;
      setState(() {
        _error = error.message;
        _loading = false;
      });
    }
  }

  Future<void> _save() async {
    setState(() {
      _saving = true;
      _error = null;
      _savedNotice = null;
    });
    try {
      final saved = await _dependencies.saveIntakeTemplates(_templates);
      final raw = _costController.text.trim();
      // An empty field means "I have not told you the price", which is a
      // different thing from zero -- the intake screen says so rather than
      // showing a figure nobody entered.
      final cost = raw.isEmpty ? null : double.tryParse(raw);
      if (raw.isNotEmpty && cost == null) {
        setState(() => _error = '1件あたりの単価は数字で入力してください。');
        return;
      }
      await _dependencies.saveIntakeCost(cost);
      if (!mounted) return;
      setState(() {
        _templates = saved;
        _savedNotice = '保存しました。次の取込から反映されます。';
      });
    } on SidecarApiException catch (error) {
      if (!mounted) return;
      setState(() => _error = error.message);
    } finally {
      if (mounted) setState(() => _saving = false);
    }
  }

  void _updateTemplate(
    IntakeTemplateModel Function(IntakeTemplateModel) update,
  ) {
    setState(() {
      _templates = [
        for (var i = 0; i < _templates.length; i++)
          i == _selected ? update(_templates[i]) : _templates[i],
      ];
    });
  }

  void _updateRules(List<IntakeRuleModel> rules, {bool structural = false}) {
    if (structural) _rulesRevision++;
    _updateTemplate(
      (template) => template.rebuild((builder) => builder.rules.replace(rules)),
    );
  }

  @override
  Widget build(BuildContext context) {
    return DefaultTabController(
      length: 2,
      child: Scaffold(
        appBar: AppBar(
          leading: const BackOrHomeButton(),
          title: const Text('設定'),
          bottom: const TabBar(
            tabs: [
              Tab(key: Key('settings-tab-intake'), text: '取込の型'),
              Tab(key: Key('settings-tab-api-key'), text: 'API キー'),
            ],
          ),
        ),
        // The 取込の型 tab's state lives in this widget, so it is built here;
        // the API-key tab owns its own and is a widget of its own. They share
        // a screen because settings are one place for the person using this,
        // not because they are the same kind of thing -- one is a folder
        // layout in plain JSON under `app-data/`, the other a secret in the
        // OS credential store (docs/intake-and-settings.md section 2.2).
        body: TabBarView(children: [_buildIntakeTab(), const ApiKeyTab()]),
      ),
    );
  }

  Widget _buildIntakeTab() {
    if (_loading) return const Center(child: CircularProgressIndicator());
    if (_templates.isEmpty) {
      return const Center(child: Text('取込の型がありません。'));
    }
    final template = _templates[_selected];
    // The list scrolls; the cost field and the save button do not. A save
    // action that has to be scrolled to is a save action people forget to
    // press, and the rule list grows with the template.
    return Column(
      children: [
        Expanded(
          child: ListView(
            padding: AppSpacing.page,
            children: [
              Row(
                children: [
                  Expanded(
                    child: DropdownButtonFormField<int>(
                      key: const Key('settings-template-picker'),
                      initialValue: _selected,
                      decoration: const InputDecoration(
                        labelText: '編集する型',
                        border: OutlineInputBorder(),
                      ),
                      items: [
                        for (var i = 0; i < _templates.length; i++)
                          DropdownMenuItem(
                            value: i,
                            child: Text(_templates[i].name),
                          ),
                      ],
                      onChanged: (value) => setState(() {
                        _selected = value ?? _selected;
                        // A different template's rules sit at the same
                        // positions, so every row has to be rebuilt.
                        _rulesRevision++;
                      }),
                    ),
                  ),
                  const SizedBox(width: AppSpacing.md),
                  OutlinedButton.icon(
                    key: const Key('settings-add-template'),
                    onPressed: _saving ? null : _addTemplate,
                    icon: const Icon(Icons.add),
                    label: const Text('型を追加'),
                  ),
                ],
              ),
              const SizedBox(height: AppSpacing.lg),
              TextFormField(
                key: Key('settings-template-name-${template.id}'),
                initialValue: template.name,
                decoration: const InputDecoration(
                  labelText: '型の名前',
                  border: OutlineInputBorder(),
                ),
                onChanged: (value) => _updateTemplate(
                  (current) =>
                      current.rebuild((builder) => builder.name = value),
                ),
              ),
              const SizedBox(height: AppSpacing.md),
              SwitchListTile(
                key: const Key('settings-split-child-directories'),
                value: template.splitChildDirectories ?? true,
                title: const Text('選んだフォルダの直下の各フォルダを、それぞれ別のテストとして取り込む'),
                subtitle: const Text('教科ごとにフォルダが分かれている資料はこれを有効にします。'),
                onChanged: (value) => _updateTemplate(
                  (current) => current.rebuild(
                    (builder) => builder.splitChildDirectories = value,
                  ),
                ),
              ),
              const SizedBox(height: AppSpacing.md),
              Text(
                '規則（上から順に当てはめます）',
                style: Theme.of(context).textTheme.titleMedium,
              ),
              _buildRuleList(template),
            ],
          ),
        ),
        const Divider(height: 1),
        Padding(
          padding: AppSpacing.card,
          child: Column(
            crossAxisAlignment: CrossAxisAlignment.stretch,
            children: [
              TextFormField(
                key: const Key('settings-unit-cost'),
                controller: _costController,
                keyboardType: TextInputType.number,
                decoration: const InputDecoration(
                  labelText: 'AI判定 1件あたりの単価',
                  border: OutlineInputBorder(),
                  helperText:
                      'このアプリは提供元の料金を知りません。'
                      '空欄のままなら、取込画面では「単価が未設定」と表示します。',
                ),
              ),
              const SizedBox(height: AppSpacing.md),
              if (_error != null) AppErrorBanner(message: _error!),
              if (_savedNotice != null)
                Text(_savedNotice!, key: const Key('settings-saved-notice')),
              const SizedBox(height: AppSpacing.sm),
              FilledButton.icon(
                key: const Key('settings-save'),
                onPressed: _saving ? null : _save,
                icon: const Icon(Icons.save),
                label: const Text('保存する'),
              ),
            ],
          ),
        ),
      ],
    );
  }

  void _addTemplate() {
    setState(() {
      _templates = [
        ..._templates,
        IntakeTemplateModel(
          (builder) => builder
            ..id = 'template-${DateTime.now().microsecondsSinceEpoch}'
            ..name = '新しい型'
            ..splitChildDirectories = true
            ..rules.replace(const <IntakeRuleModel>[]),
        ),
      ];
      _selected = _templates.length - 1;
      _rulesRevision++;
    });
  }

  Widget _buildRuleList(IntakeTemplateModel template) {
    final rules = template.rules.toList();
    return Column(
      crossAxisAlignment: CrossAxisAlignment.start,
      children: [
        ReorderableListView.builder(
          shrinkWrap: true,
          physics: const NeverScrollableScrollPhysics(),
          itemCount: rules.length,
          onReorder: (oldIndex, newIndex) {
            // Order is meaning here: the first matching rule wins, so
            // moving a row changes which rule claims a file.
            final next = [...rules];
            final moved = next.removeAt(oldIndex);
            next.insert(newIndex > oldIndex ? newIndex - 1 : newIndex, moved);
            _updateRules(structural: true, next);
          },
          itemBuilder: (context, index) =>
              // The key carries `_rulesRevision`, which changes whenever
              // rules are added, removed, reordered, or a different template
              // is selected -- and never on a keystroke.
              // `TextFormField.initialValue` is only read when its element is
              // first built, so a row keyed by position alone keeps the text of
              // whatever rule used to sit there: after a delete or a reorder
              // the reviewer sees one pattern and saves another. Changing the
              // key discards the subtree and rebuilds it from the rule now at
              // that position.
              _buildRuleRow(
                rules,
                index,
                key: ValueKey('rule-$_selected-$_rulesRevision-$index'),
              ),
        ),
        OutlinedButton.icon(
          key: const Key('settings-add-rule'),
          onPressed: () => _updateRules(structural: true, [
            ...rules,
            IntakeRuleModel(
              (builder) => builder
                ..scope = RuleScope.file
                ..pattern = '*'
                ..role = MaterialRole.reference
                ..requirement = Requirement.optional,
            ),
          ]),
          icon: const Icon(Icons.add),
          label: const Text('規則を追加'),
        ),
      ],
    );
  }

  Widget _buildRuleRow(
    List<IntakeRuleModel> rules,
    int index, {
    required Key key,
  }) {
    final rule = rules[index];
    void replace(IntakeRuleModel next) =>
        _updateRules([...rules]..[index] = next);
    return Padding(
      key: key,
      padding: const EdgeInsets.symmetric(vertical: AppSpacing.xs),
      child: Row(
        children: [
          const Icon(Icons.drag_handle),
          const SizedBox(width: AppSpacing.sm),
          Expanded(
            child: DropdownButton<RuleScope>(
              key: Key('settings-rule-scope-$index'),
              isExpanded: true,
              value: rule.scope,
              items: const [
                DropdownMenuItem(value: RuleScope.file, child: Text('ファイル名')),
                DropdownMenuItem(value: RuleScope.folder, child: Text('フォルダ名')),
              ],
              onChanged: (value) => replace(
                rule.rebuild((builder) => builder.scope = value ?? rule.scope),
              ),
            ),
          ),
          const SizedBox(width: AppSpacing.sm),
          Expanded(
            flex: 2,
            child: TextFormField(
              key: Key('settings-rule-pattern-$index'),
              initialValue: rule.pattern,
              decoration: const InputDecoration(labelText: 'パターン'),
              onChanged: (value) =>
                  replace(rule.rebuild((builder) => builder.pattern = value)),
            ),
          ),
          const SizedBox(width: AppSpacing.sm),
          Expanded(
            flex: 2,
            child: DropdownButton<MaterialRole>(
              key: Key('settings-rule-role-$index'),
              isExpanded: true,
              value: rule.role,
              items: [
                for (final role in MaterialRole.values)
                  DropdownMenuItem(
                    value: role,
                    child: Text(materialRoleLabel(role)),
                  ),
              ],
              onChanged: (value) => replace(
                rule.rebuild((builder) => builder.role = value ?? rule.role),
              ),
            ),
          ),
          const SizedBox(width: AppSpacing.sm),
          Expanded(
            child: DropdownButton<Requirement>(
              key: Key('settings-rule-requirement-$index'),
              isExpanded: true,
              value: rule.requirement,
              items: const [
                DropdownMenuItem(
                  value: Requirement.required_,
                  child: Text('必須'),
                ),
                DropdownMenuItem(
                  value: Requirement.recommended,
                  child: Text('推奨'),
                ),
                DropdownMenuItem(
                  value: Requirement.optional,
                  child: Text('任意'),
                ),
              ],
              onChanged: (value) => replace(
                rule.rebuild(
                  (builder) => builder.requirement = value ?? rule.requirement,
                ),
              ),
            ),
          ),
          IconButton(
            key: Key('settings-remove-rule-$index'),
            tooltip: 'この規則を削除',
            onPressed: () =>
                _updateRules(structural: true, [...rules]..removeAt(index)),
            icon: const Icon(Icons.delete_outline),
          ),
        ],
      ),
    );
  }
}
