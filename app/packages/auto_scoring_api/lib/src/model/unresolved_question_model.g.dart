// GENERATED CODE - DO NOT MODIFY BY HAND

part of 'unresolved_question_model.dart';

// **************************************************************************
// BuiltValueGenerator
// **************************************************************************

class _$UnresolvedQuestionModel extends UnresolvedQuestionModel {
  @override
  final String questionId;
  @override
  final String reason;

  factory _$UnresolvedQuestionModel(
          [void Function(UnresolvedQuestionModelBuilder)? updates]) =>
      (UnresolvedQuestionModelBuilder()..update(updates))._build();

  _$UnresolvedQuestionModel._({required this.questionId, required this.reason})
      : super._();
  @override
  UnresolvedQuestionModel rebuild(
          void Function(UnresolvedQuestionModelBuilder) updates) =>
      (toBuilder()..update(updates)).build();

  @override
  UnresolvedQuestionModelBuilder toBuilder() =>
      UnresolvedQuestionModelBuilder()..replace(this);

  @override
  bool operator ==(Object other) {
    if (identical(other, this)) return true;
    return other is UnresolvedQuestionModel &&
        questionId == other.questionId &&
        reason == other.reason;
  }

  @override
  int get hashCode {
    var _$hash = 0;
    _$hash = $jc(_$hash, questionId.hashCode);
    _$hash = $jc(_$hash, reason.hashCode);
    _$hash = $jf(_$hash);
    return _$hash;
  }

  @override
  String toString() {
    return (newBuiltValueToStringHelper(r'UnresolvedQuestionModel')
          ..add('questionId', questionId)
          ..add('reason', reason))
        .toString();
  }
}

class UnresolvedQuestionModelBuilder
    implements
        Builder<UnresolvedQuestionModel, UnresolvedQuestionModelBuilder> {
  _$UnresolvedQuestionModel? _$v;

  String? _questionId;
  String? get questionId => _$this._questionId;
  set questionId(String? questionId) => _$this._questionId = questionId;

  String? _reason;
  String? get reason => _$this._reason;
  set reason(String? reason) => _$this._reason = reason;

  UnresolvedQuestionModelBuilder() {
    UnresolvedQuestionModel._defaults(this);
  }

  UnresolvedQuestionModelBuilder get _$this {
    final $v = _$v;
    if ($v != null) {
      _questionId = $v.questionId;
      _reason = $v.reason;
      _$v = null;
    }
    return this;
  }

  @override
  void replace(UnresolvedQuestionModel other) {
    _$v = other as _$UnresolvedQuestionModel;
  }

  @override
  void update(void Function(UnresolvedQuestionModelBuilder)? updates) {
    if (updates != null) updates(this);
  }

  @override
  UnresolvedQuestionModel build() => _build();

  _$UnresolvedQuestionModel _build() {
    final _$result = _$v ??
        _$UnresolvedQuestionModel._(
          questionId: BuiltValueNullFieldError.checkNotNull(
              questionId, r'UnresolvedQuestionModel', 'questionId'),
          reason: BuiltValueNullFieldError.checkNotNull(
              reason, r'UnresolvedQuestionModel', 'reason'),
        );
    replace(_$result);
    return _$result;
  }
}

// ignore_for_file: deprecated_member_use_from_same_package,type=lint
