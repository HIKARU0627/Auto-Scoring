// GENERATED CODE - DO NOT MODIFY BY HAND

part of 'analyze_request.dart';

// **************************************************************************
// BuiltValueGenerator
// **************************************************************************

class _$AnalyzeRequest extends AnalyzeRequest {
  @override
  final BuiltList<QuestionTextOverride>? overrides;

  factory _$AnalyzeRequest([void Function(AnalyzeRequestBuilder)? updates]) =>
      (AnalyzeRequestBuilder()..update(updates))._build();

  _$AnalyzeRequest._({this.overrides}) : super._();
  @override
  AnalyzeRequest rebuild(void Function(AnalyzeRequestBuilder) updates) =>
      (toBuilder()..update(updates)).build();

  @override
  AnalyzeRequestBuilder toBuilder() => AnalyzeRequestBuilder()..replace(this);

  @override
  bool operator ==(Object other) {
    if (identical(other, this)) return true;
    return other is AnalyzeRequest && overrides == other.overrides;
  }

  @override
  int get hashCode {
    var _$hash = 0;
    _$hash = $jc(_$hash, overrides.hashCode);
    _$hash = $jf(_$hash);
    return _$hash;
  }

  @override
  String toString() {
    return (newBuiltValueToStringHelper(r'AnalyzeRequest')
          ..add('overrides', overrides))
        .toString();
  }
}

class AnalyzeRequestBuilder
    implements Builder<AnalyzeRequest, AnalyzeRequestBuilder> {
  _$AnalyzeRequest? _$v;

  ListBuilder<QuestionTextOverride>? _overrides;
  ListBuilder<QuestionTextOverride> get overrides =>
      _$this._overrides ??= ListBuilder<QuestionTextOverride>();
  set overrides(ListBuilder<QuestionTextOverride>? overrides) =>
      _$this._overrides = overrides;

  AnalyzeRequestBuilder() {
    AnalyzeRequest._defaults(this);
  }

  AnalyzeRequestBuilder get _$this {
    final $v = _$v;
    if ($v != null) {
      _overrides = $v.overrides?.toBuilder();
      _$v = null;
    }
    return this;
  }

  @override
  void replace(AnalyzeRequest other) {
    _$v = other as _$AnalyzeRequest;
  }

  @override
  void update(void Function(AnalyzeRequestBuilder)? updates) {
    if (updates != null) updates(this);
  }

  @override
  AnalyzeRequest build() => _build();

  _$AnalyzeRequest _build() {
    _$AnalyzeRequest _$result;
    try {
      _$result = _$v ??
          _$AnalyzeRequest._(
            overrides: _overrides?.build(),
          );
    } catch (_) {
      late String _$failedField;
      try {
        _$failedField = 'overrides';
        _overrides?.build();
      } catch (e) {
        throw BuiltValueNestedFieldError(
            r'AnalyzeRequest', _$failedField, e.toString());
      }
      rethrow;
    }
    replace(_$result);
    return _$result;
  }
}

// ignore_for_file: deprecated_member_use_from_same_package,type=lint
