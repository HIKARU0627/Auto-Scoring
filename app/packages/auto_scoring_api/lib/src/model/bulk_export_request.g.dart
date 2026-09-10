// GENERATED CODE - DO NOT MODIFY BY HAND

part of 'bulk_export_request.dart';

// **************************************************************************
// BuiltValueGenerator
// **************************************************************************

class _$BulkExportRequest extends BulkExportRequest {
  @override
  final BuiltList<String>? submissionIds;

  factory _$BulkExportRequest(
          [void Function(BulkExportRequestBuilder)? updates]) =>
      (BulkExportRequestBuilder()..update(updates))._build();

  _$BulkExportRequest._({this.submissionIds}) : super._();
  @override
  BulkExportRequest rebuild(void Function(BulkExportRequestBuilder) updates) =>
      (toBuilder()..update(updates)).build();

  @override
  BulkExportRequestBuilder toBuilder() =>
      BulkExportRequestBuilder()..replace(this);

  @override
  bool operator ==(Object other) {
    if (identical(other, this)) return true;
    return other is BulkExportRequest && submissionIds == other.submissionIds;
  }

  @override
  int get hashCode {
    var _$hash = 0;
    _$hash = $jc(_$hash, submissionIds.hashCode);
    _$hash = $jf(_$hash);
    return _$hash;
  }

  @override
  String toString() {
    return (newBuiltValueToStringHelper(r'BulkExportRequest')
          ..add('submissionIds', submissionIds))
        .toString();
  }
}

class BulkExportRequestBuilder
    implements Builder<BulkExportRequest, BulkExportRequestBuilder> {
  _$BulkExportRequest? _$v;

  ListBuilder<String>? _submissionIds;
  ListBuilder<String> get submissionIds =>
      _$this._submissionIds ??= ListBuilder<String>();
  set submissionIds(ListBuilder<String>? submissionIds) =>
      _$this._submissionIds = submissionIds;

  BulkExportRequestBuilder() {
    BulkExportRequest._defaults(this);
  }

  BulkExportRequestBuilder get _$this {
    final $v = _$v;
    if ($v != null) {
      _submissionIds = $v.submissionIds?.toBuilder();
      _$v = null;
    }
    return this;
  }

  @override
  void replace(BulkExportRequest other) {
    _$v = other as _$BulkExportRequest;
  }

  @override
  void update(void Function(BulkExportRequestBuilder)? updates) {
    if (updates != null) updates(this);
  }

  @override
  BulkExportRequest build() => _build();

  _$BulkExportRequest _build() {
    _$BulkExportRequest _$result;
    try {
      _$result = _$v ??
          _$BulkExportRequest._(
            submissionIds: _submissionIds?.build(),
          );
    } catch (_) {
      late String _$failedField;
      try {
        _$failedField = 'submissionIds';
        _submissionIds?.build();
      } catch (e) {
        throw BuiltValueNestedFieldError(
            r'BulkExportRequest', _$failedField, e.toString());
      }
      rethrow;
    }
    replace(_$result);
    return _$result;
  }
}

// ignore_for_file: deprecated_member_use_from_same_package,type=lint
