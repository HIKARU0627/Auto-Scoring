// GENERATED CODE - DO NOT MODIFY BY HAND

part of 'document_pages_response.dart';

// **************************************************************************
// BuiltValueGenerator
// **************************************************************************

class _$DocumentPagesResponse extends DocumentPagesResponse {
  @override
  final int pageCount;
  @override
  final BuiltList<PageGeometryResponse> pages;

  factory _$DocumentPagesResponse(
          [void Function(DocumentPagesResponseBuilder)? updates]) =>
      (DocumentPagesResponseBuilder()..update(updates))._build();

  _$DocumentPagesResponse._({required this.pageCount, required this.pages})
      : super._();
  @override
  DocumentPagesResponse rebuild(
          void Function(DocumentPagesResponseBuilder) updates) =>
      (toBuilder()..update(updates)).build();

  @override
  DocumentPagesResponseBuilder toBuilder() =>
      DocumentPagesResponseBuilder()..replace(this);

  @override
  bool operator ==(Object other) {
    if (identical(other, this)) return true;
    return other is DocumentPagesResponse &&
        pageCount == other.pageCount &&
        pages == other.pages;
  }

  @override
  int get hashCode {
    var _$hash = 0;
    _$hash = $jc(_$hash, pageCount.hashCode);
    _$hash = $jc(_$hash, pages.hashCode);
    _$hash = $jf(_$hash);
    return _$hash;
  }

  @override
  String toString() {
    return (newBuiltValueToStringHelper(r'DocumentPagesResponse')
          ..add('pageCount', pageCount)
          ..add('pages', pages))
        .toString();
  }
}

class DocumentPagesResponseBuilder
    implements Builder<DocumentPagesResponse, DocumentPagesResponseBuilder> {
  _$DocumentPagesResponse? _$v;

  int? _pageCount;
  int? get pageCount => _$this._pageCount;
  set pageCount(int? pageCount) => _$this._pageCount = pageCount;

  ListBuilder<PageGeometryResponse>? _pages;
  ListBuilder<PageGeometryResponse> get pages =>
      _$this._pages ??= ListBuilder<PageGeometryResponse>();
  set pages(ListBuilder<PageGeometryResponse>? pages) => _$this._pages = pages;

  DocumentPagesResponseBuilder() {
    DocumentPagesResponse._defaults(this);
  }

  DocumentPagesResponseBuilder get _$this {
    final $v = _$v;
    if ($v != null) {
      _pageCount = $v.pageCount;
      _pages = $v.pages.toBuilder();
      _$v = null;
    }
    return this;
  }

  @override
  void replace(DocumentPagesResponse other) {
    _$v = other as _$DocumentPagesResponse;
  }

  @override
  void update(void Function(DocumentPagesResponseBuilder)? updates) {
    if (updates != null) updates(this);
  }

  @override
  DocumentPagesResponse build() => _build();

  _$DocumentPagesResponse _build() {
    _$DocumentPagesResponse _$result;
    try {
      _$result = _$v ??
          _$DocumentPagesResponse._(
            pageCount: BuiltValueNullFieldError.checkNotNull(
                pageCount, r'DocumentPagesResponse', 'pageCount'),
            pages: pages.build(),
          );
    } catch (_) {
      late String _$failedField;
      try {
        _$failedField = 'pages';
        pages.build();
      } catch (e) {
        throw BuiltValueNestedFieldError(
            r'DocumentPagesResponse', _$failedField, e.toString());
      }
      rethrow;
    }
    replace(_$result);
    return _$result;
  }
}

// ignore_for_file: deprecated_member_use_from_same_package,type=lint
