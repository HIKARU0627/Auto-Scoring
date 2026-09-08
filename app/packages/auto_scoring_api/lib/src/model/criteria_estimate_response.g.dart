// GENERATED CODE - DO NOT MODIFY BY HAND

part of 'criteria_estimate_response.dart';

// **************************************************************************
// BuiltValueGenerator
// **************************************************************************

class _$CriteriaEstimateResponse extends CriteriaEstimateResponse {
  @override
  final num? estimatedCost;
  @override
  final int maxPages;
  @override
  final int pageCount;
  @override
  final num? unitCost;

  factory _$CriteriaEstimateResponse(
          [void Function(CriteriaEstimateResponseBuilder)? updates]) =>
      (CriteriaEstimateResponseBuilder()..update(updates))._build();

  _$CriteriaEstimateResponse._(
      {this.estimatedCost,
      required this.maxPages,
      required this.pageCount,
      this.unitCost})
      : super._();
  @override
  CriteriaEstimateResponse rebuild(
          void Function(CriteriaEstimateResponseBuilder) updates) =>
      (toBuilder()..update(updates)).build();

  @override
  CriteriaEstimateResponseBuilder toBuilder() =>
      CriteriaEstimateResponseBuilder()..replace(this);

  @override
  bool operator ==(Object other) {
    if (identical(other, this)) return true;
    return other is CriteriaEstimateResponse &&
        estimatedCost == other.estimatedCost &&
        maxPages == other.maxPages &&
        pageCount == other.pageCount &&
        unitCost == other.unitCost;
  }

  @override
  int get hashCode {
    var _$hash = 0;
    _$hash = $jc(_$hash, estimatedCost.hashCode);
    _$hash = $jc(_$hash, maxPages.hashCode);
    _$hash = $jc(_$hash, pageCount.hashCode);
    _$hash = $jc(_$hash, unitCost.hashCode);
    _$hash = $jf(_$hash);
    return _$hash;
  }

  @override
  String toString() {
    return (newBuiltValueToStringHelper(r'CriteriaEstimateResponse')
          ..add('estimatedCost', estimatedCost)
          ..add('maxPages', maxPages)
          ..add('pageCount', pageCount)
          ..add('unitCost', unitCost))
        .toString();
  }
}

class CriteriaEstimateResponseBuilder
    implements
        Builder<CriteriaEstimateResponse, CriteriaEstimateResponseBuilder> {
  _$CriteriaEstimateResponse? _$v;

  num? _estimatedCost;
  num? get estimatedCost => _$this._estimatedCost;
  set estimatedCost(num? estimatedCost) =>
      _$this._estimatedCost = estimatedCost;

  int? _maxPages;
  int? get maxPages => _$this._maxPages;
  set maxPages(int? maxPages) => _$this._maxPages = maxPages;

  int? _pageCount;
  int? get pageCount => _$this._pageCount;
  set pageCount(int? pageCount) => _$this._pageCount = pageCount;

  num? _unitCost;
  num? get unitCost => _$this._unitCost;
  set unitCost(num? unitCost) => _$this._unitCost = unitCost;

  CriteriaEstimateResponseBuilder() {
    CriteriaEstimateResponse._defaults(this);
  }

  CriteriaEstimateResponseBuilder get _$this {
    final $v = _$v;
    if ($v != null) {
      _estimatedCost = $v.estimatedCost;
      _maxPages = $v.maxPages;
      _pageCount = $v.pageCount;
      _unitCost = $v.unitCost;
      _$v = null;
    }
    return this;
  }

  @override
  void replace(CriteriaEstimateResponse other) {
    _$v = other as _$CriteriaEstimateResponse;
  }

  @override
  void update(void Function(CriteriaEstimateResponseBuilder)? updates) {
    if (updates != null) updates(this);
  }

  @override
  CriteriaEstimateResponse build() => _build();

  _$CriteriaEstimateResponse _build() {
    final _$result = _$v ??
        _$CriteriaEstimateResponse._(
          estimatedCost: estimatedCost,
          maxPages: BuiltValueNullFieldError.checkNotNull(
              maxPages, r'CriteriaEstimateResponse', 'maxPages'),
          pageCount: BuiltValueNullFieldError.checkNotNull(
              pageCount, r'CriteriaEstimateResponse', 'pageCount'),
          unitCost: unitCost,
        );
    replace(_$result);
    return _$result;
  }
}

// ignore_for_file: deprecated_member_use_from_same_package,type=lint
