import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';

import 'package:auto_scoring_app/api/sidecar_api_client.dart';
import 'package:auto_scoring_app/core/app_dependencies.dart';
import 'package:auto_scoring_app/core/design/design_tokens.dart';
import 'package:auto_scoring_app/core/material_role_labels.dart';
import 'package:auto_scoring_app/core/widgets/app_error_banner.dart';

/// 設定画面 (Issue #101).
///
/// **One settings screen, with tabs.** Issue #101 fills in 取込の型; Issue
/// #96's API-key settings are meant to become a second tab here rather than a
/// second screen -- for the person using this, settings are one place.
///
/// The two will not share a *storage* location, and that is deliberate: a
/// template is a folder layout and lives as plain JSON under `app-data/`,
/// while an API key belongs in the OS credential store (Issue #96's decision).
/// Sitting next to each other on screen does not make them the same kind of
/// thing.
class SettingsPage extends ConsumerStatefulWidget {
  const SettingsPage({super.key});

  @override
  ConsumerState<SettingsPage> createState() => _SettingsPageState();
}

class _SettingsPageState extends ConsumerState<SettingsPage> {
  late final AppDependencies _dependencies;

  List<IntakeTemplateModel> _templates = const [];
  int _selected = 0;
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

  void _updateRules(List<IntakeRuleModel> rules) {
    _updateTemplate(
      (template) => template.rebuild((builder) => builder.rules.replace(rules)),
    );
  }

  @override
  Widget build(BuildContext context) {
    return DefaultTabController(
      length: 1,
      child: Scaffold(
        appBar: AppBar(
          title: const Text('設定'),
          bottom: const TabBar(
            tabs: [Tab(key: Key('settings-tab-intake'), text: '取込の型')],
          ),
        ),
        body: TabBarView(children: [_buildIntakeTab()]),
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
                      onChanged: (value) =>
                          setState(() => _selected = value ?? _selected),
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
            _updateRules(next);
          },
          itemBuilder: (context, index) =>
              _buildRuleRow(rules, index, key: ValueKey('rule-$index')),
        ),
        OutlinedButton.icon(
          key: const Key('settings-add-rule'),
          onPressed: () => _updateRules([
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
            onPressed: () => _updateRules([...rules]..removeAt(index)),
            icon: const Icon(Icons.delete_outline),
          ),
        ],
      ),
    );
  }
}
