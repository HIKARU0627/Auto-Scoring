// GENERATED CODE - DO NOT MODIFY BY HAND

part of 'attribution_proposal_response.dart';

// **************************************************************************
// BuiltValueGenerator
// **************************************************************************

class _$AttributionProposalResponse extends AttributionProposalResponse {
  @override
  final num confidence;
  @override
  final String? testId;

  factory _$AttributionProposalResponse(
          [void Function(AttributionProposalResponseBuilder)? updates]) =>
      (AttributionProposalResponseBuilder()..update(updates))._build();

  _$AttributionProposalResponse._({required this.confidence, this.testId})
      : super._();
  @override
  AttributionProposalResponse rebuild(
          void Function(AttributionProposalResponseBuilder) updates) =>
      (toBuilder()..update(updates)).build();

  @override
  AttributionProposalResponseBuilder toBuilder() =>
      AttributionProposalResponseBuilder()..replace(this);

  @override
  bool operator ==(Object other) {
    if (identical(other, this)) return true;
    return other is AttributionProposalResponse &&
        confidence == other.confidence &&
        testId == other.testId;
  }

  @override
  int get hashCode {
    var _$hash = 0;
    _$hash = $jc(_$hash, confidence.hashCode);
    _$hash = $jc(_$hash, testId.hashCode);
    _$hash = $jf(_$hash);
    return _$hash;
  }

  @override
  String toString() {
    return (newBuiltValueToStringHelper(r'AttributionProposalResponse')
          ..add('confidence', confidence)
          ..add('testId', testId))
        .toString();
  }
}

class AttributionProposalResponseBuilder
    implements
        Builder<AttributionProposalResponse,
            AttributionProposalResponseBuilder> {
  _$AttributionProposalResponse? _$v;

  num? _confidence;
  num? get confidence => _$this._confidence;
  set confidence(num? confidence) => _$this._confidence = confidence;

  String? _testId;
  String? get testId => _$this._testId;
  set testId(String? testId) => _$this._testId = testId;

  AttributionProposalResponseBuilder() {
    AttributionProposalResponse._defaults(this);
  }

  AttributionProposalResponseBuilder get _$this {
    final $v = _$v;
    if ($v != null) {
      _confidence = $v.confidence;
      _testId = $v.testId;
      _$v = null;
    }
    return this;
  }

  @override
  void replace(AttributionProposalResponse other) {
    _$v = other as _$AttributionProposalResponse;
  }

  @override
  void update(void Function(AttributionProposalResponseBuilder)? updates) {
    if (updates != null) updates(this);
  }

  @override
  AttributionProposalResponse build() => _build();

  _$AttributionProposalResponse _build() {
    final _$result = _$v ??
        _$AttributionProposalResponse._(
          confidence: BuiltValueNullFieldError.checkNotNull(
              confidence, r'AttributionProposalResponse', 'confidence'),
          testId: testId,
        );
    replace(_$result);
    return _$result;
  }
}

// ignore_for_file: deprecated_member_use_from_same_package,type=lint
