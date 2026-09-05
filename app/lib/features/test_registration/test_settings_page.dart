import 'package:flutter/material.dart';
import 'package:flutter/services.dart';

import 'package:auto_scoring_app/api/sidecar_api_client.dart';
import 'package:auto_scoring_app/core/app_dependencies.dart';

/// テスト設定画面 (simplified-design-specification.md §16.3, Issue #16).
///
/// Lets a reviewer confirm/correct what candidate generation produced before
/// a test can register:
///
/// * the profile's regions (問題文/回答欄/○×等候補領域/配点/採点基準/模範解答, one
///   list per page, editable as plain fields rather than a PDF overlay --
///   see docs/test-registration.md for why the PDF-overlay editor is out of
///   scope here) -- `Profile.status` moves `draft` -> `confirmed` only once
///   every region has been reviewed (`confirmProfile`).
/// * the question-dependency graph (Issue #26): candidate edges, their
///   rationale, and any question the analyzer could not resolve, plus the
///   parallel-execution layers a confirmed graph implies. A reviewer can
///   add/remove edges before confirming; `confirmDependencyGraph` rejects a
///   cyclic edge set (422) so a confirmed graph is always a DAG.
///
/// `completeRegistration` (登録完了) only succeeds once *both* are confirmed
/// -- the Issue #16 acceptance criterion "全必須項目確認後にだけ登録完了になる"
/// and the Issue #16 追加要件 "設問依存関係を...明示確認するまでテストをreadyに
/// しない".
class TestSettingsPage extends StatefulWidget {
  const TestSettingsPage({
    super.key,
    required this.dependencies,
    required this.testId,
  });

  final AppDependencies dependencies;
  final String testId;

  @override
  State<TestSettingsPage> createState() => _TestSettingsPageState();
}

class _TestSettingsPageState extends State<TestSettingsPage> {
  TestResponse? _test;
  ProfileResponse? _profile;
  DependencyGraphResponse? _dependencyGraph;

  /// Working copy of the profile's regions, edited locally before `保存`
  /// (`updateProfile`) persists it. `null` until the profile has loaded once.
  List<RegionModel>? _editableRegions;

  /// Working copy of the dependency graph's edges, edited locally before
  /// `確定` (`confirmDependencyGraph`). `null` until a graph has loaded once.
  List<DependencyEdgeModel>? _editableEdges;

  bool _loading = true;
  bool _busy = false;
  String? _errorMessage;

  @override
  void initState() {
    super.initState();
    _loadAll();
  }

  Future<void> _loadAll() async {
    setState(() {
      _loading = true;
      _errorMessage = null;
    });
    try {
      final test = await widget.dependencies.getTest(widget.testId);
      ProfileResponse? profile;
      try {
        profile = await widget.dependencies.getProfile(widget.testId);
      } on SidecarApiException catch (error) {
        if (error.statusCode != 404) rethrow;
      }
      DependencyGraphResponse? graph;
      try {
        graph = await widget.dependencies.getDependencyGraph(widget.testId);
      } on SidecarApiException catch (error) {
        if (error.statusCode != 404) rethrow;
      }
      if (!mounted) return;
      setState(() {
        _test = test;
        _profile = profile;
        _editableRegions = profile?.regions.toList();
        _dependencyGraph = graph;
        _editableEdges = graph?.edges.toList();
      });
    } on SidecarApiException catch (error) {
      if (!mounted) return;
      setState(() => _errorMessage = error.message);
    } finally {
      if (mounted) setState(() => _loading = false);
    }
  }

  Future<void> _runGuarded(Future<void> Function() action) async {
    setState(() {
      _busy = true;
      _errorMessage = null;
    });
    try {
      await action();
    } on SidecarApiException catch (error) {
      if (!mounted) return;
      setState(() => _errorMessage = error.message);
    } finally {
      if (mounted) setState(() => _busy = false);
    }
  }

  Future<void> _analyzeProfile() => _runGuarded(() async {
    final profile = await widget.dependencies.analyzeProfile(widget.testId);
    if (!mounted) return;
    setState(() {
      _profile = profile;
      _editableRegions = profile.regions.toList();
    });
  });

  Future<void> _saveProfile() => _runGuarded(() async {
    final regions = _editableRegions;
    if (regions == null) return;
    final profile = await widget.dependencies.updateProfile(
      widget.testId,
      regions,
    );
    if (!mounted) return;
    setState(() {
      _profile = profile;
      _editableRegions = profile.regions.toList();
    });
    _showSnackBar('プロファイルを保存しました');
  });

  Future<void> _confirmProfile() => _runGuarded(() async {
    final regions = _editableRegions;
    if (regions == null) return;
    // Persist whatever the reviewer edited/added/removed *before*
    // confirming: confirmProfile only ever sends the test id, so without
    // this an edit made after the last explicit "保存" tap (or never saved
    // at all) would be silently discarded and the server would confirm a
    // stale, previously-persisted region set instead (Issue #16 review).
    final saved = await widget.dependencies.updateProfile(
      widget.testId,
      regions,
    );
    if (!mounted) return;
    setState(() {
      _profile = saved;
      _editableRegions = saved.regions.toList();
    });
    final profile = await widget.dependencies.confirmProfile(widget.testId);
    if (!mounted) return;
    setState(() {
      _profile = profile;
      _editableRegions = profile.regions.toList();
    });
    _showSnackBar('プロファイルを確定しました');
  });

  Future<void> _analyzeDependencyGraph() => _runGuarded(() async {
    // The dependency analyzer only sees 問題文 (prompt text) via an
    // explicit override -- `Question` has no column for it yet, so unless
    // this is passed, a dependency stated only in a question's own prompt
    // (as opposed to the model answer or rubric, which the analyzer already
    // reads from the confirmed Question/Rubric rows) would be invisible and
    // the analyzer could wrongly conclude "no dependency" (Issue #16
    // review). QUESTION regions only exist once the profile has been
    // confirmed (that's also a prerequisite for this endpoint to find any
    // Question rows at all), so `_profile` here always holds the confirmed
    // set with real text.
    final overrides = [
      for (final region in _profile?.regions ?? const <RegionModel>[])
        if (region.kind == RegionKind.question)
          QuestionTextOverride(
            (b) => b
              ..questionId = '${widget.testId}:${region.label}'
              ..promptText = region.text,
          ),
    ];
    final graph = await widget.dependencies.analyzeDependencyGraph(
      widget.testId,
      overrides: overrides,
    );
    if (!mounted) return;
    setState(() {
      _dependencyGraph = graph;
      _editableEdges = graph.edges.toList();
    });
  });

  Future<void> _confirmDependencyGraph() => _runGuarded(() async {
    final graph = _dependencyGraph;
    final edges = _editableEdges;
    if (graph == null || edges == null) return;
    final confirmed = await widget.dependencies.confirmDependencyGraph(
      widget.testId,
      version: graph.version,
      edges: edges,
    );
    if (!mounted) return;
    setState(() {
      _dependencyGraph = confirmed;
      _editableEdges = confirmed.edges.toList();
    });
    _showSnackBar('設問依存関係グラフを確定しました');
  });

  Future<void> _completeRegistration() => _runGuarded(() async {
    final result = await widget.dependencies.completeRegistration(
      widget.testId,
    );
    if (!mounted) return;
    setState(() => _test = result.test);
    _showSnackBar('テスト登録が完了しました');
  });

  void _showSnackBar(String message) {
    ScaffoldMessenger.of(
      context,
    ).showSnackBar(SnackBar(content: Text(message)));
  }

  bool get _profileConfirmed => _profile?.status == 'confirmed';
  bool get _dependencyGraphConfirmed => _dependencyGraph?.status == 'confirmed';
  bool get _isReady => _test?.status == 'ready';

  void _addRegion() {
    final regions = _editableRegions;
    if (regions == null) return;
    setState(() {
      regions.add(
        RegionModel(
          (b) => b
            ..regionId = 'manual-${regions.length + 1}'
            ..kind = RegionKind.question
            ..pageIndex = 0
            ..label = ''
            ..confirmed = false
            ..bbox.x0 = 0.1
            ..bbox.y0 = 0.1
            ..bbox.x1 = 0.3
            ..bbox.y1 = 0.2,
        ),
      );
    });
  }

  void _removeRegion(int index) {
    setState(() => _editableRegions?.removeAt(index));
  }

  Future<void> _editRegion(int index) async {
    final regions = _editableRegions;
    if (regions == null) return;
    final updated = await showDialog<RegionModel>(
      context: context,
      builder: (_) => _RegionEditDialog(region: regions[index]),
    );
    if (updated == null) return;
    setState(() => regions[index] = updated);
  }

  void _addEdge() {
    final questionIds = _dependencyGraph?.questionIds.toList() ?? const [];
    if (questionIds.length < 2) return;
    setState(() {
      _editableEdges?.add(
        DependencyEdgeModel(
          (b) => b
            ..fromQuestionId = questionIds[0]
            ..toQuestionId = questionIds[1]
            ..rationale = '人間が追加'
            ..provides.replace([DependencyProvision.recognizedText]),
        ),
      );
    });
  }

  void _removeEdge(int index) {
    setState(() => _editableEdges?.removeAt(index));
  }

  Future<void> _editEdge(int index) async {
    final edges = _editableEdges;
    final questionIds = _dependencyGraph?.questionIds.toList();
    if (edges == null || questionIds == null) return;
    final updated = await showDialog<DependencyEdgeModel>(
      context: context,
      builder: (_) =>
          _EdgeEditDialog(edge: edges[index], questionIds: questionIds),
    );
    if (updated == null) return;
    setState(() => edges[index] = updated);
  }

  @override
  Widget build(BuildContext context) {
    return Scaffold(
      appBar: AppBar(title: Text(_test?.name ?? 'テスト設定')),
      body: _loading
          ? const Center(child: CircularProgressIndicator())
          : RefreshIndicator(
              onRefresh: _loadAll,
              child: ListView(
                padding: const EdgeInsets.all(16),
                children: [
                  _buildStatusBanner(),
                  if (_errorMessage != null) ...[
                    const SizedBox(height: 8),
                    _buildErrorBanner(),
                  ],
                  if (_busy) ...[
                    const SizedBox(height: 8),
                    const LinearProgressIndicator(),
                  ],
                  const SizedBox(height: 16),
                  _buildProfileSection(),
                  const SizedBox(height: 24),
                  _buildDependencyGraphSection(),
                  const SizedBox(height: 24),
                  _buildCompleteRegistrationButton(),
                ],
              ),
            ),
    );
  }

  Widget _buildStatusBanner() {
    final status = _test?.status ?? 'draft';
    return Card(
      child: Padding(
        padding: const EdgeInsets.all(12),
        child: Row(
          children: [
            Icon(status == 'ready' ? Icons.verified : Icons.pending_actions),
            const SizedBox(width: 8),
            Text(
              status == 'ready' ? 'テスト状態: 登録完了' : 'テスト状態: 下書き',
              key: const Key('test-status-label'),
            ),
          ],
        ),
      ),
    );
  }

  Widget _buildErrorBanner() {
    return Card(
      color: Theme.of(context).colorScheme.errorContainer,
      child: Padding(
        padding: const EdgeInsets.all(12),
        child: Row(
          children: [
            Icon(
              Icons.error_outline,
              color: Theme.of(context).colorScheme.onErrorContainer,
            ),
            const SizedBox(width: 8),
            Expanded(
              child: Text(
                _errorMessage!,
                key: const Key('settings-error-message'),
                style: TextStyle(
                  color: Theme.of(context).colorScheme.onErrorContainer,
                ),
              ),
            ),
          ],
        ),
      ),
    );
  }

  Widget _buildProfileSection() {
    final regions = _editableRegions;
    return Card(
      child: Padding(
        padding: const EdgeInsets.all(16),
        child: Column(
          crossAxisAlignment: CrossAxisAlignment.stretch,
          children: [
            Row(
              children: [
                Expanded(
                  child: Text(
                    'テストプロファイル（設問・回答欄・配点・採点基準・模範解答）',
                    style: Theme.of(context).textTheme.titleMedium,
                  ),
                ),
                if (_profileConfirmed)
                  const Chip(label: Text('確認済み'))
                else
                  const Chip(label: Text('未確認')),
              ],
            ),
            const SizedBox(height: 8),
            Wrap(
              spacing: 8,
              children: [
                FilledButton.icon(
                  key: const Key('analyze-profile-button'),
                  onPressed: (_busy || _profileConfirmed)
                      ? null
                      : _analyzeProfile,
                  icon: const Icon(Icons.auto_fix_high),
                  label: const Text('自動解析（再実行）'),
                ),
                OutlinedButton.icon(
                  onPressed: (_busy || regions == null || _profileConfirmed)
                      ? null
                      : _addRegion,
                  icon: const Icon(Icons.add_box_outlined),
                  label: const Text('領域を手動追加'),
                ),
              ],
            ),
            const SizedBox(height: 12),
            if (regions == null)
              const Text('まだ解析されていません。「自動解析」を実行してください。')
            else if (regions.isEmpty)
              const Text('領域がありません。手動で追加してください。')
            else
              ...regions.asMap().entries.map(
                (entry) => _buildRegionTile(entry.key, entry.value),
              ),
            const SizedBox(height: 12),
            Wrap(
              spacing: 8,
              children: [
                OutlinedButton.icon(
                  key: const Key('save-profile-button'),
                  onPressed: (_busy || regions == null || _profileConfirmed)
                      ? null
                      : _saveProfile,
                  icon: const Icon(Icons.save_outlined),
                  label: const Text('修正内容を保存'),
                ),
                FilledButton.icon(
                  key: const Key('confirm-profile-button'),
                  onPressed:
                      (_busy ||
                          regions == null ||
                          regions.isEmpty ||
                          _profileConfirmed)
                      ? null
                      : _confirmProfile,
                  icon: const Icon(Icons.check_circle_outline),
                  label: const Text('プロファイルを確定'),
                ),
              ],
            ),
          ],
        ),
      ),
    );
  }

  Widget _buildRegionTile(int index, RegionModel region) {
    return ListTile(
      key: Key('region-tile-$index'),
      leading: Icon(_regionIcon(region.kind)),
      title: Text('${_regionKindLabel(region.kind)} ・ 設問${region.label}'),
      subtitle: Text(
        'ページ${region.pageIndex + 1} ・ '
        '(${region.bbox.x0.toStringAsFixed(2)}, ${region.bbox.y0.toStringAsFixed(2)}) - '
        '(${region.bbox.x1.toStringAsFixed(2)}, ${region.bbox.y1.toStringAsFixed(2)})'
        '${region.text != null && region.text!.isNotEmpty ? '\n${region.text}' : ''}',
      ),
      isThreeLine: region.text != null && region.text!.isNotEmpty,
      trailing: _profileConfirmed
          ? null
          : Row(
              mainAxisSize: MainAxisSize.min,
              children: [
                IconButton(
                  icon: const Icon(Icons.edit_outlined),
                  tooltip: '編集',
                  onPressed: () => _editRegion(index),
                ),
                IconButton(
                  icon: const Icon(Icons.delete_outline),
                  tooltip: '削除',
                  onPressed: () => _removeRegion(index),
                ),
              ],
            ),
    );
  }

  Widget _buildDependencyGraphSection() {
    final graph = _dependencyGraph;
    final edges = _editableEdges;
    return Card(
      child: Padding(
        padding: const EdgeInsets.all(16),
        child: Column(
          crossAxisAlignment: CrossAxisAlignment.stretch,
          children: [
            Row(
              children: [
                Expanded(
                  child: Text(
                    '設問依存関係グラフ',
                    style: Theme.of(context).textTheme.titleMedium,
                  ),
                ),
                if (_dependencyGraphConfirmed)
                  const Chip(label: Text('確認済み'))
                else
                  const Chip(label: Text('未確認')),
              ],
            ),
            const SizedBox(height: 8),
            Wrap(
              spacing: 8,
              children: [
                FilledButton.icon(
                  key: const Key('analyze-dependency-graph-button'),
                  // Gated on the *profile* being confirmed, not merely
                  // analyzed: Question rows (what the dependency-graph
                  // endpoint actually operates on) are only created by
                  // confirmProfile, so tapping this in the normal
                  // draft-profile interim would always hit the backend's
                  // 404 "no questions to analyze" (Issue #16 review).
                  onPressed:
                      (_busy || _dependencyGraphConfirmed || !_profileConfirmed)
                      ? null
                      : _analyzeDependencyGraph,
                  icon: const Icon(Icons.auto_fix_high),
                  label: const Text('依存関係を分析（再実行）'),
                ),
                OutlinedButton.icon(
                  onPressed:
                      (_busy ||
                          _dependencyGraphConfirmed ||
                          graph == null ||
                          graph.questionIds.length < 2)
                      ? null
                      : _addEdge,
                  icon: const Icon(Icons.add_link),
                  label: const Text('依存関係を手動追加'),
                ),
              ],
            ),
            const SizedBox(height: 12),
            if (graph == null)
              const Text('まだ分析されていません。「依存関係を分析」を実行してください。')
            else ...[
              if (edges == null || edges.isEmpty)
                const Text('依存関係はありません（すべて独立した設問）。')
              else
                ...edges.asMap().entries.map(
                  (entry) => _buildEdgeTile(entry.key, entry.value),
                ),
              if (graph.unresolved.isNotEmpty) ...[
                const SizedBox(height: 8),
                Text(
                  '要確認（AIが依存を判断できなかった設問）',
                  style: Theme.of(context).textTheme.titleSmall,
                ),
                for (final unresolved in graph.unresolved)
                  ListTile(
                    leading: const Icon(Icons.help_outline),
                    title: Text('設問 ${unresolved.questionId}'),
                    subtitle: Text(unresolved.reason),
                  ),
              ],
              const SizedBox(height: 8),
              Text('並列実行可能な層', style: Theme.of(context).textTheme.titleSmall),
              for (final (i, layer) in graph.layers.indexed)
                Text('第${i + 1}層: ${layer.join(', ')}'),
            ],
            const SizedBox(height: 12),
            FilledButton.icon(
              key: const Key('confirm-dependency-graph-button'),
              onPressed: (_busy || graph == null || _dependencyGraphConfirmed)
                  ? null
                  : _confirmDependencyGraph,
              icon: const Icon(Icons.check_circle_outline),
              label: const Text('依存関係グラフを確定'),
            ),
          ],
        ),
      ),
    );
  }

  Widget _buildEdgeTile(int index, DependencyEdgeModel edge) {
    return ListTile(
      key: Key('edge-tile-$index'),
      leading: const Icon(Icons.arrow_forward),
      title: Text('${edge.fromQuestionId} → ${edge.toQuestionId}'),
      subtitle: Text(edge.rationale),
      trailing: _dependencyGraphConfirmed
          ? null
          : Row(
              mainAxisSize: MainAxisSize.min,
              children: [
                IconButton(
                  icon: const Icon(Icons.edit_outlined),
                  tooltip: '編集',
                  onPressed: () => _editEdge(index),
                ),
                IconButton(
                  icon: const Icon(Icons.delete_outline),
                  tooltip: '削除',
                  onPressed: () => _removeEdge(index),
                ),
              ],
            ),
    );
  }

  Widget _buildCompleteRegistrationButton() {
    final canComplete =
        !_busy && !_isReady && _profileConfirmed && _dependencyGraphConfirmed;
    return FilledButton.icon(
      key: const Key('complete-registration-button'),
      onPressed: canComplete ? _completeRegistration : null,
      icon: const Icon(Icons.task_alt),
      label: Text(_isReady ? '登録完了済み' : '登録完了'),
    );
  }
}

IconData _regionIcon(RegionKind kind) => switch (kind) {
  RegionKind.question => Icons.help_outline,
  RegionKind.answerArea => Icons.edit_note,
  RegionKind.annotationArea => Icons.rate_review_outlined,
  RegionKind.score => Icons.grade_outlined,
  RegionKind.rubric => Icons.rule_outlined,
  RegionKind.modelAnswer => Icons.fact_check_outlined,
  _ => Icons.crop_square,
};

String _regionKindLabel(RegionKind kind) => switch (kind) {
  RegionKind.question => '問題文',
  RegionKind.answerArea => '回答欄',
  RegionKind.annotationArea => '添削記号領域',
  RegionKind.score => '配点',
  RegionKind.rubric => '採点基準',
  RegionKind.modelAnswer => '模範解答',
  _ => kind.toString(),
};

/// Edits one region's kind/page/label/bbox/text in place.
class _RegionEditDialog extends StatefulWidget {
  const _RegionEditDialog({required this.region});

  final RegionModel region;

  @override
  State<_RegionEditDialog> createState() => _RegionEditDialogState();
}

class _RegionEditDialogState extends State<_RegionEditDialog> {
  late RegionKind _kind;
  late final TextEditingController _labelController;
  late final TextEditingController _pageController;
  late final TextEditingController _x0Controller;
  late final TextEditingController _y0Controller;
  late final TextEditingController _x1Controller;
  late final TextEditingController _y1Controller;
  late final TextEditingController _textController;
  String? _validationError;

  @override
  void initState() {
    super.initState();
    final region = widget.region;
    _kind = region.kind;
    _labelController = TextEditingController(text: region.label);
    _pageController = TextEditingController(
      text: (region.pageIndex + 1).toString(),
    );
    _x0Controller = TextEditingController(text: region.bbox.x0.toString());
    _y0Controller = TextEditingController(text: region.bbox.y0.toString());
    _x1Controller = TextEditingController(text: region.bbox.x1.toString());
    _y1Controller = TextEditingController(text: region.bbox.y1.toString());
    _textController = TextEditingController(text: region.text ?? '');
  }

  @override
  void dispose() {
    _labelController.dispose();
    _pageController.dispose();
    _x0Controller.dispose();
    _y0Controller.dispose();
    _x1Controller.dispose();
    _y1Controller.dispose();
    _textController.dispose();
    super.dispose();
  }

  void _save() {
    final page = int.tryParse(_pageController.text);
    final x0 = double.tryParse(_x0Controller.text);
    final y0 = double.tryParse(_y0Controller.text);
    final x1 = double.tryParse(_x1Controller.text);
    final y1 = double.tryParse(_y1Controller.text);
    if (page == null || page < 1) {
      setState(() => _validationError = 'ページ番号は1以上の整数で入力してください');
      return;
    }
    if (x0 == null ||
        y0 == null ||
        x1 == null ||
        y1 == null ||
        x0 < 0 ||
        y0 < 0 ||
        x1 > 1 ||
        y1 > 1 ||
        x0 >= x1 ||
        y0 >= y1) {
      setState(() => _validationError = '座標は0〜1の範囲で、右下が左上より大きくなるように入力してください');
      return;
    }
    if (_labelController.text.trim().isEmpty) {
      setState(() => _validationError = '設問番号を入力してください');
      return;
    }
    final updated = widget.region.rebuild(
      (b) => b
        ..kind = _kind
        ..label = _labelController.text.trim()
        ..pageIndex = page - 1
        ..text = _textController.text.trim().isEmpty
            ? null
            : _textController.text.trim()
        ..bbox.x0 = x0
        ..bbox.y0 = y0
        ..bbox.x1 = x1
        ..bbox.y1 = y1,
    );
    Navigator.of(context).pop(updated);
  }

  @override
  Widget build(BuildContext context) {
    return AlertDialog(
      title: const Text('領域を編集'),
      content: SingleChildScrollView(
        child: Column(
          mainAxisSize: MainAxisSize.min,
          crossAxisAlignment: CrossAxisAlignment.stretch,
          children: [
            DropdownButtonFormField<RegionKind>(
              key: const Key('region-kind-field'),
              initialValue: _kind,
              decoration: const InputDecoration(labelText: '種類'),
              items: [
                for (final kind in RegionKind.values)
                  DropdownMenuItem(
                    value: kind,
                    child: Text(_regionKindLabel(kind)),
                  ),
              ],
              onChanged: (value) {
                if (value != null) setState(() => _kind = value);
              },
            ),
            TextField(
              key: const Key('region-label-field'),
              controller: _labelController,
              decoration: const InputDecoration(labelText: '設問番号'),
            ),
            TextField(
              key: const Key('region-page-field'),
              controller: _pageController,
              keyboardType: TextInputType.number,
              inputFormatters: [FilteringTextInputFormatter.digitsOnly],
              decoration: const InputDecoration(labelText: 'ページ（1始まり）'),
            ),
            Row(
              children: [
                Expanded(
                  child: TextField(
                    key: const Key('region-x0-field'),
                    controller: _x0Controller,
                    decoration: const InputDecoration(labelText: 'x0'),
                  ),
                ),
                const SizedBox(width: 8),
                Expanded(
                  child: TextField(
                    key: const Key('region-y0-field'),
                    controller: _y0Controller,
                    decoration: const InputDecoration(labelText: 'y0'),
                  ),
                ),
              ],
            ),
            Row(
              children: [
                Expanded(
                  child: TextField(
                    key: const Key('region-x1-field'),
                    controller: _x1Controller,
                    decoration: const InputDecoration(labelText: 'x1'),
                  ),
                ),
                const SizedBox(width: 8),
                Expanded(
                  child: TextField(
                    key: const Key('region-y1-field'),
                    controller: _y1Controller,
                    decoration: const InputDecoration(labelText: 'y1'),
                  ),
                ),
              ],
            ),
            TextField(
              key: const Key('region-text-field'),
              controller: _textController,
              maxLines: 3,
              decoration: const InputDecoration(
                labelText: 'テキスト（模範解答/採点基準/配点等）',
              ),
            ),
            if (_validationError != null) ...[
              const SizedBox(height: 8),
              Text(
                _validationError!,
                style: TextStyle(color: Theme.of(context).colorScheme.error),
              ),
            ],
          ],
        ),
      ),
      actions: [
        TextButton(
          onPressed: () => Navigator.of(context).pop(),
          child: const Text('キャンセル'),
        ),
        FilledButton(
          key: const Key('region-save-button'),
          onPressed: _save,
          child: const Text('保存'),
        ),
      ],
    );
  }
}

/// Edits one dependency edge's endpoints/provisions/rationale in place.
class _EdgeEditDialog extends StatefulWidget {
  const _EdgeEditDialog({required this.edge, required this.questionIds});

  final DependencyEdgeModel edge;
  final List<String> questionIds;

  @override
  State<_EdgeEditDialog> createState() => _EdgeEditDialogState();
}

class _EdgeEditDialogState extends State<_EdgeEditDialog> {
  late String _from;
  late String _to;
  late final TextEditingController _rationaleController;
  String? _validationError;

  @override
  void initState() {
    super.initState();
    _from = widget.edge.fromQuestionId;
    _to = widget.edge.toQuestionId;
    _rationaleController = TextEditingController(text: widget.edge.rationale);
  }

  @override
  void dispose() {
    _rationaleController.dispose();
    super.dispose();
  }

  void _save() {
    if (_from == _to) {
      setState(() => _validationError = '依存元と依存先には異なる設問を選んでください');
      return;
    }
    if (_rationaleController.text.trim().isEmpty) {
      setState(() => _validationError = '根拠を入力してください');
      return;
    }
    final updated = widget.edge.rebuild(
      (b) => b
        ..fromQuestionId = _from
        ..toQuestionId = _to
        ..rationale = _rationaleController.text.trim(),
    );
    Navigator.of(context).pop(updated);
  }

  @override
  Widget build(BuildContext context) {
    return AlertDialog(
      title: const Text('依存関係を編集'),
      content: Column(
        mainAxisSize: MainAxisSize.min,
        crossAxisAlignment: CrossAxisAlignment.stretch,
        children: [
          DropdownButtonFormField<String>(
            key: const Key('edge-from-field'),
            initialValue: _from,
            decoration: const InputDecoration(labelText: '依存元（先に処理する設問）'),
            items: [
              for (final id in widget.questionIds)
                DropdownMenuItem(value: id, child: Text(id)),
            ],
            onChanged: (value) {
              if (value != null) setState(() => _from = value);
            },
          ),
          DropdownButtonFormField<String>(
            key: const Key('edge-to-field'),
            initialValue: _to,
            decoration: const InputDecoration(labelText: '依存先（後で処理する設問）'),
            items: [
              for (final id in widget.questionIds)
                DropdownMenuItem(value: id, child: Text(id)),
            ],
            onChanged: (value) {
              if (value != null) setState(() => _to = value);
            },
          ),
          TextField(
            key: const Key('edge-rationale-field'),
            controller: _rationaleController,
            maxLines: 2,
            decoration: const InputDecoration(labelText: '根拠'),
          ),
          if (_validationError != null) ...[
            const SizedBox(height: 8),
            Text(
              _validationError!,
              style: TextStyle(color: Theme.of(context).colorScheme.error),
            ),
          ],
        ],
      ),
      actions: [
        TextButton(
          onPressed: () => Navigator.of(context).pop(),
          child: const Text('キャンセル'),
        ),
        FilledButton(
          key: const Key('edge-save-button'),
          onPressed: _save,
          child: const Text('保存'),
        ),
      ],
    );
  }
}
