// GENERATED CODE - DO NOT MODIFY BY HAND

part of 'bounding_box_response.dart';

// **************************************************************************
// BuiltValueGenerator
// **************************************************************************

class _$BoundingBoxResponse extends BoundingBoxResponse {
  @override
  final num height;
  @override
  final String text;
  @override
  final bool? unreadable;
  @override
  final num width;
  @override
  final num x;
  @override
  final num y;

  factory _$BoundingBoxResponse(
          [void Function(BoundingBoxResponseBuilder)? updates]) =>
      (BoundingBoxResponseBuilder()..update(updates))._build();

  _$BoundingBoxResponse._(
      {required this.height,
      required this.text,
      this.unreadable,
      required this.width,
      required this.x,
      required this.y})
      : super._();
  @override
  BoundingBoxResponse rebuild(
          void Function(BoundingBoxResponseBuilder) updates) =>
      (toBuilder()..update(updates)).build();

  @override
  BoundingBoxResponseBuilder toBuilder() =>
      BoundingBoxResponseBuilder()..replace(this);

  @override
  bool operator ==(Object other) {
    if (identical(other, this)) return true;
    return other is BoundingBoxResponse &&
        height == other.height &&
        text == other.text &&
        unreadable == other.unreadable &&
        width == other.width &&
        x == other.x &&
        y == other.y;
  }

  @override
  int get hashCode {
    var _$hash = 0;
    _$hash = $jc(_$hash, height.hashCode);
    _$hash = $jc(_$hash, text.hashCode);
    _$hash = $jc(_$hash, unreadable.hashCode);
    _$hash = $jc(_$hash, width.hashCode);
    _$hash = $jc(_$hash, x.hashCode);
    _$hash = $jc(_$hash, y.hashCode);
    _$hash = $jf(_$hash);
    return _$hash;
  }

  @override
  String toString() {
    return (newBuiltValueToStringHelper(r'BoundingBoxResponse')
          ..add('height', height)
          ..add('text', text)
          ..add('unreadable', unreadable)
          ..add('width', width)
          ..add('x', x)
          ..add('y', y))
        .toString();
  }
}

class BoundingBoxResponseBuilder
    implements Builder<BoundingBoxResponse, BoundingBoxResponseBuilder> {
  _$BoundingBoxResponse? _$v;

  num? _height;
  num? get height => _$this._height;
  set height(num? height) => _$this._height = height;

  String? _text;
  String? get text => _$this._text;
  set text(String? text) => _$this._text = text;

  bool? _unreadable;
  bool? get unreadable => _$this._unreadable;
  set unreadable(bool? unreadable) => _$this._unreadable = unreadable;

  num? _width;
  num? get width => _$this._width;
  set width(num? width) => _$this._width = width;

  num? _x;
  num? get x => _$this._x;
  set x(num? x) => _$this._x = x;

  num? _y;
  num? get y => _$this._y;
  set y(num? y) => _$this._y = y;

  BoundingBoxResponseBuilder() {
    BoundingBoxResponse._defaults(this);
  }

  BoundingBoxResponseBuilder get _$this {
    final $v = _$v;
    if ($v != null) {
      _height = $v.height;
      _text = $v.text;
      _unreadable = $v.unreadable;
      _width = $v.width;
      _x = $v.x;
      _y = $v.y;
      _$v = null;
    }
    return this;
  }

  @override
  void replace(BoundingBoxResponse other) {
    _$v = other as _$BoundingBoxResponse;
  }

  @override
  void update(void Function(BoundingBoxResponseBuilder)? updates) {
    if (updates != null) updates(this);
  }

  @override
  BoundingBoxResponse build() => _build();

  _$BoundingBoxResponse _build() {
    final _$result = _$v ??
        _$BoundingBoxResponse._(
          height: BuiltValueNullFieldError.checkNotNull(
              height, r'BoundingBoxResponse', 'height'),
          text: BuiltValueNullFieldError.checkNotNull(
              text, r'BoundingBoxResponse', 'text'),
          unreadable: unreadable,
          width: BuiltValueNullFieldError.checkNotNull(
              width, r'BoundingBoxResponse', 'width'),
          x: BuiltValueNullFieldError.checkNotNull(
              x, r'BoundingBoxResponse', 'x'),
          y: BuiltValueNullFieldError.checkNotNull(
              y, r'BoundingBoxResponse', 'y'),
        );
    replace(_$result);
    return _$result;
  }
}

// ignore_for_file: deprecated_member_use_from_same_package,type=lint
