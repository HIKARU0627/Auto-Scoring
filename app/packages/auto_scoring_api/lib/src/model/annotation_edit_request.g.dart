// GENERATED CODE - DO NOT MODIFY BY HAND

part of 'annotation_edit_request.dart';

// **************************************************************************
// BuiltValueGenerator
// **************************************************************************

class _$AnnotationEditRequest extends AnnotationEditRequest {
  @override
  final String? anchorText;
  @override
  final String? comment;
  @override
  final num? height;
  @override
  final String kind;
  @override
  final num? width;
  @override
  final num? x;
  @override
  final num? y;

  factory _$AnnotationEditRequest(
          [void Function(AnnotationEditRequestBuilder)? updates]) =>
      (AnnotationEditRequestBuilder()..update(updates))._build();

  _$AnnotationEditRequest._(
      {this.anchorText,
      this.comment,
      this.height,
      required this.kind,
      this.width,
      this.x,
      this.y})
      : super._();
  @override
  AnnotationEditRequest rebuild(
          void Function(AnnotationEditRequestBuilder) updates) =>
      (toBuilder()..update(updates)).build();

  @override
  AnnotationEditRequestBuilder toBuilder() =>
      AnnotationEditRequestBuilder()..replace(this);

  @override
  bool operator ==(Object other) {
    if (identical(other, this)) return true;
    return other is AnnotationEditRequest &&
        anchorText == other.anchorText &&
        comment == other.comment &&
        height == other.height &&
        kind == other.kind &&
        width == other.width &&
        x == other.x &&
        y == other.y;
  }

  @override
  int get hashCode {
    var _$hash = 0;
    _$hash = $jc(_$hash, anchorText.hashCode);
    _$hash = $jc(_$hash, comment.hashCode);
    _$hash = $jc(_$hash, height.hashCode);
    _$hash = $jc(_$hash, kind.hashCode);
    _$hash = $jc(_$hash, width.hashCode);
    _$hash = $jc(_$hash, x.hashCode);
    _$hash = $jc(_$hash, y.hashCode);
    _$hash = $jf(_$hash);
    return _$hash;
  }

  @override
  String toString() {
    return (newBuiltValueToStringHelper(r'AnnotationEditRequest')
          ..add('anchorText', anchorText)
          ..add('comment', comment)
          ..add('height', height)
          ..add('kind', kind)
          ..add('width', width)
          ..add('x', x)
          ..add('y', y))
        .toString();
  }
}

class AnnotationEditRequestBuilder
    implements Builder<AnnotationEditRequest, AnnotationEditRequestBuilder> {
  _$AnnotationEditRequest? _$v;

  String? _anchorText;
  String? get anchorText => _$this._anchorText;
  set anchorText(String? anchorText) => _$this._anchorText = anchorText;

  String? _comment;
  String? get comment => _$this._comment;
  set comment(String? comment) => _$this._comment = comment;

  num? _height;
  num? get height => _$this._height;
  set height(num? height) => _$this._height = height;

  String? _kind;
  String? get kind => _$this._kind;
  set kind(String? kind) => _$this._kind = kind;

  num? _width;
  num? get width => _$this._width;
  set width(num? width) => _$this._width = width;

  num? _x;
  num? get x => _$this._x;
  set x(num? x) => _$this._x = x;

  num? _y;
  num? get y => _$this._y;
  set y(num? y) => _$this._y = y;

  AnnotationEditRequestBuilder() {
    AnnotationEditRequest._defaults(this);
  }

  AnnotationEditRequestBuilder get _$this {
    final $v = _$v;
    if ($v != null) {
      _anchorText = $v.anchorText;
      _comment = $v.comment;
      _height = $v.height;
      _kind = $v.kind;
      _width = $v.width;
      _x = $v.x;
      _y = $v.y;
      _$v = null;
    }
    return this;
  }

  @override
  void replace(AnnotationEditRequest other) {
    _$v = other as _$AnnotationEditRequest;
  }

  @override
  void update(void Function(AnnotationEditRequestBuilder)? updates) {
    if (updates != null) updates(this);
  }

  @override
  AnnotationEditRequest build() => _build();

  _$AnnotationEditRequest _build() {
    final _$result = _$v ??
        _$AnnotationEditRequest._(
          anchorText: anchorText,
          comment: comment,
          height: height,
          kind: BuiltValueNullFieldError.checkNotNull(
              kind, r'AnnotationEditRequest', 'kind'),
          width: width,
          x: x,
          y: y,
        );
    replace(_$result);
    return _$result;
  }
}

// ignore_for_file: deprecated_member_use_from_same_package,type=lint
