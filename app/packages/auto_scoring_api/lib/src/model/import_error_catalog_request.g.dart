// GENERATED CODE - DO NOT MODIFY BY HAND

part of 'import_error_catalog_request.dart';

// **************************************************************************
// BuiltValueGenerator
// **************************************************************************

class _$ImportErrorCatalogRequest extends ImportErrorCatalogRequest {
  @override
  final ImportConflictPolicy onConflict;

  factory _$ImportErrorCatalogRequest(
          [void Function(ImportErrorCatalogRequestBuilder)? updates]) =>
      (ImportErrorCatalogRequestBuilder()..update(updates))._build();

  _$ImportErrorCatalogRequest._({required this.onConflict}) : super._();
  @override
  ImportErrorCatalogRequest rebuild(
          void Function(ImportErrorCatalogRequestBuilder) updates) =>
      (toBuilder()..update(updates)).build();

  @override
  ImportErrorCatalogRequestBuilder toBuilder() =>
      ImportErrorCatalogRequestBuilder()..replace(this);

  @override
  bool operator ==(Object other) {
    if (identical(other, this)) return true;
    return other is ImportErrorCatalogRequest && onConflict == other.onConflict;
  }

  @override
  int get hashCode {
    var _$hash = 0;
    _$hash = $jc(_$hash, onConflict.hashCode);
    _$hash = $jf(_$hash);
    return _$hash;
  }

  @override
  String toString() {
    return (newBuiltValueToStringHelper(r'ImportErrorCatalogRequest')
          ..add('onConflict', onConflict))
        .toString();
  }
}

class ImportErrorCatalogRequestBuilder
    implements
        Builder<ImportErrorCatalogRequest, ImportErrorCatalogRequestBuilder> {
  _$ImportErrorCatalogRequest? _$v;

  ImportConflictPolicy? _onConflict;
  ImportConflictPolicy? get onConflict => _$this._onConflict;
  set onConflict(ImportConflictPolicy? onConflict) =>
      _$this._onConflict = onConflict;

  ImportErrorCatalogRequestBuilder() {
    ImportErrorCatalogRequest._defaults(this);
  }

  ImportErrorCatalogRequestBuilder get _$this {
    final $v = _$v;
    if ($v != null) {
      _onConflict = $v.onConflict;
      _$v = null;
    }
    return this;
  }

  @override
  void replace(ImportErrorCatalogRequest other) {
    _$v = other as _$ImportErrorCatalogRequest;
  }

  @override
  void update(void Function(ImportErrorCatalogRequestBuilder)? updates) {
    if (updates != null) updates(this);
  }

  @override
  ImportErrorCatalogRequest build() => _build();

  _$ImportErrorCatalogRequest _build() {
    final _$result = _$v ??
        _$ImportErrorCatalogRequest._(
          onConflict: BuiltValueNullFieldError.checkNotNull(
              onConflict, r'ImportErrorCatalogRequest', 'onConflict'),
        );
    replace(_$result);
    return _$result;
  }
}

// ignore_for_file: deprecated_member_use_from_same_package,type=lint
