// GENERATED CODE - DO NOT MODIFY BY HAND

part of 'rubric_criterion_response.dart';

// **************************************************************************
// BuiltValueGenerator
// **************************************************************************

class _$RubricCriterionResponse extends RubricCriterionResponse {
  @override
  final String description;
  @override
  final String id;
  @override
  final int maxPoints;
  @override
  final int position;

  factory _$RubricCriterionResponse(
          [void Function(RubricCriterionResponseBuilder)? updates]) =>
      (RubricCriterionResponseBuilder()..update(updates))._build();

  _$RubricCriterionResponse._(
      {required this.description,
      required this.id,
      required this.maxPoints,
      required this.position})
      : super._();
  @override
  RubricCriterionResponse rebuild(
          void Function(RubricCriterionResponseBuilder) updates) =>
      (toBuilder()..update(updates)).build();

  @override
  RubricCriterionResponseBuilder toBuilder() =>
      RubricCriterionResponseBuilder()..replace(this);

  @override
  bool operator ==(Object other) {
    if (identical(other, this)) return true;
    return other is RubricCriterionResponse &&
        description == other.description &&
        id == other.id &&
        maxPoints == other.maxPoints &&
        position == other.position;
  }

  @override
  int get hashCode {
    var _$hash = 0;
    _$hash = $jc(_$hash, description.hashCode);
    _$hash = $jc(_$hash, id.hashCode);
    _$hash = $jc(_$hash, maxPoints.hashCode);
    _$hash = $jc(_$hash, position.hashCode);
    _$hash = $jf(_$hash);
    return _$hash;
  }

  @override
  String toString() {
    return (newBuiltValueToStringHelper(r'RubricCriterionResponse')
          ..add('description', description)
          ..add('id', id)
          ..add('maxPoints', maxPoints)
          ..add('position', position))
        .toString();
  }
}

class RubricCriterionResponseBuilder
    implements
        Builder<RubricCriterionResponse, RubricCriterionResponseBuilder> {
  _$RubricCriterionResponse? _$v;

  String? _description;
  String? get description => _$this._description;
  set description(String? description) => _$this._description = description;

  String? _id;
  String? get id => _$this._id;
  set id(String? id) => _$this._id = id;

  int? _maxPoints;
  int? get maxPoints => _$this._maxPoints;
  set maxPoints(int? maxPoints) => _$this._maxPoints = maxPoints;

  int? _position;
  int? get position => _$this._position;
  set position(int? position) => _$this._position = position;

  RubricCriterionResponseBuilder() {
    RubricCriterionResponse._defaults(this);
  }

  RubricCriterionResponseBuilder get _$this {
    final $v = _$v;
    if ($v != null) {
      _description = $v.description;
      _id = $v.id;
      _maxPoints = $v.maxPoints;
      _position = $v.position;
      _$v = null;
    }
    return this;
  }

  @override
  void replace(RubricCriterionResponse other) {
    _$v = other as _$RubricCriterionResponse;
  }

  @override
  void update(void Function(RubricCriterionResponseBuilder)? updates) {
    if (updates != null) updates(this);
  }

  @override
  RubricCriterionResponse build() => _build();

  _$RubricCriterionResponse _build() {
    final _$result = _$v ??
        _$RubricCriterionResponse._(
          description: BuiltValueNullFieldError.checkNotNull(
              description, r'RubricCriterionResponse', 'description'),
          id: BuiltValueNullFieldError.checkNotNull(
              id, r'RubricCriterionResponse', 'id'),
          maxPoints: BuiltValueNullFieldError.checkNotNull(
              maxPoints, r'RubricCriterionResponse', 'maxPoints'),
          position: BuiltValueNullFieldError.checkNotNull(
              position, r'RubricCriterionResponse', 'position'),
        );
    replace(_$result);
    return _$result;
  }
}

// ignore_for_file: deprecated_member_use_from_same_package,type=lint
