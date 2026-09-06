// GENERATED CODE - DO NOT MODIFY BY HAND

part of 'criterion_outcome_request.dart';

// **************************************************************************
// BuiltValueGenerator
// **************************************************************************

class _$CriterionOutcomeRequest extends CriterionOutcomeRequest {
  @override
  final num? confidence;
  @override
  final String criterionId;
  @override
  final String outcome;

  factory _$CriterionOutcomeRequest(
          [void Function(CriterionOutcomeRequestBuilder)? updates]) =>
      (CriterionOutcomeRequestBuilder()..update(updates))._build();

  _$CriterionOutcomeRequest._(
      {this.confidence, required this.criterionId, required this.outcome})
      : super._();
  @override
  CriterionOutcomeRequest rebuild(
          void Function(CriterionOutcomeRequestBuilder) updates) =>
      (toBuilder()..update(updates)).build();

  @override
  CriterionOutcomeRequestBuilder toBuilder() =>
      CriterionOutcomeRequestBuilder()..replace(this);

  @override
  bool operator ==(Object other) {
    if (identical(other, this)) return true;
    return other is CriterionOutcomeRequest &&
        confidence == other.confidence &&
        criterionId == other.criterionId &&
        outcome == other.outcome;
  }

  @override
  int get hashCode {
    var _$hash = 0;
    _$hash = $jc(_$hash, confidence.hashCode);
    _$hash = $jc(_$hash, criterionId.hashCode);
    _$hash = $jc(_$hash, outcome.hashCode);
    _$hash = $jf(_$hash);
    return _$hash;
  }

  @override
  String toString() {
    return (newBuiltValueToStringHelper(r'CriterionOutcomeRequest')
          ..add('confidence', confidence)
          ..add('criterionId', criterionId)
          ..add('outcome', outcome))
        .toString();
  }
}

class CriterionOutcomeRequestBuilder
    implements
        Builder<CriterionOutcomeRequest, CriterionOutcomeRequestBuilder> {
  _$CriterionOutcomeRequest? _$v;

  num? _confidence;
  num? get confidence => _$this._confidence;
  set confidence(num? confidence) => _$this._confidence = confidence;

  String? _criterionId;
  String? get criterionId => _$this._criterionId;
  set criterionId(String? criterionId) => _$this._criterionId = criterionId;

  String? _outcome;
  String? get outcome => _$this._outcome;
  set outcome(String? outcome) => _$this._outcome = outcome;

  CriterionOutcomeRequestBuilder() {
    CriterionOutcomeRequest._defaults(this);
  }

  CriterionOutcomeRequestBuilder get _$this {
    final $v = _$v;
    if ($v != null) {
      _confidence = $v.confidence;
      _criterionId = $v.criterionId;
      _outcome = $v.outcome;
      _$v = null;
    }
    return this;
  }

  @override
  void replace(CriterionOutcomeRequest other) {
    _$v = other as _$CriterionOutcomeRequest;
  }

  @override
  void update(void Function(CriterionOutcomeRequestBuilder)? updates) {
    if (updates != null) updates(this);
  }

  @override
  CriterionOutcomeRequest build() => _build();

  _$CriterionOutcomeRequest _build() {
    final _$result = _$v ??
        _$CriterionOutcomeRequest._(
          confidence: confidence,
          criterionId: BuiltValueNullFieldError.checkNotNull(
              criterionId, r'CriterionOutcomeRequest', 'criterionId'),
          outcome: BuiltValueNullFieldError.checkNotNull(
              outcome, r'CriterionOutcomeRequest', 'outcome'),
        );
    replace(_$result);
    return _$result;
  }
}

// ignore_for_file: deprecated_member_use_from_same_package,type=lint
