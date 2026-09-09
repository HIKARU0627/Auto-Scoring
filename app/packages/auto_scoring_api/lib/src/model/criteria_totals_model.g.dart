// GENERATED CODE - DO NOT MODIFY BY HAND

part of 'criteria_totals_model.dart';

// **************************************************************************
// BuiltValueGenerator
// **************************************************************************

class _$CriteriaTotalsModel extends CriteriaTotalsModel {
  @override
  final int? declaredDifference;
  @override
  final int? declaredTotalPoints;
  @override
  final bool isComplete;
  @override
  final int knownPoints;
  @override
  final int unknownCount;

  factory _$CriteriaTotalsModel(
          [void Function(CriteriaTotalsModelBuilder)? updates]) =>
      (CriteriaTotalsModelBuilder()..update(updates))._build();

  _$CriteriaTotalsModel._(
      {this.declaredDifference,
      this.declaredTotalPoints,
      required this.isComplete,
      required this.knownPoints,
      required this.unknownCount})
      : super._();
  @override
  CriteriaTotalsModel rebuild(
          void Function(CriteriaTotalsModelBuilder) updates) =>
      (toBuilder()..update(updates)).build();

  @override
  CriteriaTotalsModelBuilder toBuilder() =>
      CriteriaTotalsModelBuilder()..replace(this);

  @override
  bool operator ==(Object other) {
    if (identical(other, this)) return true;
    return other is CriteriaTotalsModel &&
        declaredDifference == other.declaredDifference &&
        declaredTotalPoints == other.declaredTotalPoints &&
        isComplete == other.isComplete &&
        knownPoints == other.knownPoints &&
        unknownCount == other.unknownCount;
  }

  @override
  int get hashCode {
    var _$hash = 0;
    _$hash = $jc(_$hash, declaredDifference.hashCode);
    _$hash = $jc(_$hash, declaredTotalPoints.hashCode);
    _$hash = $jc(_$hash, isComplete.hashCode);
    _$hash = $jc(_$hash, knownPoints.hashCode);
    _$hash = $jc(_$hash, unknownCount.hashCode);
    _$hash = $jf(_$hash);
    return _$hash;
  }

  @override
  String toString() {
    return (newBuiltValueToStringHelper(r'CriteriaTotalsModel')
          ..add('declaredDifference', declaredDifference)
          ..add('declaredTotalPoints', declaredTotalPoints)
          ..add('isComplete', isComplete)
          ..add('knownPoints', knownPoints)
          ..add('unknownCount', unknownCount))
        .toString();
  }
}

class CriteriaTotalsModelBuilder
    implements Builder<CriteriaTotalsModel, CriteriaTotalsModelBuilder> {
  _$CriteriaTotalsModel? _$v;

  int? _declaredDifference;
  int? get declaredDifference => _$this._declaredDifference;
  set declaredDifference(int? declaredDifference) =>
      _$this._declaredDifference = declaredDifference;

  int? _declaredTotalPoints;
  int? get declaredTotalPoints => _$this._declaredTotalPoints;
  set declaredTotalPoints(int? declaredTotalPoints) =>
      _$this._declaredTotalPoints = declaredTotalPoints;

  bool? _isComplete;
  bool? get isComplete => _$this._isComplete;
  set isComplete(bool? isComplete) => _$this._isComplete = isComplete;

  int? _knownPoints;
  int? get knownPoints => _$this._knownPoints;
  set knownPoints(int? knownPoints) => _$this._knownPoints = knownPoints;

  int? _unknownCount;
  int? get unknownCount => _$this._unknownCount;
  set unknownCount(int? unknownCount) => _$this._unknownCount = unknownCount;

  CriteriaTotalsModelBuilder() {
    CriteriaTotalsModel._defaults(this);
  }

  CriteriaTotalsModelBuilder get _$this {
    final $v = _$v;
    if ($v != null) {
      _declaredDifference = $v.declaredDifference;
      _declaredTotalPoints = $v.declaredTotalPoints;
      _isComplete = $v.isComplete;
      _knownPoints = $v.knownPoints;
      _unknownCount = $v.unknownCount;
      _$v = null;
    }
    return this;
  }

  @override
  void replace(CriteriaTotalsModel other) {
    _$v = other as _$CriteriaTotalsModel;
  }

  @override
  void update(void Function(CriteriaTotalsModelBuilder)? updates) {
    if (updates != null) updates(this);
  }

  @override
  CriteriaTotalsModel build() => _build();

  _$CriteriaTotalsModel _build() {
    final _$result = _$v ??
        _$CriteriaTotalsModel._(
          declaredDifference: declaredDifference,
          declaredTotalPoints: declaredTotalPoints,
          isComplete: BuiltValueNullFieldError.checkNotNull(
              isComplete, r'CriteriaTotalsModel', 'isComplete'),
          knownPoints: BuiltValueNullFieldError.checkNotNull(
              knownPoints, r'CriteriaTotalsModel', 'knownPoints'),
          unknownCount: BuiltValueNullFieldError.checkNotNull(
              unknownCount, r'CriteriaTotalsModel', 'unknownCount'),
        );
    replace(_$result);
    return _$result;
  }
}

// ignore_for_file: deprecated_member_use_from_same_package,type=lint
