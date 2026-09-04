// GENERATED CODE - DO NOT MODIFY BY HAND

part of 'score_request.dart';

// **************************************************************************
// BuiltValueGenerator
// **************************************************************************

class _$ScoreRequest extends ScoreRequest {
  @override
  final String key;
  @override
  final int maximum;
  @override
  final int raw;

  factory _$ScoreRequest([void Function(ScoreRequestBuilder)? updates]) =>
      (ScoreRequestBuilder()..update(updates))._build();

  _$ScoreRequest._(
      {required this.key, required this.maximum, required this.raw})
      : super._();
  @override
  ScoreRequest rebuild(void Function(ScoreRequestBuilder) updates) =>
      (toBuilder()..update(updates)).build();

  @override
  ScoreRequestBuilder toBuilder() => ScoreRequestBuilder()..replace(this);

  @override
  bool operator ==(Object other) {
    if (identical(other, this)) return true;
    return other is ScoreRequest &&
        key == other.key &&
        maximum == other.maximum &&
        raw == other.raw;
  }

  @override
  int get hashCode {
    var _$hash = 0;
    _$hash = $jc(_$hash, key.hashCode);
    _$hash = $jc(_$hash, maximum.hashCode);
    _$hash = $jc(_$hash, raw.hashCode);
    _$hash = $jf(_$hash);
    return _$hash;
  }

  @override
  String toString() {
    return (newBuiltValueToStringHelper(r'ScoreRequest')
          ..add('key', key)
          ..add('maximum', maximum)
          ..add('raw', raw))
        .toString();
  }
}

class ScoreRequestBuilder
    implements Builder<ScoreRequest, ScoreRequestBuilder> {
  _$ScoreRequest? _$v;

  String? _key;
  String? get key => _$this._key;
  set key(String? key) => _$this._key = key;

  int? _maximum;
  int? get maximum => _$this._maximum;
  set maximum(int? maximum) => _$this._maximum = maximum;

  int? _raw;
  int? get raw => _$this._raw;
  set raw(int? raw) => _$this._raw = raw;

  ScoreRequestBuilder() {
    ScoreRequest._defaults(this);
  }

  ScoreRequestBuilder get _$this {
    final $v = _$v;
    if ($v != null) {
      _key = $v.key;
      _maximum = $v.maximum;
      _raw = $v.raw;
      _$v = null;
    }
    return this;
  }

  @override
  void replace(ScoreRequest other) {
    _$v = other as _$ScoreRequest;
  }

  @override
  void update(void Function(ScoreRequestBuilder)? updates) {
    if (updates != null) updates(this);
  }

  @override
  ScoreRequest build() => _build();

  _$ScoreRequest _build() {
    final _$result = _$v ??
        _$ScoreRequest._(
          key: BuiltValueNullFieldError.checkNotNull(
              key, r'ScoreRequest', 'key'),
          maximum: BuiltValueNullFieldError.checkNotNull(
              maximum, r'ScoreRequest', 'maximum'),
          raw: BuiltValueNullFieldError.checkNotNull(
              raw, r'ScoreRequest', 'raw'),
        );
    replace(_$result);
    return _$result;
  }
}

// ignore_for_file: deprecated_member_use_from_same_package,type=lint
