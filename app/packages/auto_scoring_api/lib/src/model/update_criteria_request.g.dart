// GENERATED CODE - DO NOT MODIFY BY HAND

part of 'update_criteria_request.dart';

// **************************************************************************
// BuiltValueGenerator
// **************************************************************************

class _$UpdateCriteriaRequest extends UpdateCriteriaRequest {
  @override
  final int? declaredTotalPoints;
  @override
  final BuiltList<CriteriaQuestionModel> questions;

  factory _$UpdateCriteriaRequest(
          [void Function(UpdateCriteriaRequestBuilder)? updates]) =>
      (UpdateCriteriaRequestBuilder()..update(updates))._build();

  _$UpdateCriteriaRequest._({this.declaredTotalPoints, required this.questions})
      : super._();
  @override
  UpdateCriteriaRequest rebuild(
          void Function(UpdateCriteriaRequestBuilder) updates) =>
      (toBuilder()..update(updates)).build();

  @override
  UpdateCriteriaRequestBuilder toBuilder() =>
      UpdateCriteriaRequestBuilder()..replace(this);

  @override
  bool operator ==(Object other) {
    if (identical(other, this)) return true;
    return other is UpdateCriteriaRequest &&
        declaredTotalPoints == other.declaredTotalPoints &&
        questions == other.questions;
  }

  @override
  int get hashCode {
    var _$hash = 0;
    _$hash = $jc(_$hash, declaredTotalPoints.hashCode);
    _$hash = $jc(_$hash, questions.hashCode);
    _$hash = $jf(_$hash);
    return _$hash;
  }

  @override
  String toString() {
    return (newBuiltValueToStringHelper(r'UpdateCriteriaRequest')
          ..add('declaredTotalPoints', declaredTotalPoints)
          ..add('questions', questions))
        .toString();
  }
}

class UpdateCriteriaRequestBuilder
    implements Builder<UpdateCriteriaRequest, UpdateCriteriaRequestBuilder> {
  _$UpdateCriteriaRequest? _$v;

  int? _declaredTotalPoints;
  int? get declaredTotalPoints => _$this._declaredTotalPoints;
  set declaredTotalPoints(int? declaredTotalPoints) =>
      _$this._declaredTotalPoints = declaredTotalPoints;

  ListBuilder<CriteriaQuestionModel>? _questions;
  ListBuilder<CriteriaQuestionModel> get questions =>
      _$this._questions ??= ListBuilder<CriteriaQuestionModel>();
  set questions(ListBuilder<CriteriaQuestionModel>? questions) =>
      _$this._questions = questions;

  UpdateCriteriaRequestBuilder() {
    UpdateCriteriaRequest._defaults(this);
  }

  UpdateCriteriaRequestBuilder get _$this {
    final $v = _$v;
    if ($v != null) {
      _declaredTotalPoints = $v.declaredTotalPoints;
      _questions = $v.questions.toBuilder();
      _$v = null;
    }
    return this;
  }

  @override
  void replace(UpdateCriteriaRequest other) {
    _$v = other as _$UpdateCriteriaRequest;
  }

  @override
  void update(void Function(UpdateCriteriaRequestBuilder)? updates) {
    if (updates != null) updates(this);
  }

  @override
  UpdateCriteriaRequest build() => _build();

  _$UpdateCriteriaRequest _build() {
    _$UpdateCriteriaRequest _$result;
    try {
      _$result = _$v ??
          _$UpdateCriteriaRequest._(
            declaredTotalPoints: declaredTotalPoints,
            questions: questions.build(),
          );
    } catch (_) {
      late String _$failedField;
      try {
        _$failedField = 'questions';
        questions.build();
      } catch (e) {
        throw BuiltValueNestedFieldError(
            r'UpdateCriteriaRequest', _$failedField, e.toString());
      }
      rethrow;
    }
    replace(_$result);
    return _$result;
  }
}

// ignore_for_file: deprecated_member_use_from_same_package,type=lint
