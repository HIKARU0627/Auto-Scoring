// GENERATED CODE - DO NOT MODIFY BY HAND

part of 'page_geometry_response.dart';

// **************************************************************************
// BuiltValueGenerator
// **************************************************************************

class _$PageGeometryResponse extends PageGeometryResponse {
  @override
  final num displayedHeight;
  @override
  final num displayedWidth;
  @override
  final int pageIndex;
  @override
  final int rotation;

  factory _$PageGeometryResponse(
          [void Function(PageGeometryResponseBuilder)? updates]) =>
      (PageGeometryResponseBuilder()..update(updates))._build();

  _$PageGeometryResponse._(
      {required this.displayedHeight,
      required this.displayedWidth,
      required this.pageIndex,
      required this.rotation})
      : super._();
  @override
  PageGeometryResponse rebuild(
          void Function(PageGeometryResponseBuilder) updates) =>
      (toBuilder()..update(updates)).build();

  @override
  PageGeometryResponseBuilder toBuilder() =>
      PageGeometryResponseBuilder()..replace(this);

  @override
  bool operator ==(Object other) {
    if (identical(other, this)) return true;
    return other is PageGeometryResponse &&
        displayedHeight == other.displayedHeight &&
        displayedWidth == other.displayedWidth &&
        pageIndex == other.pageIndex &&
        rotation == other.rotation;
  }

  @override
  int get hashCode {
    var _$hash = 0;
    _$hash = $jc(_$hash, displayedHeight.hashCode);
    _$hash = $jc(_$hash, displayedWidth.hashCode);
    _$hash = $jc(_$hash, pageIndex.hashCode);
    _$hash = $jc(_$hash, rotation.hashCode);
    _$hash = $jf(_$hash);
    return _$hash;
  }

  @override
  String toString() {
    return (newBuiltValueToStringHelper(r'PageGeometryResponse')
          ..add('displayedHeight', displayedHeight)
          ..add('displayedWidth', displayedWidth)
          ..add('pageIndex', pageIndex)
          ..add('rotation', rotation))
        .toString();
  }
}

class PageGeometryResponseBuilder
    implements Builder<PageGeometryResponse, PageGeometryResponseBuilder> {
  _$PageGeometryResponse? _$v;

  num? _displayedHeight;
  num? get displayedHeight => _$this._displayedHeight;
  set displayedHeight(num? displayedHeight) =>
      _$this._displayedHeight = displayedHeight;

  num? _displayedWidth;
  num? get displayedWidth => _$this._displayedWidth;
  set displayedWidth(num? displayedWidth) =>
      _$this._displayedWidth = displayedWidth;

  int? _pageIndex;
  int? get pageIndex => _$this._pageIndex;
  set pageIndex(int? pageIndex) => _$this._pageIndex = pageIndex;

  int? _rotation;
  int? get rotation => _$this._rotation;
  set rotation(int? rotation) => _$this._rotation = rotation;

  PageGeometryResponseBuilder() {
    PageGeometryResponse._defaults(this);
  }

  PageGeometryResponseBuilder get _$this {
    final $v = _$v;
    if ($v != null) {
      _displayedHeight = $v.displayedHeight;
      _displayedWidth = $v.displayedWidth;
      _pageIndex = $v.pageIndex;
      _rotation = $v.rotation;
      _$v = null;
    }
    return this;
  }

  @override
  void replace(PageGeometryResponse other) {
    _$v = other as _$PageGeometryResponse;
  }

  @override
  void update(void Function(PageGeometryResponseBuilder)? updates) {
    if (updates != null) updates(this);
  }

  @override
  PageGeometryResponse build() => _build();

  _$PageGeometryResponse _build() {
    final _$result = _$v ??
        _$PageGeometryResponse._(
          displayedHeight: BuiltValueNullFieldError.checkNotNull(
              displayedHeight, r'PageGeometryResponse', 'displayedHeight'),
          displayedWidth: BuiltValueNullFieldError.checkNotNull(
              displayedWidth, r'PageGeometryResponse', 'displayedWidth'),
          pageIndex: BuiltValueNullFieldError.checkNotNull(
              pageIndex, r'PageGeometryResponse', 'pageIndex'),
          rotation: BuiltValueNullFieldError.checkNotNull(
              rotation, r'PageGeometryResponse', 'rotation'),
        );
    replace(_$result);
    return _$result;
  }
}

// ignore_for_file: deprecated_member_use_from_same_package,type=lint
