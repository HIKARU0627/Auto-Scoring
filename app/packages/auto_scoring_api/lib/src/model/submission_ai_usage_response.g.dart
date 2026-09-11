// GENERATED CODE - DO NOT MODIFY BY HAND

part of 'submission_ai_usage_response.dart';

// **************************************************************************
// BuiltValueGenerator
// **************************************************************************

class _$SubmissionAiUsageResponse extends SubmissionAiUsageResponse {
  @override
  final num? estimatedCost;
  @override
  final int? inputTokens;
  @override
  final int? outputTokens;
  @override
  final num? tokenUnitCost;
  @override
  final UsageAvailability usageAvailability;

  factory _$SubmissionAiUsageResponse(
          [void Function(SubmissionAiUsageResponseBuilder)? updates]) =>
      (SubmissionAiUsageResponseBuilder()..update(updates))._build();

  _$SubmissionAiUsageResponse._(
      {this.estimatedCost,
      this.inputTokens,
      this.outputTokens,
      this.tokenUnitCost,
      required this.usageAvailability})
      : super._();
  @override
  SubmissionAiUsageResponse rebuild(
          void Function(SubmissionAiUsageResponseBuilder) updates) =>
      (toBuilder()..update(updates)).build();

  @override
  SubmissionAiUsageResponseBuilder toBuilder() =>
      SubmissionAiUsageResponseBuilder()..replace(this);

  @override
  bool operator ==(Object other) {
    if (identical(other, this)) return true;
    return other is SubmissionAiUsageResponse &&
        estimatedCost == other.estimatedCost &&
        inputTokens == other.inputTokens &&
        outputTokens == other.outputTokens &&
        tokenUnitCost == other.tokenUnitCost &&
        usageAvailability == other.usageAvailability;
  }

  @override
  int get hashCode {
    var _$hash = 0;
    _$hash = $jc(_$hash, estimatedCost.hashCode);
    _$hash = $jc(_$hash, inputTokens.hashCode);
    _$hash = $jc(_$hash, outputTokens.hashCode);
    _$hash = $jc(_$hash, tokenUnitCost.hashCode);
    _$hash = $jc(_$hash, usageAvailability.hashCode);
    _$hash = $jf(_$hash);
    return _$hash;
  }

  @override
  String toString() {
    return (newBuiltValueToStringHelper(r'SubmissionAiUsageResponse')
          ..add('estimatedCost', estimatedCost)
          ..add('inputTokens', inputTokens)
          ..add('outputTokens', outputTokens)
          ..add('tokenUnitCost', tokenUnitCost)
          ..add('usageAvailability', usageAvailability))
        .toString();
  }
}

class SubmissionAiUsageResponseBuilder
    implements
        Builder<SubmissionAiUsageResponse, SubmissionAiUsageResponseBuilder> {
  _$SubmissionAiUsageResponse? _$v;

  num? _estimatedCost;
  num? get estimatedCost => _$this._estimatedCost;
  set estimatedCost(num? estimatedCost) =>
      _$this._estimatedCost = estimatedCost;

  int? _inputTokens;
  int? get inputTokens => _$this._inputTokens;
  set inputTokens(int? inputTokens) => _$this._inputTokens = inputTokens;

  int? _outputTokens;
  int? get outputTokens => _$this._outputTokens;
  set outputTokens(int? outputTokens) => _$this._outputTokens = outputTokens;

  num? _tokenUnitCost;
  num? get tokenUnitCost => _$this._tokenUnitCost;
  set tokenUnitCost(num? tokenUnitCost) =>
      _$this._tokenUnitCost = tokenUnitCost;

  UsageAvailability? _usageAvailability;
  UsageAvailability? get usageAvailability => _$this._usageAvailability;
  set usageAvailability(UsageAvailability? usageAvailability) =>
      _$this._usageAvailability = usageAvailability;

  SubmissionAiUsageResponseBuilder() {
    SubmissionAiUsageResponse._defaults(this);
  }

  SubmissionAiUsageResponseBuilder get _$this {
    final $v = _$v;
    if ($v != null) {
      _estimatedCost = $v.estimatedCost;
      _inputTokens = $v.inputTokens;
      _outputTokens = $v.outputTokens;
      _tokenUnitCost = $v.tokenUnitCost;
      _usageAvailability = $v.usageAvailability;
      _$v = null;
    }
    return this;
  }

  @override
  void replace(SubmissionAiUsageResponse other) {
    _$v = other as _$SubmissionAiUsageResponse;
  }

  @override
  void update(void Function(SubmissionAiUsageResponseBuilder)? updates) {
    if (updates != null) updates(this);
  }

  @override
  SubmissionAiUsageResponse build() => _build();

  _$SubmissionAiUsageResponse _build() {
    final _$result = _$v ??
        _$SubmissionAiUsageResponse._(
          estimatedCost: estimatedCost,
          inputTokens: inputTokens,
          outputTokens: outputTokens,
          tokenUnitCost: tokenUnitCost,
          usageAvailability: BuiltValueNullFieldError.checkNotNull(
              usageAvailability,
              r'SubmissionAiUsageResponse',
              'usageAvailability'),
        );
    replace(_$result);
    return _$result;
  }
}

// ignore_for_file: deprecated_member_use_from_same_package,type=lint
