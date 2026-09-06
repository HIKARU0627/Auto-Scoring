// GENERATED CODE - DO NOT MODIFY BY HAND

part of 'score_value_response.dart';

// **************************************************************************
// BuiltValueGenerator
// **************************************************************************

class _$ScoreValueResponse extends ScoreValueResponse {
  @override
  final int awarded;
  @override
  final int maximum;
  @override
  final num ratio;

  factory _$ScoreValueResponse(
          [void Function(ScoreValueResponseBuilder)? updates]) =>
      (ScoreValueResponseBuilder()..update(updates))._build();

  _$ScoreValueResponse._(
      {required this.awarded, required this.maximum, required this.ratio})
      : super._();
  @override
  ScoreValueResponse rebuild(
          void Function(ScoreValueResponseBuilder) updates) =>
      (toBuilder()..update(updates)).build();

  @override
  ScoreValueResponseBuilder toBuilder() =>
      ScoreValueResponseBuilder()..replace(this);

  @override
  bool operator ==(Object other) {
    if (identical(other, this)) return true;
    return other is ScoreValueResponse &&
        awarded == other.awarded &&
        maximum == other.maximum &&
        ratio == other.ratio;
  }

  @override
  int get hashCode {
    var _$hash = 0;
    _$hash = $jc(_$hash, awarded.hashCode);
    _$hash = $jc(_$hash, maximum.hashCode);
    _$hash = $jc(_$hash, ratio.hashCode);
    _$hash = $jf(_$hash);
    return _$hash;
  }

  @override
  String toString() {
    return (newBuiltValueToStringHelper(r'ScoreValueResponse')
          ..add('awarded', awarded)
          ..add('maximum', maximum)
          ..add('ratio', ratio))
        .toString();
  }
}

class ScoreValueResponseBuilder
    implements Builder<ScoreValueResponse, ScoreValueResponseBuilder> {
  _$ScoreValueResponse? _$v;

  int? _awarded;
  int? get awarded => _$this._awarded;
  set awarded(int? awarded) => _$this._awarded = awarded;

  int? _maximum;
  int? get maximum => _$this._maximum;
  set maximum(int? maximum) => _$this._maximum = maximum;

  num? _ratio;
  num? get ratio => _$this._ratio;
  set ratio(num? ratio) => _$this._ratio = ratio;

  ScoreValueResponseBuilder() {
    ScoreValueResponse._defaults(this);
  }

  ScoreValueResponseBuilder get _$this {
    final $v = _$v;
    if ($v != null) {
      _awarded = $v.awarded;
      _maximum = $v.maximum;
      _ratio = $v.ratio;
      _$v = null;
    }
    return this;
  }

  @override
  void replace(ScoreValueResponse other) {
    _$v = other as _$ScoreValueResponse;
  }

  @override
  void update(void Function(ScoreValueResponseBuilder)? updates) {
    if (updates != null) updates(this);
  }

  @override
  ScoreValueResponse build() => _build();

  _$ScoreValueResponse _build() {
    final _$result = _$v ??
        _$ScoreValueResponse._(
          awarded: BuiltValueNullFieldError.checkNotNull(
              awarded, r'ScoreValueResponse', 'awarded'),
          maximum: BuiltValueNullFieldError.checkNotNull(
              maximum, r'ScoreValueResponse', 'maximum'),
          ratio: BuiltValueNullFieldError.checkNotNull(
              ratio, r'ScoreValueResponse', 'ratio'),
        );
    replace(_$result);
    return _$result;
  }
}

// ignore_for_file: deprecated_member_use_from_same_package,type=lint
