// GENERATED CODE - DO NOT MODIFY BY HAND

part of 'criteria_item_model.dart';

// **************************************************************************
// BuiltValueGenerator
// **************************************************************************

class _$CriteriaItemModel extends CriteriaItemModel {
  @override
  final String description;
  @override
  final CriterionKind kind;
  @override
  final int? points;

  factory _$CriteriaItemModel(
          [void Function(CriteriaItemModelBuilder)? updates]) =>
      (CriteriaItemModelBuilder()..update(updates))._build();

  _$CriteriaItemModel._(
      {required this.description, required this.kind, this.points})
      : super._();
  @override
  CriteriaItemModel rebuild(void Function(CriteriaItemModelBuilder) updates) =>
      (toBuilder()..update(updates)).build();

  @override
  CriteriaItemModelBuilder toBuilder() =>
      CriteriaItemModelBuilder()..replace(this);

  @override
  bool operator ==(Object other) {
    if (identical(other, this)) return true;
    return other is CriteriaItemModel &&
        description == other.description &&
        kind == other.kind &&
        points == other.points;
  }

  @override
  int get hashCode {
    var _$hash = 0;
    _$hash = $jc(_$hash, description.hashCode);
    _$hash = $jc(_$hash, kind.hashCode);
    _$hash = $jc(_$hash, points.hashCode);
    _$hash = $jf(_$hash);
    return _$hash;
  }

  @override
  String toString() {
    return (newBuiltValueToStringHelper(r'CriteriaItemModel')
          ..add('description', description)
          ..add('kind', kind)
          ..add('points', points))
        .toString();
  }
}

class CriteriaItemModelBuilder
    implements Builder<CriteriaItemModel, CriteriaItemModelBuilder> {
  _$CriteriaItemModel? _$v;

  String? _description;
  String? get description => _$this._description;
  set description(String? description) => _$this._description = description;

  CriterionKind? _kind;
  CriterionKind? get kind => _$this._kind;
  set kind(CriterionKind? kind) => _$this._kind = kind;

  int? _points;
  int? get points => _$this._points;
  set points(int? points) => _$this._points = points;

  CriteriaItemModelBuilder() {
    CriteriaItemModel._defaults(this);
  }

  CriteriaItemModelBuilder get _$this {
    final $v = _$v;
    if ($v != null) {
      _description = $v.description;
      _kind = $v.kind;
      _points = $v.points;
      _$v = null;
    }
    return this;
  }

  @override
  void replace(CriteriaItemModel other) {
    _$v = other as _$CriteriaItemModel;
  }

  @override
  void update(void Function(CriteriaItemModelBuilder)? updates) {
    if (updates != null) updates(this);
  }

  @override
  CriteriaItemModel build() => _build();

  _$CriteriaItemModel _build() {
    final _$result = _$v ??
        _$CriteriaItemModel._(
          description: BuiltValueNullFieldError.checkNotNull(
              description, r'CriteriaItemModel', 'description'),
          kind: BuiltValueNullFieldError.checkNotNull(
              kind, r'CriteriaItemModel', 'kind'),
          points: points,
        );
    replace(_$result);
    return _$result;
  }
}

// ignore_for_file: deprecated_member_use_from_same_package,type=lint
