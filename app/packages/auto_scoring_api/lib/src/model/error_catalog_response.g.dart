// GENERATED CODE - DO NOT MODIFY BY HAND

part of 'error_catalog_response.dart';

// **************************************************************************
// BuiltValueGenerator
// **************************************************************************

class _$ErrorCatalogResponse extends ErrorCatalogResponse {
  @override
  final BuiltList<ErrorCatalogEntryModel> entries;
  @override
  final int entryCount;
  @override
  final String? importError;
  @override
  final bool imported;
  @override
  final int revision;
  @override
  final CatalogState state;
  @override
  final String testId;

  factory _$ErrorCatalogResponse(
          [void Function(ErrorCatalogResponseBuilder)? updates]) =>
      (ErrorCatalogResponseBuilder()..update(updates))._build();

  _$ErrorCatalogResponse._(
      {required this.entries,
      required this.entryCount,
      this.importError,
      required this.imported,
      required this.revision,
      required this.state,
      required this.testId})
      : super._();
  @override
  ErrorCatalogResponse rebuild(
          void Function(ErrorCatalogResponseBuilder) updates) =>
      (toBuilder()..update(updates)).build();

  @override
  ErrorCatalogResponseBuilder toBuilder() =>
      ErrorCatalogResponseBuilder()..replace(this);

  @override
  bool operator ==(Object other) {
    if (identical(other, this)) return true;
    return other is ErrorCatalogResponse &&
        entries == other.entries &&
        entryCount == other.entryCount &&
        importError == other.importError &&
        imported == other.imported &&
        revision == other.revision &&
        state == other.state &&
        testId == other.testId;
  }

  @override
  int get hashCode {
    var _$hash = 0;
    _$hash = $jc(_$hash, entries.hashCode);
    _$hash = $jc(_$hash, entryCount.hashCode);
    _$hash = $jc(_$hash, importError.hashCode);
    _$hash = $jc(_$hash, imported.hashCode);
    _$hash = $jc(_$hash, revision.hashCode);
    _$hash = $jc(_$hash, state.hashCode);
    _$hash = $jc(_$hash, testId.hashCode);
    _$hash = $jf(_$hash);
    return _$hash;
  }

  @override
  String toString() {
    return (newBuiltValueToStringHelper(r'ErrorCatalogResponse')
          ..add('entries', entries)
          ..add('entryCount', entryCount)
          ..add('importError', importError)
          ..add('imported', imported)
          ..add('revision', revision)
          ..add('state', state)
          ..add('testId', testId))
        .toString();
  }
}

class ErrorCatalogResponseBuilder
    implements Builder<ErrorCatalogResponse, ErrorCatalogResponseBuilder> {
  _$ErrorCatalogResponse? _$v;

  ListBuilder<ErrorCatalogEntryModel>? _entries;
  ListBuilder<ErrorCatalogEntryModel> get entries =>
      _$this._entries ??= ListBuilder<ErrorCatalogEntryModel>();
  set entries(ListBuilder<ErrorCatalogEntryModel>? entries) =>
      _$this._entries = entries;

  int? _entryCount;
  int? get entryCount => _$this._entryCount;
  set entryCount(int? entryCount) => _$this._entryCount = entryCount;

  String? _importError;
  String? get importError => _$this._importError;
  set importError(String? importError) => _$this._importError = importError;

  bool? _imported;
  bool? get imported => _$this._imported;
  set imported(bool? imported) => _$this._imported = imported;

  int? _revision;
  int? get revision => _$this._revision;
  set revision(int? revision) => _$this._revision = revision;

  CatalogState? _state;
  CatalogState? get state => _$this._state;
  set state(CatalogState? state) => _$this._state = state;

  String? _testId;
  String? get testId => _$this._testId;
  set testId(String? testId) => _$this._testId = testId;

  ErrorCatalogResponseBuilder() {
    ErrorCatalogResponse._defaults(this);
  }

  ErrorCatalogResponseBuilder get _$this {
    final $v = _$v;
    if ($v != null) {
      _entries = $v.entries.toBuilder();
      _entryCount = $v.entryCount;
      _importError = $v.importError;
      _imported = $v.imported;
      _revision = $v.revision;
      _state = $v.state;
      _testId = $v.testId;
      _$v = null;
    }
    return this;
  }

  @override
  void replace(ErrorCatalogResponse other) {
    _$v = other as _$ErrorCatalogResponse;
  }

  @override
  void update(void Function(ErrorCatalogResponseBuilder)? updates) {
    if (updates != null) updates(this);
  }

  @override
  ErrorCatalogResponse build() => _build();

  _$ErrorCatalogResponse _build() {
    _$ErrorCatalogResponse _$result;
    try {
      _$result = _$v ??
          _$ErrorCatalogResponse._(
            entries: entries.build(),
            entryCount: BuiltValueNullFieldError.checkNotNull(
                entryCount, r'ErrorCatalogResponse', 'entryCount'),
            importError: importError,
            imported: BuiltValueNullFieldError.checkNotNull(
                imported, r'ErrorCatalogResponse', 'imported'),
            revision: BuiltValueNullFieldError.checkNotNull(
                revision, r'ErrorCatalogResponse', 'revision'),
            state: BuiltValueNullFieldError.checkNotNull(
                state, r'ErrorCatalogResponse', 'state'),
            testId: BuiltValueNullFieldError.checkNotNull(
                testId, r'ErrorCatalogResponse', 'testId'),
          );
    } catch (_) {
      late String _$failedField;
      try {
        _$failedField = 'entries';
        entries.build();
      } catch (e) {
        throw BuiltValueNestedFieldError(
            r'ErrorCatalogResponse', _$failedField, e.toString());
      }
      rethrow;
    }
    replace(_$result);
    return _$result;
  }
}

// ignore_for_file: deprecated_member_use_from_same_package,type=lint
