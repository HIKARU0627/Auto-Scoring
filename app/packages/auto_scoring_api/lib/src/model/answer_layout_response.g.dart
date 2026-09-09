// GENERATED CODE - DO NOT MODIFY BY HAND

part of 'answer_layout_response.dart';

// **************************************************************************
// BuiltValueGenerator
// **************************************************************************

class _$AnswerLayoutResponse extends AnswerLayoutResponse {
  @override
  final bool detectionAvailable;
  @override
  final String? detectionUnavailableReason;
  @override
  final int? droppedRegionCount;
  @override
  final int? pageCount;
  @override
  final String testId;

  factory _$AnswerLayoutResponse(
          [void Function(AnswerLayoutResponseBuilder)? updates]) =>
      (AnswerLayoutResponseBuilder()..update(updates))._build();

  _$AnswerLayoutResponse._(
      {required this.detectionAvailable,
      this.detectionUnavailableReason,
      this.droppedRegionCount,
      this.pageCount,
      required this.testId})
      : super._();
  @override
  AnswerLayoutResponse rebuild(
          void Function(AnswerLayoutResponseBuilder) updates) =>
      (toBuilder()..update(updates)).build();

  @override
  AnswerLayoutResponseBuilder toBuilder() =>
      AnswerLayoutResponseBuilder()..replace(this);

  @override
  bool operator ==(Object other) {
    if (identical(other, this)) return true;
    return other is AnswerLayoutResponse &&
        detectionAvailable == other.detectionAvailable &&
        detectionUnavailableReason == other.detectionUnavailableReason &&
        droppedRegionCount == other.droppedRegionCount &&
        pageCount == other.pageCount &&
        testId == other.testId;
  }

  @override
  int get hashCode {
    var _$hash = 0;
    _$hash = $jc(_$hash, detectionAvailable.hashCode);
    _$hash = $jc(_$hash, detectionUnavailableReason.hashCode);
    _$hash = $jc(_$hash, droppedRegionCount.hashCode);
    _$hash = $jc(_$hash, pageCount.hashCode);
    _$hash = $jc(_$hash, testId.hashCode);
    _$hash = $jf(_$hash);
    return _$hash;
  }

  @override
  String toString() {
    return (newBuiltValueToStringHelper(r'AnswerLayoutResponse')
          ..add('detectionAvailable', detectionAvailable)
          ..add('detectionUnavailableReason', detectionUnavailableReason)
          ..add('droppedRegionCount', droppedRegionCount)
          ..add('pageCount', pageCount)
          ..add('testId', testId))
        .toString();
  }
}

class AnswerLayoutResponseBuilder
    implements Builder<AnswerLayoutResponse, AnswerLayoutResponseBuilder> {
  _$AnswerLayoutResponse? _$v;

  bool? _detectionAvailable;
  bool? get detectionAvailable => _$this._detectionAvailable;
  set detectionAvailable(bool? detectionAvailable) =>
      _$this._detectionAvailable = detectionAvailable;

  String? _detectionUnavailableReason;
  String? get detectionUnavailableReason => _$this._detectionUnavailableReason;
  set detectionUnavailableReason(String? detectionUnavailableReason) =>
      _$this._detectionUnavailableReason = detectionUnavailableReason;

  int? _droppedRegionCount;
  int? get droppedRegionCount => _$this._droppedRegionCount;
  set droppedRegionCount(int? droppedRegionCount) =>
      _$this._droppedRegionCount = droppedRegionCount;

  int? _pageCount;
  int? get pageCount => _$this._pageCount;
  set pageCount(int? pageCount) => _$this._pageCount = pageCount;

  String? _testId;
  String? get testId => _$this._testId;
  set testId(String? testId) => _$this._testId = testId;

  AnswerLayoutResponseBuilder() {
    AnswerLayoutResponse._defaults(this);
  }

  AnswerLayoutResponseBuilder get _$this {
    final $v = _$v;
    if ($v != null) {
      _detectionAvailable = $v.detectionAvailable;
      _detectionUnavailableReason = $v.detectionUnavailableReason;
      _droppedRegionCount = $v.droppedRegionCount;
      _pageCount = $v.pageCount;
      _testId = $v.testId;
      _$v = null;
    }
    return this;
  }

  @override
  void replace(AnswerLayoutResponse other) {
    _$v = other as _$AnswerLayoutResponse;
  }

  @override
  void update(void Function(AnswerLayoutResponseBuilder)? updates) {
    if (updates != null) updates(this);
  }

  @override
  AnswerLayoutResponse build() => _build();

  _$AnswerLayoutResponse _build() {
    final _$result = _$v ??
        _$AnswerLayoutResponse._(
          detectionAvailable: BuiltValueNullFieldError.checkNotNull(
              detectionAvailable,
              r'AnswerLayoutResponse',
              'detectionAvailable'),
          detectionUnavailableReason: detectionUnavailableReason,
          droppedRegionCount: droppedRegionCount,
          pageCount: pageCount,
          testId: BuiltValueNullFieldError.checkNotNull(
              testId, r'AnswerLayoutResponse', 'testId'),
        );
    replace(_$result);
    return _$result;
  }
}

// ignore_for_file: deprecated_member_use_from_same_package,type=lint
