// GENERATED CODE - DO NOT MODIFY BY HAND

part of 'criterion_result_response.dart';

// **************************************************************************
// BuiltValueGenerator
// **************************************************************************

class _$CriterionResultResponse extends CriterionResultResponse {
  @override
  final num? confidence;
  @override
  final String criterionId;
  @override
  final String outcome;

  factory _$CriterionResultResponse(
          [void Function(CriterionResultResponseBuilder)? updates]) =>
      (CriterionResultResponseBuilder()..update(updates))._build();

  _$CriterionResultResponse._(
      {this.confidence, required this.criterionId, required this.outcome})
      : super._();
  @override
  CriterionResultResponse rebuild(
          void Function(CriterionResultResponseBuilder) updates) =>
      (toBuilder()..update(updates)).build();

  @override
  CriterionResultResponseBuilder toBuilder() =>
      CriterionResultResponseBuilder()..replace(this);

  @override
  bool operator ==(Object other) {
    if (identical(other, this)) return true;
    return other is CriterionResultResponse &&
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
    return (newBuiltValueToStringHelper(r'CriterionResultResponse')
          ..add('confidence', confidence)
          ..add('criterionId', criterionId)
          ..add('outcome', outcome))
        .toString();
  }
}

class CriterionResultResponseBuilder
    implements
        Builder<CriterionResultResponse, CriterionResultResponseBuilder> {
  _$CriterionResultResponse? _$v;

  num? _confidence;
  num? get confidence => _$this._confidence;
  set confidence(num? confidence) => _$this._confidence = confidence;

  String? _criterionId;
  String? get criterionId => _$this._criterionId;
  set criterionId(String? criterionId) => _$this._criterionId = criterionId;

  String? _outcome;
  String? get outcome => _$this._outcome;
  set outcome(String? outcome) => _$this._outcome = outcome;

  CriterionResultResponseBuilder() {
    CriterionResultResponse._defaults(this);
  }

  CriterionResultResponseBuilder get _$this {
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
  void replace(CriterionResultResponse other) {
    _$v = other as _$CriterionResultResponse;
  }

  @override
  void update(void Function(CriterionResultResponseBuilder)? updates) {
    if (updates != null) updates(this);
  }

  @override
  CriterionResultResponse build() => _build();

  _$CriterionResultResponse _build() {
    final _$result = _$v ??
        _$CriterionResultResponse._(
          confidence: confidence,
          criterionId: BuiltValueNullFieldError.checkNotNull(
              criterionId, r'CriterionResultResponse', 'criterionId'),
          outcome: BuiltValueNullFieldError.checkNotNull(
              outcome, r'CriterionResultResponse', 'outcome'),
        );
    replace(_$result);
    return _$result;
  }
}

// ignore_for_file: deprecated_member_use_from_same_package,type=lint
