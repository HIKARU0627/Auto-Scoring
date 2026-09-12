// GENERATED CODE - DO NOT MODIFY BY HAND

part of 'scoring_targets_request.dart';

// **************************************************************************
// BuiltValueGenerator
// **************************************************************************

class _$ScoringTargetsRequest extends ScoringTargetsRequest {
  @override
  final BuiltList<String> questionIds;

  factory _$ScoringTargetsRequest(
          [void Function(ScoringTargetsRequestBuilder)? updates]) =>
      (ScoringTargetsRequestBuilder()..update(updates))._build();

  _$ScoringTargetsRequest._({required this.questionIds}) : super._();
  @override
  ScoringTargetsRequest rebuild(
          void Function(ScoringTargetsRequestBuilder) updates) =>
      (toBuilder()..update(updates)).build();

  @override
  ScoringTargetsRequestBuilder toBuilder() =>
      ScoringTargetsRequestBuilder()..replace(this);

  @override
  bool operator ==(Object other) {
    if (identical(other, this)) return true;
    return other is ScoringTargetsRequest && questionIds == other.questionIds;
  }

  @override
  int get hashCode {
    var _$hash = 0;
    _$hash = $jc(_$hash, questionIds.hashCode);
    _$hash = $jf(_$hash);
    return _$hash;
  }

  @override
  String toString() {
    return (newBuiltValueToStringHelper(r'ScoringTargetsRequest')
          ..add('questionIds', questionIds))
        .toString();
  }
}

class ScoringTargetsRequestBuilder
    implements Builder<ScoringTargetsRequest, ScoringTargetsRequestBuilder> {
  _$ScoringTargetsRequest? _$v;

  ListBuilder<String>? _questionIds;
  ListBuilder<String> get questionIds =>
      _$this._questionIds ??= ListBuilder<String>();
  set questionIds(ListBuilder<String>? questionIds) =>
      _$this._questionIds = questionIds;

  ScoringTargetsRequestBuilder() {
    ScoringTargetsRequest._defaults(this);
  }

  ScoringTargetsRequestBuilder get _$this {
    final $v = _$v;
    if ($v != null) {
      _questionIds = $v.questionIds.toBuilder();
      _$v = null;
    }
    return this;
  }

  @override
  void replace(ScoringTargetsRequest other) {
    _$v = other as _$ScoringTargetsRequest;
  }

  @override
  void update(void Function(ScoringTargetsRequestBuilder)? updates) {
    if (updates != null) updates(this);
  }

  @override
  ScoringTargetsRequest build() => _build();

  _$ScoringTargetsRequest _build() {
    _$ScoringTargetsRequest _$result;
    try {
      _$result = _$v ??
          _$ScoringTargetsRequest._(
            questionIds: questionIds.build(),
          );
    } catch (_) {
      late String _$failedField;
      try {
        _$failedField = 'questionIds';
        questionIds.build();
      } catch (e) {
        throw BuiltValueNestedFieldError(
            r'ScoringTargetsRequest', _$failedField, e.toString());
      }
      rethrow;
    }
    replace(_$result);
    return _$result;
  }
}

// ignore_for_file: deprecated_member_use_from_same_package,type=lint
