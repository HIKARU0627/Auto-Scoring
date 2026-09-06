// GENERATED CODE - DO NOT MODIFY BY HAND

part of 'normalized_b_box_model.dart';

// **************************************************************************
// BuiltValueGenerator
// **************************************************************************

class _$NormalizedBBoxModel extends NormalizedBBoxModel {
  @override
  final num x0;
  @override
  final num x1;
  @override
  final num y0;
  @override
  final num y1;

  factory _$NormalizedBBoxModel(
          [void Function(NormalizedBBoxModelBuilder)? updates]) =>
      (NormalizedBBoxModelBuilder()..update(updates))._build();

  _$NormalizedBBoxModel._(
      {required this.x0, required this.x1, required this.y0, required this.y1})
      : super._();
  @override
  NormalizedBBoxModel rebuild(
          void Function(NormalizedBBoxModelBuilder) updates) =>
      (toBuilder()..update(updates)).build();

  @override
  NormalizedBBoxModelBuilder toBuilder() =>
      NormalizedBBoxModelBuilder()..replace(this);

  @override
  bool operator ==(Object other) {
    if (identical(other, this)) return true;
    return other is NormalizedBBoxModel &&
        x0 == other.x0 &&
        x1 == other.x1 &&
        y0 == other.y0 &&
        y1 == other.y1;
  }

  @override
  int get hashCode {
    var _$hash = 0;
    _$hash = $jc(_$hash, x0.hashCode);
    _$hash = $jc(_$hash, x1.hashCode);
    _$hash = $jc(_$hash, y0.hashCode);
    _$hash = $jc(_$hash, y1.hashCode);
    _$hash = $jf(_$hash);
    return _$hash;
  }

  @override
  String toString() {
    return (newBuiltValueToStringHelper(r'NormalizedBBoxModel')
          ..add('x0', x0)
          ..add('x1', x1)
          ..add('y0', y0)
          ..add('y1', y1))
        .toString();
  }
}

class NormalizedBBoxModelBuilder
    implements Builder<NormalizedBBoxModel, NormalizedBBoxModelBuilder> {
  _$NormalizedBBoxModel? _$v;

  num? _x0;
  num? get x0 => _$this._x0;
  set x0(num? x0) => _$this._x0 = x0;

  num? _x1;
  num? get x1 => _$this._x1;
  set x1(num? x1) => _$this._x1 = x1;

  num? _y0;
  num? get y0 => _$this._y0;
  set y0(num? y0) => _$this._y0 = y0;

  num? _y1;
  num? get y1 => _$this._y1;
  set y1(num? y1) => _$this._y1 = y1;

  NormalizedBBoxModelBuilder() {
    NormalizedBBoxModel._defaults(this);
  }

  NormalizedBBoxModelBuilder get _$this {
    final $v = _$v;
    if ($v != null) {
      _x0 = $v.x0;
      _x1 = $v.x1;
      _y0 = $v.y0;
      _y1 = $v.y1;
      _$v = null;
    }
    return this;
  }

  @override
  void replace(NormalizedBBoxModel other) {
    _$v = other as _$NormalizedBBoxModel;
  }

  @override
  void update(void Function(NormalizedBBoxModelBuilder)? updates) {
    if (updates != null) updates(this);
  }

  @override
  NormalizedBBoxModel build() => _build();

  _$NormalizedBBoxModel _build() {
    final _$result = _$v ??
        _$NormalizedBBoxModel._(
          x0: BuiltValueNullFieldError.checkNotNull(
              x0, r'NormalizedBBoxModel', 'x0'),
          x1: BuiltValueNullFieldError.checkNotNull(
              x1, r'NormalizedBBoxModel', 'x1'),
          y0: BuiltValueNullFieldError.checkNotNull(
              y0, r'NormalizedBBoxModel', 'y0'),
          y1: BuiltValueNullFieldError.checkNotNull(
              y1, r'NormalizedBBoxModel', 'y1'),
        );
    replace(_$result);
    return _$result;
  }
}

// ignore_for_file: deprecated_member_use_from_same_package,type=lint
