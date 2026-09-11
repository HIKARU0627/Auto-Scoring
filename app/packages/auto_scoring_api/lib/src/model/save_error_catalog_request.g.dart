// GENERATED CODE - DO NOT MODIFY BY HAND

part of 'save_error_catalog_request.dart';

// **************************************************************************
// BuiltValueGenerator
// **************************************************************************

class _$SaveErrorCatalogRequest extends SaveErrorCatalogRequest {
  @override
  final BuiltList<ErrorCatalogEntryInput> entries;
  @override
  final int revision;

  factory _$SaveErrorCatalogRequest(
          [void Function(SaveErrorCatalogRequestBuilder)? updates]) =>
      (SaveErrorCatalogRequestBuilder()..update(updates))._build();

  _$SaveErrorCatalogRequest._({required this.entries, required this.revision})
      : super._();
  @override
  SaveErrorCatalogRequest rebuild(
          void Function(SaveErrorCatalogRequestBuilder) updates) =>
      (toBuilder()..update(updates)).build();

  @override
  SaveErrorCatalogRequestBuilder toBuilder() =>
      SaveErrorCatalogRequestBuilder()..replace(this);

  @override
  bool operator ==(Object other) {
    if (identical(other, this)) return true;
    return other is SaveErrorCatalogRequest &&
        entries == other.entries &&
        revision == other.revision;
  }

  @override
  int get hashCode {
    var _$hash = 0;
    _$hash = $jc(_$hash, entries.hashCode);
    _$hash = $jc(_$hash, revision.hashCode);
    _$hash = $jf(_$hash);
    return _$hash;
  }

  @override
  String toString() {
    return (newBuiltValueToStringHelper(r'SaveErrorCatalogRequest')
          ..add('entries', entries)
          ..add('revision', revision))
        .toString();
  }
}

class SaveErrorCatalogRequestBuilder
    implements
        Builder<SaveErrorCatalogRequest, SaveErrorCatalogRequestBuilder> {
  _$SaveErrorCatalogRequest? _$v;

  ListBuilder<ErrorCatalogEntryInput>? _entries;
  ListBuilder<ErrorCatalogEntryInput> get entries =>
      _$this._entries ??= ListBuilder<ErrorCatalogEntryInput>();
  set entries(ListBuilder<ErrorCatalogEntryInput>? entries) =>
      _$this._entries = entries;

  int? _revision;
  int? get revision => _$this._revision;
  set revision(int? revision) => _$this._revision = revision;

  SaveErrorCatalogRequestBuilder() {
    SaveErrorCatalogRequest._defaults(this);
  }

  SaveErrorCatalogRequestBuilder get _$this {
    final $v = _$v;
    if ($v != null) {
      _entries = $v.entries.toBuilder();
      _revision = $v.revision;
      _$v = null;
    }
    return this;
  }

  @override
  void replace(SaveErrorCatalogRequest other) {
    _$v = other as _$SaveErrorCatalogRequest;
  }

  @override
  void update(void Function(SaveErrorCatalogRequestBuilder)? updates) {
    if (updates != null) updates(this);
  }

  @override
  SaveErrorCatalogRequest build() => _build();

  _$SaveErrorCatalogRequest _build() {
    _$SaveErrorCatalogRequest _$result;
    try {
      _$result = _$v ??
          _$SaveErrorCatalogRequest._(
            entries: entries.build(),
            revision: BuiltValueNullFieldError.checkNotNull(
                revision, r'SaveErrorCatalogRequest', 'revision'),
          );
    } catch (_) {
      late String _$failedField;
      try {
        _$failedField = 'entries';
        entries.build();
      } catch (e) {
        throw BuiltValueNestedFieldError(
            r'SaveErrorCatalogRequest', _$failedField, e.toString());
      }
      rethrow;
    }
    replace(_$result);
    return _$result;
  }
}

// ignore_for_file: deprecated_member_use_from_same_package,type=lint
