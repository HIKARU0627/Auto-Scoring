import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';

import 'package:auto_scoring_app/api/sidecar_api_client.dart';
import 'package:auto_scoring_app/core/action_requirements.dart';
import 'package:auto_scoring_app/core/app_dependencies.dart';
import 'package:auto_scoring_app/core/design/design_tokens.dart';
import 'package:auto_scoring_app/core/sidecar_restart.dart';
import 'package:auto_scoring_app/core/widgets/app_error_banner.dart';
import 'package:auto_scoring_app/core/widgets/disabled_action_reason.dart';

/// 設定画面の「API キー」タブ (Issue #96).
///
/// **The key goes in and never comes back out.** The field is for entering a
/// new one; what the screen shows about an existing key is that it is held
/// and which layer it came from. A value this app will not display cannot
/// leak through a screenshot or a support conversation, and there is nothing
/// a user can do with a key they already own that reading it back here would
/// help with.
///
/// Three things this screen refuses to let stay implicit:
///
/// * **「保存できた」は「使える」ではない。** A typo, a revoked key and a
///   blocked network are indistinguishable until something tries one, so
///   there is a button that tries, and its three outcomes read differently.
/// * **どこから読んだキーなのか。** A developer machine can have a key in
///   `.env.local` *and* one saved here. "There is a key" would not say which
///   is in use, so each row names its source, and so does the provider
///   priority order (which the environment still wins).
/// * **保存しただけでは採点は変わらない。** The sidecar builds its provider
///   chain at startup. Rather than explain that, the screen restarts the
///   sidecar itself (`core/sidecar_restart.dart`).
class ApiKeyTab extends ConsumerStatefulWidget {
  const ApiKeyTab({super.key});

  @override
  ConsumerState<ApiKeyTab> createState() => _ApiKeyTabState();
}

class _ApiKeyTabState extends ConsumerState<ApiKeyTab> {
  late final AppDependencies _dependencies;

  ApiKeySettingsResponse? _settings;
  bool _loading = true;
  String? _error;

  /// Which slot has a request in flight, so only that row's buttons are
  /// disabled -- and `null` when nothing is running.
  String? _busySlotId;

  /// The last 疎通 result per slot. Cleared when its key changes, because a
  /// verdict about the previous key is worse than no verdict.
  final Map<String, VerifyApiKeyResponse> _verified = {};
  final Map<String, TextEditingController> _controllers = {};

  @override
  void initState() {
    super.initState();
    _dependencies = ref.read(appDependenciesProvider);
    _load();
  }

  @override
  void dispose() {
    for (final controller in _controllers.values) {
      controller.dispose();
    }
    super.dispose();
  }

  TextEditingController _controllerFor(String slotId) =>
      _controllers.putIfAbsent(slotId, TextEditingController.new);

  Future<void> _load() async {
    try {
      final settings = await _dependencies.apiKeySettings();
      if (!mounted) return;
      setState(() {
        _settings = settings;
        _error = null;
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

  /// Runs one slot-scoped request, keeping the row's buttons disabled while
  /// it is in flight and turning any failure into the banner.
  Future<void> _run(
    String slotId,
    Future<ApiKeySettingsResponse> Function() request,
  ) async {
    setState(() {
      _busySlotId = slotId;
      _error = null;
    });
    try {
      final settings = await request();
      if (!mounted) return;
      setState(() => _settings = settings);
    } on SidecarApiException catch (error) {
      if (!mounted) return;
      setState(() => _error = error.message);
    } finally {
      if (mounted) setState(() => _busySlotId = null);
    }
  }

  Future<void> _save(String slotId) async {
    final controller = _controllerFor(slotId);
    final value = controller.text.trim();
    if (value.isEmpty) {
      setState(() => _error = 'API キーを入力してください。');
      return;
    }
    // The verdict was about the key being replaced.
    setState(() => _verified.remove(slotId));
    await _run(slotId, () => _dependencies.saveApiKey(slotId, value));
    // Cleared whatever the outcome: leaving a key sitting in a text field is
    // exactly the "on screen for anyone to read" this whole tab avoids, and
    // on a failure the user retypes rather than re-sends something they can
    // no longer see the state of.
    controller.clear();
  }

  Future<void> _delete(String slotId) async {
    setState(() => _verified.remove(slotId));
    await _run(slotId, () => _dependencies.deleteApiKey(slotId));
  }

  Future<void> _verify(String slotId) async {
    setState(() {
      _busySlotId = slotId;
      _error = null;
      _verified.remove(slotId);
    });
    try {
      final outcome = await _dependencies.verifyApiKey(slotId);
      if (!mounted) return;
      setState(() => _verified[slotId] = outcome);
    } on SidecarApiException catch (error) {
      if (!mounted) return;
      setState(() => _error = error.message);
    } finally {
      if (mounted) setState(() => _busySlotId = null);
    }
  }

  @override
  Widget build(BuildContext context) {
    if (_loading) return const Center(child: CircularProgressIndicator());
    final settings = _settings;
    if (settings == null) {
      return Padding(
        padding: AppSpacing.page,
        child: AppErrorBanner(
          message: _error ?? '設定を読み込めませんでした。',
          onRetry: _load,
        ),
      );
    }
    return ListView(
      padding: AppSpacing.page,
      children: [
        const Text('AI 採点は外部のサービスに問い合わせます。その利用料は、ここに入れたキーの持ち主に請求されます。'),
        const SizedBox(height: AppSpacing.xs),
        const Text('キーはこの PC の資格情報ストアに保存し、画面には二度と表示しません。'),
        if (settings.storeUnavailableReason != null) ...[
          const SizedBox(height: AppSpacing.md),
          AppErrorBanner(
            key: const Key('settings-api-key-store-unavailable'),
            message:
                '${settings.storeUnavailableReason}'
                ' キーの保存はできません。環境変数で渡す運用は今までどおり使えます。',
            retryable: false,
          ),
        ],
        if (_error != null) ...[
          const SizedBox(height: AppSpacing.md),
          AppErrorBanner(
            messageKey: const Key('settings-api-key-error'),
            message: _error!,
            retryable: false,
          ),
        ],
        if (settings.restartRequired) ...[
          const SizedBox(height: AppSpacing.md),
          _RestartNotice(onRestart: ref.watch(restartSidecarProvider)),
        ],
        const SizedBox(height: AppSpacing.lg),
        _TransportOrder(settings: settings),
        const SizedBox(height: AppSpacing.lg),
        for (final slot in settings.keys) ...[
          _SlotCard(
            slot: slot,
            controller: _controllerFor(slot.id),
            busy: _busySlotId != null,
            canSave: settings.storeUnavailableReason == null,
            verification: _verified[slot.id],
            onSave: () => _save(slot.id),
            onDelete: () => _delete(slot.id),
            onVerify: () => _verify(slot.id),
          ),
          const SizedBox(height: AppSpacing.md),
        ],
      ],
    );
  }
}

/// Which provider order this installation actually uses, and who decided it.
///
/// A distributed copy defaults to OpenRouter; a development machine keeps
/// the Vertex-first order from its environment (Issue #96's decision). The
/// two look nothing alike, so the screen says which one it is looking at
/// rather than implying there is only one.
class _TransportOrder extends StatelessWidget {
  const _TransportOrder({required this.settings});

  final ApiKeySettingsResponse settings;

  @override
  Widget build(BuildContext context) {
    final order = settings.transportOrder.isEmpty
        ? '（まだありません）'
        : settings.transportOrder;
    return Card(
      child: Padding(
        padding: AppSpacing.card,
        child: Column(
          crossAxisAlignment: CrossAxisAlignment.start,
          children: [
            Text('使う順番', style: Theme.of(context).textTheme.titleMedium),
            const SizedBox(height: AppSpacing.xs),
            Text(order, key: const Key('settings-api-key-transport-order')),
            const SizedBox(height: AppSpacing.xs),
            Text(switch (settings.transportSource) {
              ConfigurationSource.environment =>
                'この PC の環境変数 AUTO_SCORING_AI_GRADING_TRANSPORT で決まっています。'
                    'ここでキーを足しても、この順番は変わりません。',
              ConfigurationSource.builtinDefault => '保存されているキーから決めています。',
              _ => 'キーも環境変数もまだありません。',
            }, style: Theme.of(context).textTheme.bodySmall),
          ],
        ),
      ),
    );
  }
}

/// "Saved" and "in use" are different states, and this is the gap between
/// them -- with the button that closes it.
class _RestartNotice extends StatelessWidget {
  const _RestartNotice({required this.onRestart});

  final RestartSidecar? onRestart;

  @override
  Widget build(BuildContext context) {
    return Card(
      child: Padding(
        padding: AppSpacing.card,
        child: Column(
          crossAxisAlignment: CrossAxisAlignment.start,
          children: [
            const Text(
              key: Key('settings-api-key-restart-required'),
              '保存した内容は、まだ採点には使われていません。'
              '反映するにはサイドカーを再起動します。',
            ),
            const SizedBox(height: AppSpacing.sm),
            if (onRestart == null)
              const Text('この起動方法では画面から再起動できません。アプリを起動し直してください。')
            else
              FilledButton.icon(
                key: const Key('settings-api-key-restart'),
                // Not awaited: `start()` returns only once the sidecar is
                // ready or has failed, and the startup overlay is what
                // renders that wait -- this screen is replaced while it runs.
                onPressed: () => onRestart!(),
                icon: const Icon(Icons.restart_alt),
                label: const Text('いま再起動して反映する'),
              ),
          ],
        ),
      ),
    );
  }
}

class _SlotCard extends StatelessWidget {
  const _SlotCard({
    required this.slot,
    required this.controller,
    required this.busy,
    required this.canSave,
    required this.verification,
    required this.onSave,
    required this.onDelete,
    required this.onVerify,
  });

  final ApiKeyStatusModel slot;
  final TextEditingController controller;
  final bool busy;
  final bool canSave;
  final VerifyApiKeyResponse? verification;
  final VoidCallback onSave;
  final VoidCallback onDelete;
  final VoidCallback onVerify;

  @override
  Widget build(BuildContext context) {
    final theme = Theme.of(context);
    // 無効にしている条件と、無効の理由は同じ1つの計算から出す (Issue #88)。
    // 文言は `core/action_requirements.dart` にしか無い。
    final save = apiKeySaveRequirements(
      busy: busy,
      credentialStoreAvailable: canSave,
    );
    final verify = apiKeyVerifyRequirements(
      busy: busy,
      configured: slot.configured,
    );
    return Card(
      child: Padding(
        padding: AppSpacing.card,
        child: Column(
          crossAxisAlignment: CrossAxisAlignment.start,
          children: [
            Text(slot.label, style: theme.textTheme.titleMedium),
            const SizedBox(height: AppSpacing.xs),
            Text(key: Key('settings-api-key-status-${slot.id}'), switch ((
              slot.configured,
              slot.keySource,
            )) {
              (true, ConfigurationSource.credentialStore) =>
                '保存済み（この PC の資格情報ストア）',
              (true, _) => '環境変数 ${slot.keyVariable} から読み込み済み',
              _ => '未設定',
            }),
            const SizedBox(height: AppSpacing.xs),
            Text(
              'モデル: ${slot.model}'
              '${slot.modelSource == ConfigurationSource.environment ? '（環境変数）' : '（既定）'}',
              style: theme.textTheme.bodySmall,
            ),
            const SizedBox(height: AppSpacing.xs),
            SelectableText(
              'キーの発行: ${slot.consoleUrl}',
              style: theme.textTheme.bodySmall,
            ),
            const SizedBox(height: AppSpacing.md),
            TextField(
              key: Key('settings-api-key-field-${slot.id}'),
              controller: controller,
              // Entering a credential in front of whoever is in the room --
              // and, in this project, in front of a screenshot in an Issue.
              obscureText: true,
              autocorrect: false,
              enableSuggestions: false,
              decoration: InputDecoration(
                labelText: slot.configured ? '新しいキーに置き換える' : 'API キー',
                border: const OutlineInputBorder(),
                // 保存できない理由はここには書かない。ボタンの横に
                // `DisabledActionReason` が出すので、2か所に同じことを書くと
                // 片方だけ古くなる (Issue #88)。
                helperText: canSave ? '保存すると、この欄は空になります。保存したキーは表示できません。' : null,
              ),
            ),
            const SizedBox(height: AppSpacing.md),
            Wrap(
              spacing: AppSpacing.sm,
              runSpacing: AppSpacing.sm,
              children: [
                FilledButton.icon(
                  key: Key('settings-api-key-save-${slot.id}'),
                  onPressed: save.isEmpty ? onSave : null,
                  icon: const Icon(Icons.save),
                  label: const Text('保存する'),
                ),
                OutlinedButton.icon(
                  key: Key('settings-api-key-verify-${slot.id}'),
                  onPressed: verify.isEmpty ? onVerify : null,
                  icon: const Icon(Icons.network_check),
                  label: const Text('疎通を確認する'),
                ),
                if (slot.configured &&
                    slot.keySource == ConfigurationSource.credentialStore)
                  TextButton.icon(
                    key: Key('settings-api-key-delete-${slot.id}'),
                    onPressed: busy ? null : onDelete,
                    icon: const Icon(Icons.delete_outline),
                    label: const Text('保存したキーを削除する'),
                  ),
              ],
            ),
            // 2つ並べるのは、押せない理由が別々だからである -- 保存は資格情報
            // ストア、疎通はキーの有無。どちらか片方だけ無効な状態が普通に
            // 起きるので、1本にまとめると無効でないボタンの理由まで出る。
            DisabledActionReason(requirements: save),
            DisabledActionReason(requirements: verify),
            if (verification != null) ...[
              const SizedBox(height: AppSpacing.md),
              _VerificationResult(slotId: slot.id, outcome: verification!),
            ],
          ],
        ),
      ),
    );
  }
}

/// The 疎通 verdict. Each outcome gets its own icon, colour **and wording**
/// -- Issue #96 requires them to be distinguishable, and colour alone is not
/// a distinction everyone can see (`AGENTS.md`: non-colour-dependent states).
class _VerificationResult extends StatelessWidget {
  const _VerificationResult({required this.slotId, required this.outcome});

  final String slotId;
  final VerifyApiKeyResponse outcome;

  @override
  Widget build(BuildContext context) {
    final theme = Theme.of(context);
    final (icon, colour) = switch (outcome.result) {
      'ok' => (Icons.check_circle_outline, theme.colorScheme.primary),
      'no_credit' => (
        Icons.account_balance_wallet_outlined,
        theme.colorScheme.error,
      ),
      'unauthorized' => (Icons.key_off_outlined, theme.colorScheme.error),
      'unreachable' => (Icons.wifi_off_outlined, theme.colorScheme.error),
      _ => (Icons.error_outline, theme.colorScheme.error),
    };
    return Row(
      crossAxisAlignment: CrossAxisAlignment.start,
      children: [
        Icon(icon, color: colour),
        const SizedBox(width: AppSpacing.sm),
        Expanded(
          child: Text(
            key: Key('settings-api-key-verification-$slotId'),
            outcome.detail,
            style: theme.textTheme.bodyMedium?.copyWith(color: colour),
          ),
        ),
      ],
    );
  }
}
