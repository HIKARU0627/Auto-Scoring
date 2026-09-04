// GENERATED CODE - DO NOT MODIFY BY HAND

part of 'score_response.dart';

// **************************************************************************
// BuiltValueGenerator
// **************************************************************************

class _$ScoreResponse extends ScoreResponse {
  @override
  final int awarded;
  @override
  final String key;
  @override
  final int maximum;
  @override
  final num ratio;

  factory _$ScoreResponse([void Function(ScoreResponseBuilder)? updates]) =>
      (ScoreResponseBuilder()..update(updates))._build();

  _$ScoreResponse._(
      {required this.awarded,
      required this.key,
      required this.maximum,
      required this.ratio})
      : super._();
  @override
  ScoreResponse rebuild(void Function(ScoreResponseBuilder) updates) =>
      (toBuilder()..update(updates)).build();

  @override
  ScoreResponseBuilder toBuilder() => ScoreResponseBuilder()..replace(this);

  @override
  bool operator ==(Object other) {
    if (identical(other, this)) return true;
    return other is ScoreResponse &&
        awarded == other.awarded &&
        key == other.key &&
        maximum == other.maximum &&
        ratio == other.ratio;
  }

  @override
  int get hashCode {
    var _$hash = 0;
    _$hash = $jc(_$hash, awarded.hashCode);
    _$hash = $jc(_$hash, key.hashCode);
    _$hash = $jc(_$hash, maximum.hashCode);
    _$hash = $jc(_$hash, ratio.hashCode);
    _$hash = $jf(_$hash);
    return _$hash;
  }

  @override
  String toString() {
    return (newBuiltValueToStringHelper(r'ScoreResponse')
          ..add('awarded', awarded)
          ..add('key', key)
          ..add('maximum', maximum)
          ..add('ratio', ratio))
        .toString();
  }
}

class ScoreResponseBuilder
    implements Builder<ScoreResponse, ScoreResponseBuilder> {
  _$ScoreResponse? _$v;

  int? _awarded;
  int? get awarded => _$this._awarded;
  set awarded(int? awarded) => _$this._awarded = awarded;

  String? _key;
  String? get key => _$this._key;
  set key(String? key) => _$this._key = key;

  int? _maximum;
  int? get maximum => _$this._maximum;
  set maximum(int? maximum) => _$this._maximum = maximum;

  num? _ratio;
  num? get ratio => _$this._ratio;
  set ratio(num? ratio) => _$this._ratio = ratio;

  ScoreResponseBuilder() {
    ScoreResponse._defaults(this);
  }

  ScoreResponseBuilder get _$this {
    final $v = _$v;
    if ($v != null) {
      _awarded = $v.awarded;
      _key = $v.key;
      _maximum = $v.maximum;
      _ratio = $v.ratio;
      _$v = null;
    }
    return this;
  }

  @override
  void replace(ScoreResponse other) {
    _$v = other as _$ScoreResponse;
  }

  @override
  void update(void Function(ScoreResponseBuilder)? updates) {
    if (updates != null) updates(this);
  }

  @override
  ScoreResponse build() => _build();

  _$ScoreResponse _build() {
    final _$result = _$v ??
        _$ScoreResponse._(
          awarded: BuiltValueNullFieldError.checkNotNull(
              awarded, r'ScoreResponse', 'awarded'),
          key: BuiltValueNullFieldError.checkNotNull(
              key, r'ScoreResponse', 'key'),
          maximum: BuiltValueNullFieldError.checkNotNull(
              maximum, r'ScoreResponse', 'maximum'),
          ratio: BuiltValueNullFieldError.checkNotNull(
              ratio, r'ScoreResponse', 'ratio'),
        );
    replace(_$result);
    return _$result;
  }
}

// ignore_for_file: deprecated_member_use_from_same_package,type=lint
