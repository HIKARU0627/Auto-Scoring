// GENERATED CODE - DO NOT MODIFY BY HAND

part of 'bulk_export_item_response.dart';

// **************************************************************************
// BuiltValueGenerator
// **************************************************************************

class _$BulkExportItemResponse extends BulkExportItemResponse {
  @override
  final ExportResponse? export_;
  @override
  final String? jobId;
  @override
  final String? originalFilename;
  @override
  final ExportRefusalReason? refusalCode;
  @override
  final BuiltList<String>? refusalQuestionIds;
  @override
  final BulkExportItemStatus status;
  @override
  final String submissionId;

  factory _$BulkExportItemResponse(
          [void Function(BulkExportItemResponseBuilder)? updates]) =>
      (BulkExportItemResponseBuilder()..update(updates))._build();

  _$BulkExportItemResponse._(
      {this.export_,
      this.jobId,
      this.originalFilename,
      this.refusalCode,
      this.refusalQuestionIds,
      required this.status,
      required this.submissionId})
      : super._();
  @override
  BulkExportItemResponse rebuild(
          void Function(BulkExportItemResponseBuilder) updates) =>
      (toBuilder()..update(updates)).build();

  @override
  BulkExportItemResponseBuilder toBuilder() =>
      BulkExportItemResponseBuilder()..replace(this);

  @override
  bool operator ==(Object other) {
    if (identical(other, this)) return true;
    return other is BulkExportItemResponse &&
        export_ == other.export_ &&
        jobId == other.jobId &&
        originalFilename == other.originalFilename &&
        refusalCode == other.refusalCode &&
        refusalQuestionIds == other.refusalQuestionIds &&
        status == other.status &&
        submissionId == other.submissionId;
  }

  @override
  int get hashCode {
    var _$hash = 0;
    _$hash = $jc(_$hash, export_.hashCode);
    _$hash = $jc(_$hash, jobId.hashCode);
    _$hash = $jc(_$hash, originalFilename.hashCode);
    _$hash = $jc(_$hash, refusalCode.hashCode);
    _$hash = $jc(_$hash, refusalQuestionIds.hashCode);
    _$hash = $jc(_$hash, status.hashCode);
    _$hash = $jc(_$hash, submissionId.hashCode);
    _$hash = $jf(_$hash);
    return _$hash;
  }

  @override
  String toString() {
    return (newBuiltValueToStringHelper(r'BulkExportItemResponse')
          ..add('export_', export_)
          ..add('jobId', jobId)
          ..add('originalFilename', originalFilename)
          ..add('refusalCode', refusalCode)
          ..add('refusalQuestionIds', refusalQuestionIds)
          ..add('status', status)
          ..add('submissionId', submissionId))
        .toString();
  }
}

class BulkExportItemResponseBuilder
    implements Builder<BulkExportItemResponse, BulkExportItemResponseBuilder> {
  _$BulkExportItemResponse? _$v;

  ExportResponseBuilder? _export_;
  ExportResponseBuilder get export_ =>
      _$this._export_ ??= ExportResponseBuilder();
  set export_(ExportResponseBuilder? export_) => _$this._export_ = export_;

  String? _jobId;
  String? get jobId => _$this._jobId;
  set jobId(String? jobId) => _$this._jobId = jobId;

  String? _originalFilename;
  String? get originalFilename => _$this._originalFilename;
  set originalFilename(String? originalFilename) =>
      _$this._originalFilename = originalFilename;

  ExportRefusalReason? _refusalCode;
  ExportRefusalReason? get refusalCode => _$this._refusalCode;
  set refusalCode(ExportRefusalReason? refusalCode) =>
      _$this._refusalCode = refusalCode;

  ListBuilder<String>? _refusalQuestionIds;
  ListBuilder<String> get refusalQuestionIds =>
      _$this._refusalQuestionIds ??= ListBuilder<String>();
  set refusalQuestionIds(ListBuilder<String>? refusalQuestionIds) =>
      _$this._refusalQuestionIds = refusalQuestionIds;

  BulkExportItemStatus? _status;
  BulkExportItemStatus? get status => _$this._status;
  set status(BulkExportItemStatus? status) => _$this._status = status;

  String? _submissionId;
  String? get submissionId => _$this._submissionId;
  set submissionId(String? submissionId) => _$this._submissionId = submissionId;

  BulkExportItemResponseBuilder() {
    BulkExportItemResponse._defaults(this);
  }

  BulkExportItemResponseBuilder get _$this {
    final $v = _$v;
    if ($v != null) {
      _export_ = $v.export_?.toBuilder();
      _jobId = $v.jobId;
      _originalFilename = $v.originalFilename;
      _refusalCode = $v.refusalCode;
      _refusalQuestionIds = $v.refusalQuestionIds?.toBuilder();
      _status = $v.status;
      _submissionId = $v.submissionId;
      _$v = null;
    }
    return this;
  }

  @override
  void replace(BulkExportItemResponse other) {
    _$v = other as _$BulkExportItemResponse;
  }

  @override
  void update(void Function(BulkExportItemResponseBuilder)? updates) {
    if (updates != null) updates(this);
  }

  @override
  BulkExportItemResponse build() => _build();

  _$BulkExportItemResponse _build() {
    _$BulkExportItemResponse _$result;
    try {
      _$result = _$v ??
          _$BulkExportItemResponse._(
            export_: _export_?.build(),
            jobId: jobId,
            originalFilename: originalFilename,
            refusalCode: refusalCode,
            refusalQuestionIds: _refusalQuestionIds?.build(),
            status: BuiltValueNullFieldError.checkNotNull(
                status, r'BulkExportItemResponse', 'status'),
            submissionId: BuiltValueNullFieldError.checkNotNull(
                submissionId, r'BulkExportItemResponse', 'submissionId'),
          );
    } catch (_) {
      late String _$failedField;
      try {
        _$failedField = 'export_';
        _export_?.build();

        _$failedField = 'refusalQuestionIds';
        _refusalQuestionIds?.build();
      } catch (e) {
        throw BuiltValueNestedFieldError(
            r'BulkExportItemResponse', _$failedField, e.toString());
      }
      rethrow;
    }
    replace(_$result);
    return _$result;
  }
}

// ignore_for_file: deprecated_member_use_from_same_package,type=lint
