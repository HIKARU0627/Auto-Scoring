// GENERATED CODE - DO NOT MODIFY BY HAND

part of 'intake_plan_response.dart';

// **************************************************************************
// BuiltValueGenerator
// **************************************************************************

class _$IntakePlanResponse extends IntakePlanResponse {
  @override
  final ClassificationEstimateModel estimate;
  @override
  final BuiltList<PlannedGroupModel> groups;

  factory _$IntakePlanResponse(
          [void Function(IntakePlanResponseBuilder)? updates]) =>
      (IntakePlanResponseBuilder()..update(updates))._build();

  _$IntakePlanResponse._({required this.estimate, required this.groups})
      : super._();
  @override
  IntakePlanResponse rebuild(
          void Function(IntakePlanResponseBuilder) updates) =>
      (toBuilder()..update(updates)).build();

  @override
  IntakePlanResponseBuilder toBuilder() =>
      IntakePlanResponseBuilder()..replace(this);

  @override
  bool operator ==(Object other) {
    if (identical(other, this)) return true;
    return other is IntakePlanResponse &&
        estimate == other.estimate &&
        groups == other.groups;
  }

  @override
  int get hashCode {
    var _$hash = 0;
    _$hash = $jc(_$hash, estimate.hashCode);
    _$hash = $jc(_$hash, groups.hashCode);
    _$hash = $jf(_$hash);
    return _$hash;
  }

  @override
  String toString() {
    return (newBuiltValueToStringHelper(r'IntakePlanResponse')
          ..add('estimate', estimate)
          ..add('groups', groups))
        .toString();
  }
}

class IntakePlanResponseBuilder
    implements Builder<IntakePlanResponse, IntakePlanResponseBuilder> {
  _$IntakePlanResponse? _$v;

  ClassificationEstimateModelBuilder? _estimate;
  ClassificationEstimateModelBuilder get estimate =>
      _$this._estimate ??= ClassificationEstimateModelBuilder();
  set estimate(ClassificationEstimateModelBuilder? estimate) =>
      _$this._estimate = estimate;

  ListBuilder<PlannedGroupModel>? _groups;
  ListBuilder<PlannedGroupModel> get groups =>
      _$this._groups ??= ListBuilder<PlannedGroupModel>();
  set groups(ListBuilder<PlannedGroupModel>? groups) => _$this._groups = groups;

  IntakePlanResponseBuilder() {
    IntakePlanResponse._defaults(this);
  }

  IntakePlanResponseBuilder get _$this {
    final $v = _$v;
    if ($v != null) {
      _estimate = $v.estimate.toBuilder();
      _groups = $v.groups.toBuilder();
      _$v = null;
    }
    return this;
  }

  @override
  void replace(IntakePlanResponse other) {
    _$v = other as _$IntakePlanResponse;
  }

  @override
  void update(void Function(IntakePlanResponseBuilder)? updates) {
    if (updates != null) updates(this);
  }

  @override
  IntakePlanResponse build() => _build();

  _$IntakePlanResponse _build() {
    _$IntakePlanResponse _$result;
    try {
      _$result = _$v ??
          _$IntakePlanResponse._(
            estimate: estimate.build(),
            groups: groups.build(),
          );
    } catch (_) {
      late String _$failedField;
      try {
        _$failedField = 'estimate';
        estimate.build();
        _$failedField = 'groups';
        groups.build();
      } catch (e) {
        throw BuiltValueNestedFieldError(
            r'IntakePlanResponse', _$failedField, e.toString());
      }
      rethrow;
    }
    replace(_$result);
    return _$result;
  }
}

// ignore_for_file: deprecated_member_use_from_same_package,type=lint
