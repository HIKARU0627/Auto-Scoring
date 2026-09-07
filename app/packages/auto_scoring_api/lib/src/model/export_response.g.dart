// GENERATED CODE - DO NOT MODIFY BY HAND

part of 'export_response.dart';

// **************************************************************************
// BuiltValueGenerator
// **************************************************************************

class _$ExportResponse extends ExportResponse {
  @override
  final DateTime createdAt;
  @override
  final String filePath;
  @override
  final String fileSha256;
  @override
  final String id;
  @override
  final String jobId;
  @override
  final String submissionId;

  factory _$ExportResponse([void Function(ExportResponseBuilder)? updates]) =>
      (ExportResponseBuilder()..update(updates))._build();

  _$ExportResponse._(
      {required this.createdAt,
      required this.filePath,
      required this.fileSha256,
      required this.id,
      required this.jobId,
      required this.submissionId})
      : super._();
  @override
  ExportResponse rebuild(void Function(ExportResponseBuilder) updates) =>
      (toBuilder()..update(updates)).build();

  @override
  ExportResponseBuilder toBuilder() => ExportResponseBuilder()..replace(this);

  @override
  bool operator ==(Object other) {
    if (identical(other, this)) return true;
    return other is ExportResponse &&
        createdAt == other.createdAt &&
        filePath == other.filePath &&
        fileSha256 == other.fileSha256 &&
        id == other.id &&
        jobId == other.jobId &&
        submissionId == other.submissionId;
  }

  @override
  int get hashCode {
    var _$hash = 0;
    _$hash = $jc(_$hash, createdAt.hashCode);
    _$hash = $jc(_$hash, filePath.hashCode);
    _$hash = $jc(_$hash, fileSha256.hashCode);
    _$hash = $jc(_$hash, id.hashCode);
    _$hash = $jc(_$hash, jobId.hashCode);
    _$hash = $jc(_$hash, submissionId.hashCode);
    _$hash = $jf(_$hash);
    return _$hash;
  }

  @override
  String toString() {
    return (newBuiltValueToStringHelper(r'ExportResponse')
          ..add('createdAt', createdAt)
          ..add('filePath', filePath)
          ..add('fileSha256', fileSha256)
          ..add('id', id)
          ..add('jobId', jobId)
          ..add('submissionId', submissionId))
        .toString();
  }
}

class ExportResponseBuilder
    implements Builder<ExportResponse, ExportResponseBuilder> {
  _$ExportResponse? _$v;

  DateTime? _createdAt;
  DateTime? get createdAt => _$this._createdAt;
  set createdAt(DateTime? createdAt) => _$this._createdAt = createdAt;

  String? _filePath;
  String? get filePath => _$this._filePath;
  set filePath(String? filePath) => _$this._filePath = filePath;

  String? _fileSha256;
  String? get fileSha256 => _$this._fileSha256;
  set fileSha256(String? fileSha256) => _$this._fileSha256 = fileSha256;

  String? _id;
  String? get id => _$this._id;
  set id(String? id) => _$this._id = id;

  String? _jobId;
  String? get jobId => _$this._jobId;
  set jobId(String? jobId) => _$this._jobId = jobId;

  String? _submissionId;
  String? get submissionId => _$this._submissionId;
  set submissionId(String? submissionId) => _$this._submissionId = submissionId;

  ExportResponseBuilder() {
    ExportResponse._defaults(this);
  }

  ExportResponseBuilder get _$this {
    final $v = _$v;
    if ($v != null) {
      _createdAt = $v.createdAt;
      _filePath = $v.filePath;
      _fileSha256 = $v.fileSha256;
      _id = $v.id;
      _jobId = $v.jobId;
      _submissionId = $v.submissionId;
      _$v = null;
    }
    return this;
  }

  @override
  void replace(ExportResponse other) {
    _$v = other as _$ExportResponse;
  }

  @override
  void update(void Function(ExportResponseBuilder)? updates) {
    if (updates != null) updates(this);
  }

  @override
  ExportResponse build() => _build();

  _$ExportResponse _build() {
    final _$result = _$v ??
        _$ExportResponse._(
          createdAt: BuiltValueNullFieldError.checkNotNull(
              createdAt, r'ExportResponse', 'createdAt'),
          filePath: BuiltValueNullFieldError.checkNotNull(
              filePath, r'ExportResponse', 'filePath'),
          fileSha256: BuiltValueNullFieldError.checkNotNull(
              fileSha256, r'ExportResponse', 'fileSha256'),
          id: BuiltValueNullFieldError.checkNotNull(
              id, r'ExportResponse', 'id'),
          jobId: BuiltValueNullFieldError.checkNotNull(
              jobId, r'ExportResponse', 'jobId'),
          submissionId: BuiltValueNullFieldError.checkNotNull(
              submissionId, r'ExportResponse', 'submissionId'),
        );
    replace(_$result);
    return _$result;
  }
}

// ignore_for_file: deprecated_member_use_from_same_package,type=lint
