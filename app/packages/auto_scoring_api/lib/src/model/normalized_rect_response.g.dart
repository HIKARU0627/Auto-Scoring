// GENERATED CODE - DO NOT MODIFY BY HAND

part of 'normalized_rect_response.dart';

// **************************************************************************
// BuiltValueGenerator
// **************************************************************************

class _$NormalizedRectResponse extends NormalizedRectResponse {
  @override
  final num height;
  @override
  final num width;
  @override
  final num x;
  @override
  final num y;

  factory _$NormalizedRectResponse(
          [void Function(NormalizedRectResponseBuilder)? updates]) =>
      (NormalizedRectResponseBuilder()..update(updates))._build();

  _$NormalizedRectResponse._(
      {required this.height,
      required this.width,
      required this.x,
      required this.y})
      : super._();
  @override
  NormalizedRectResponse rebuild(
          void Function(NormalizedRectResponseBuilder) updates) =>
      (toBuilder()..update(updates)).build();

  @override
  NormalizedRectResponseBuilder toBuilder() =>
      NormalizedRectResponseBuilder()..replace(this);

  @override
  bool operator ==(Object other) {
    if (identical(other, this)) return true;
    return other is NormalizedRectResponse &&
        height == other.height &&
        width == other.width &&
        x == other.x &&
        y == other.y;
  }

  @override
  int get hashCode {
    var _$hash = 0;
    _$hash = $jc(_$hash, height.hashCode);
    _$hash = $jc(_$hash, width.hashCode);
    _$hash = $jc(_$hash, x.hashCode);
    _$hash = $jc(_$hash, y.hashCode);
    _$hash = $jf(_$hash);
    return _$hash;
  }

  @override
  String toString() {
    return (newBuiltValueToStringHelper(r'NormalizedRectResponse')
          ..add('height', height)
          ..add('width', width)
          ..add('x', x)
          ..add('y', y))
        .toString();
  }
}

class NormalizedRectResponseBuilder
    implements Builder<NormalizedRectResponse, NormalizedRectResponseBuilder> {
  _$NormalizedRectResponse? _$v;

  num? _height;
  num? get height => _$this._height;
  set height(num? height) => _$this._height = height;

  num? _width;
  num? get width => _$this._width;
  set width(num? width) => _$this._width = width;

  num? _x;
  num? get x => _$this._x;
  set x(num? x) => _$this._x = x;

  num? _y;
  num? get y => _$this._y;
  set y(num? y) => _$this._y = y;

  NormalizedRectResponseBuilder() {
    NormalizedRectResponse._defaults(this);
  }

  NormalizedRectResponseBuilder get _$this {
    final $v = _$v;
    if ($v != null) {
      _height = $v.height;
      _width = $v.width;
      _x = $v.x;
      _y = $v.y;
      _$v = null;
    }
    return this;
  }

  @override
  void replace(NormalizedRectResponse other) {
    _$v = other as _$NormalizedRectResponse;
  }

  @override
  void update(void Function(NormalizedRectResponseBuilder)? updates) {
    if (updates != null) updates(this);
  }

  @override
  NormalizedRectResponse build() => _build();

  _$NormalizedRectResponse _build() {
    final _$result = _$v ??
        _$NormalizedRectResponse._(
          height: BuiltValueNullFieldError.checkNotNull(
              height, r'NormalizedRectResponse', 'height'),
          width: BuiltValueNullFieldError.checkNotNull(
              width, r'NormalizedRectResponse', 'width'),
          x: BuiltValueNullFieldError.checkNotNull(
              x, r'NormalizedRectResponse', 'x'),
          y: BuiltValueNullFieldError.checkNotNull(
              y, r'NormalizedRectResponse', 'y'),
        );
    replace(_$result);
    return _$result;
  }
}

// ignore_for_file: deprecated_member_use_from_same_package,type=lint
