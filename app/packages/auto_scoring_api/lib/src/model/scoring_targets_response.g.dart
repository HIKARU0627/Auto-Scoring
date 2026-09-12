// GENERATED CODE - DO NOT MODIFY BY HAND

part of 'scoring_targets_response.dart';

// **************************************************************************
// BuiltValueGenerator
// **************************************************************************

class _$ScoringTargetsResponse extends ScoringTargetsResponse {
  @override
  final BuiltList<String> questionIds;

  factory _$ScoringTargetsResponse(
          [void Function(ScoringTargetsResponseBuilder)? updates]) =>
      (ScoringTargetsResponseBuilder()..update(updates))._build();

  _$ScoringTargetsResponse._({required this.questionIds}) : super._();
  @override
  ScoringTargetsResponse rebuild(
          void Function(ScoringTargetsResponseBuilder) updates) =>
      (toBuilder()..update(updates)).build();

  @override
  ScoringTargetsResponseBuilder toBuilder() =>
      ScoringTargetsResponseBuilder()..replace(this);

  @override
  bool operator ==(Object other) {
    if (identical(other, this)) return true;
    return other is ScoringTargetsResponse && questionIds == other.questionIds;
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
    return (newBuiltValueToStringHelper(r'ScoringTargetsResponse')
          ..add('questionIds', questionIds))
        .toString();
  }
}

class ScoringTargetsResponseBuilder
    implements Builder<ScoringTargetsResponse, ScoringTargetsResponseBuilder> {
  _$ScoringTargetsResponse? _$v;

  ListBuilder<String>? _questionIds;
  ListBuilder<String> get questionIds =>
      _$this._questionIds ??= ListBuilder<String>();
  set questionIds(ListBuilder<String>? questionIds) =>
      _$this._questionIds = questionIds;

  ScoringTargetsResponseBuilder() {
    ScoringTargetsResponse._defaults(this);
  }

  ScoringTargetsResponseBuilder get _$this {
    final $v = _$v;
    if ($v != null) {
      _questionIds = $v.questionIds.toBuilder();
      _$v = null;
    }
    return this;
  }

  @override
  void replace(ScoringTargetsResponse other) {
    _$v = other as _$ScoringTargetsResponse;
  }

  @override
  void update(void Function(ScoringTargetsResponseBuilder)? updates) {
    if (updates != null) updates(this);
  }

  @override
  ScoringTargetsResponse build() => _build();

  _$ScoringTargetsResponse _build() {
    _$ScoringTargetsResponse _$result;
    try {
      _$result = _$v ??
          _$ScoringTargetsResponse._(
            questionIds: questionIds.build(),
          );
    } catch (_) {
      late String _$failedField;
      try {
        _$failedField = 'questionIds';
        questionIds.build();
      } catch (e) {
        throw BuiltValueNestedFieldError(
            r'ScoringTargetsResponse', _$failedField, e.toString());
      }
      rethrow;
    }
    replace(_$result);
    return _$result;
  }
}

// ignore_for_file: deprecated_member_use_from_same_package,type=lint
