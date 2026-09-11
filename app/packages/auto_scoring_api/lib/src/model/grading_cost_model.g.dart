// GENERATED CODE - DO NOT MODIFY BY HAND

part of 'grading_cost_model.dart';

// **************************************************************************
// BuiltValueGenerator
// **************************************************************************

class _$GradingCostModel extends GradingCostModel {
  @override
  final num? tokenUnitCost;

  factory _$GradingCostModel(
          [void Function(GradingCostModelBuilder)? updates]) =>
      (GradingCostModelBuilder()..update(updates))._build();

  _$GradingCostModel._({this.tokenUnitCost}) : super._();
  @override
  GradingCostModel rebuild(void Function(GradingCostModelBuilder) updates) =>
      (toBuilder()..update(updates)).build();

  @override
  GradingCostModelBuilder toBuilder() =>
      GradingCostModelBuilder()..replace(this);

  @override
  bool operator ==(Object other) {
    if (identical(other, this)) return true;
    return other is GradingCostModel && tokenUnitCost == other.tokenUnitCost;
  }

  @override
  int get hashCode {
    var _$hash = 0;
    _$hash = $jc(_$hash, tokenUnitCost.hashCode);
    _$hash = $jf(_$hash);
    return _$hash;
  }

  @override
  String toString() {
    return (newBuiltValueToStringHelper(r'GradingCostModel')
          ..add('tokenUnitCost', tokenUnitCost))
        .toString();
  }
}

class GradingCostModelBuilder
    implements Builder<GradingCostModel, GradingCostModelBuilder> {
  _$GradingCostModel? _$v;

  num? _tokenUnitCost;
  num? get tokenUnitCost => _$this._tokenUnitCost;
  set tokenUnitCost(num? tokenUnitCost) =>
      _$this._tokenUnitCost = tokenUnitCost;

  GradingCostModelBuilder() {
    GradingCostModel._defaults(this);
  }

  GradingCostModelBuilder get _$this {
    final $v = _$v;
    if ($v != null) {
      _tokenUnitCost = $v.tokenUnitCost;
      _$v = null;
    }
    return this;
  }

  @override
  void replace(GradingCostModel other) {
    _$v = other as _$GradingCostModel;
  }

  @override
  void update(void Function(GradingCostModelBuilder)? updates) {
    if (updates != null) updates(this);
  }

  @override
  GradingCostModel build() => _build();

  _$GradingCostModel _build() {
    final _$result = _$v ??
        _$GradingCostModel._(
          tokenUnitCost: tokenUnitCost,
        );
    replace(_$result);
    return _$result;
  }
}

// ignore_for_file: deprecated_member_use_from_same_package,type=lint
