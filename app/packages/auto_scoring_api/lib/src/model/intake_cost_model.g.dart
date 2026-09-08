// GENERATED CODE - DO NOT MODIFY BY HAND

part of 'intake_cost_model.dart';

// **************************************************************************
// BuiltValueGenerator
// **************************************************************************

class _$IntakeCostModel extends IntakeCostModel {
  @override
  final num? classificationUnitCost;

  factory _$IntakeCostModel([void Function(IntakeCostModelBuilder)? updates]) =>
      (IntakeCostModelBuilder()..update(updates))._build();

  _$IntakeCostModel._({this.classificationUnitCost}) : super._();
  @override
  IntakeCostModel rebuild(void Function(IntakeCostModelBuilder) updates) =>
      (toBuilder()..update(updates)).build();

  @override
  IntakeCostModelBuilder toBuilder() => IntakeCostModelBuilder()..replace(this);

  @override
  bool operator ==(Object other) {
    if (identical(other, this)) return true;
    return other is IntakeCostModel &&
        classificationUnitCost == other.classificationUnitCost;
  }

  @override
  int get hashCode {
    var _$hash = 0;
    _$hash = $jc(_$hash, classificationUnitCost.hashCode);
    _$hash = $jf(_$hash);
    return _$hash;
  }

  @override
  String toString() {
    return (newBuiltValueToStringHelper(r'IntakeCostModel')
          ..add('classificationUnitCost', classificationUnitCost))
        .toString();
  }
}

class IntakeCostModelBuilder
    implements Builder<IntakeCostModel, IntakeCostModelBuilder> {
  _$IntakeCostModel? _$v;

  num? _classificationUnitCost;
  num? get classificationUnitCost => _$this._classificationUnitCost;
  set classificationUnitCost(num? classificationUnitCost) =>
      _$this._classificationUnitCost = classificationUnitCost;

  IntakeCostModelBuilder() {
    IntakeCostModel._defaults(this);
  }

  IntakeCostModelBuilder get _$this {
    final $v = _$v;
    if ($v != null) {
      _classificationUnitCost = $v.classificationUnitCost;
      _$v = null;
    }
    return this;
  }

  @override
  void replace(IntakeCostModel other) {
    _$v = other as _$IntakeCostModel;
  }

  @override
  void update(void Function(IntakeCostModelBuilder)? updates) {
    if (updates != null) updates(this);
  }

  @override
  IntakeCostModel build() => _build();

  _$IntakeCostModel _build() {
    final _$result = _$v ??
        _$IntakeCostModel._(
          classificationUnitCost: classificationUnitCost,
        );
    replace(_$result);
    return _$result;
  }
}

// ignore_for_file: deprecated_member_use_from_same_package,type=lint
