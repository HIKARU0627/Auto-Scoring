// GENERATED CODE - DO NOT MODIFY BY HAND

part of 'bulk_export_response.dart';

// **************************************************************************
// BuiltValueGenerator
// **************************************************************************

class _$BulkExportResponse extends BulkExportResponse {
  @override
  final BuiltList<BulkExportItemResponse> items;
  @override
  final String testId;

  factory _$BulkExportResponse(
          [void Function(BulkExportResponseBuilder)? updates]) =>
      (BulkExportResponseBuilder()..update(updates))._build();

  _$BulkExportResponse._({required this.items, required this.testId})
      : super._();
  @override
  BulkExportResponse rebuild(
          void Function(BulkExportResponseBuilder) updates) =>
      (toBuilder()..update(updates)).build();

  @override
  BulkExportResponseBuilder toBuilder() =>
      BulkExportResponseBuilder()..replace(this);

  @override
  bool operator ==(Object other) {
    if (identical(other, this)) return true;
    return other is BulkExportResponse &&
        items == other.items &&
        testId == other.testId;
  }

  @override
  int get hashCode {
    var _$hash = 0;
    _$hash = $jc(_$hash, items.hashCode);
    _$hash = $jc(_$hash, testId.hashCode);
    _$hash = $jf(_$hash);
    return _$hash;
  }

  @override
  String toString() {
    return (newBuiltValueToStringHelper(r'BulkExportResponse')
          ..add('items', items)
          ..add('testId', testId))
        .toString();
  }
}

class BulkExportResponseBuilder
    implements Builder<BulkExportResponse, BulkExportResponseBuilder> {
  _$BulkExportResponse? _$v;

  ListBuilder<BulkExportItemResponse>? _items;
  ListBuilder<BulkExportItemResponse> get items =>
      _$this._items ??= ListBuilder<BulkExportItemResponse>();
  set items(ListBuilder<BulkExportItemResponse>? items) =>
      _$this._items = items;

  String? _testId;
  String? get testId => _$this._testId;
  set testId(String? testId) => _$this._testId = testId;

  BulkExportResponseBuilder() {
    BulkExportResponse._defaults(this);
  }

  BulkExportResponseBuilder get _$this {
    final $v = _$v;
    if ($v != null) {
      _items = $v.items.toBuilder();
      _testId = $v.testId;
      _$v = null;
    }
    return this;
  }

  @override
  void replace(BulkExportResponse other) {
    _$v = other as _$BulkExportResponse;
  }

  @override
  void update(void Function(BulkExportResponseBuilder)? updates) {
    if (updates != null) updates(this);
  }

  @override
  BulkExportResponse build() => _build();

  _$BulkExportResponse _build() {
    _$BulkExportResponse _$result;
    try {
      _$result = _$v ??
          _$BulkExportResponse._(
            items: items.build(),
            testId: BuiltValueNullFieldError.checkNotNull(
                testId, r'BulkExportResponse', 'testId'),
          );
    } catch (_) {
      late String _$failedField;
      try {
        _$failedField = 'items';
        items.build();
      } catch (e) {
        throw BuiltValueNestedFieldError(
            r'BulkExportResponse', _$failedField, e.toString());
      }
      rethrow;
    }
    replace(_$result);
    return _$result;
  }
}

// ignore_for_file: deprecated_member_use_from_same_package,type=lint
