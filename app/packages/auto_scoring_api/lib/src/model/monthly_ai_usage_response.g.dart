// GENERATED CODE - DO NOT MODIFY BY HAND

part of 'monthly_ai_usage_response.dart';

// **************************************************************************
// BuiltValueGenerator
// **************************************************************************

class _$MonthlyAiUsageResponse extends MonthlyAiUsageResponse {
  @override
  final num? estimatedCost;
  @override
  final int? inputTokens;
  @override
  final String month;
  @override
  final int? outputTokens;
  @override
  final num? tokenUnitCost;
  @override
  final UsageAvailability usageAvailability;

  factory _$MonthlyAiUsageResponse(
          [void Function(MonthlyAiUsageResponseBuilder)? updates]) =>
      (MonthlyAiUsageResponseBuilder()..update(updates))._build();

  _$MonthlyAiUsageResponse._(
      {this.estimatedCost,
      this.inputTokens,
      required this.month,
      this.outputTokens,
      this.tokenUnitCost,
      required this.usageAvailability})
      : super._();
  @override
  MonthlyAiUsageResponse rebuild(
          void Function(MonthlyAiUsageResponseBuilder) updates) =>
      (toBuilder()..update(updates)).build();

  @override
  MonthlyAiUsageResponseBuilder toBuilder() =>
      MonthlyAiUsageResponseBuilder()..replace(this);

  @override
  bool operator ==(Object other) {
    if (identical(other, this)) return true;
    return other is MonthlyAiUsageResponse &&
        estimatedCost == other.estimatedCost &&
        inputTokens == other.inputTokens &&
        month == other.month &&
        outputTokens == other.outputTokens &&
        tokenUnitCost == other.tokenUnitCost &&
        usageAvailability == other.usageAvailability;
  }

  @override
  int get hashCode {
    var _$hash = 0;
    _$hash = $jc(_$hash, estimatedCost.hashCode);
    _$hash = $jc(_$hash, inputTokens.hashCode);
    _$hash = $jc(_$hash, month.hashCode);
    _$hash = $jc(_$hash, outputTokens.hashCode);
    _$hash = $jc(_$hash, tokenUnitCost.hashCode);
    _$hash = $jc(_$hash, usageAvailability.hashCode);
    _$hash = $jf(_$hash);
    return _$hash;
  }

  @override
  String toString() {
    return (newBuiltValueToStringHelper(r'MonthlyAiUsageResponse')
          ..add('estimatedCost', estimatedCost)
          ..add('inputTokens', inputTokens)
          ..add('month', month)
          ..add('outputTokens', outputTokens)
          ..add('tokenUnitCost', tokenUnitCost)
          ..add('usageAvailability', usageAvailability))
        .toString();
  }
}

class MonthlyAiUsageResponseBuilder
    implements Builder<MonthlyAiUsageResponse, MonthlyAiUsageResponseBuilder> {
  _$MonthlyAiUsageResponse? _$v;

  num? _estimatedCost;
  num? get estimatedCost => _$this._estimatedCost;
  set estimatedCost(num? estimatedCost) =>
      _$this._estimatedCost = estimatedCost;

  int? _inputTokens;
  int? get inputTokens => _$this._inputTokens;
  set inputTokens(int? inputTokens) => _$this._inputTokens = inputTokens;

  String? _month;
  String? get month => _$this._month;
  set month(String? month) => _$this._month = month;

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

  MonthlyAiUsageResponseBuilder() {
    MonthlyAiUsageResponse._defaults(this);
  }

  MonthlyAiUsageResponseBuilder get _$this {
    final $v = _$v;
    if ($v != null) {
      _estimatedCost = $v.estimatedCost;
      _inputTokens = $v.inputTokens;
      _month = $v.month;
      _outputTokens = $v.outputTokens;
      _tokenUnitCost = $v.tokenUnitCost;
      _usageAvailability = $v.usageAvailability;
      _$v = null;
    }
    return this;
  }

  @override
  void replace(MonthlyAiUsageResponse other) {
    _$v = other as _$MonthlyAiUsageResponse;
  }

  @override
  void update(void Function(MonthlyAiUsageResponseBuilder)? updates) {
    if (updates != null) updates(this);
  }

  @override
  MonthlyAiUsageResponse build() => _build();

  _$MonthlyAiUsageResponse _build() {
    final _$result = _$v ??
        _$MonthlyAiUsageResponse._(
          estimatedCost: estimatedCost,
          inputTokens: inputTokens,
          month: BuiltValueNullFieldError.checkNotNull(
              month, r'MonthlyAiUsageResponse', 'month'),
          outputTokens: outputTokens,
          tokenUnitCost: tokenUnitCost,
          usageAvailability: BuiltValueNullFieldError.checkNotNull(
              usageAvailability,
              r'MonthlyAiUsageResponse',
              'usageAvailability'),
        );
    replace(_$result);
    return _$result;
  }
}

// ignore_for_file: deprecated_member_use_from_same_package,type=lint
