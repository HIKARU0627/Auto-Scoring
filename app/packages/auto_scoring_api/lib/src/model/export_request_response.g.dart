// GENERATED CODE - DO NOT MODIFY BY HAND

part of 'export_request_response.dart';

// **************************************************************************
// BuiltValueGenerator
// **************************************************************************

class _$ExportRequestResponse extends ExportRequestResponse {
  @override
  final String decision;
  @override
  final ExportResponse? export_;
  @override
  final String? jobId;

  factory _$ExportRequestResponse(
          [void Function(ExportRequestResponseBuilder)? updates]) =>
      (ExportRequestResponseBuilder()..update(updates))._build();

  _$ExportRequestResponse._({required this.decision, this.export_, this.jobId})
      : super._();
  @override
  ExportRequestResponse rebuild(
          void Function(ExportRequestResponseBuilder) updates) =>
      (toBuilder()..update(updates)).build();

  @override
  ExportRequestResponseBuilder toBuilder() =>
      ExportRequestResponseBuilder()..replace(this);

  @override
  bool operator ==(Object other) {
    if (identical(other, this)) return true;
    return other is ExportRequestResponse &&
        decision == other.decision &&
        export_ == other.export_ &&
        jobId == other.jobId;
  }

  @override
  int get hashCode {
    var _$hash = 0;
    _$hash = $jc(_$hash, decision.hashCode);
    _$hash = $jc(_$hash, export_.hashCode);
    _$hash = $jc(_$hash, jobId.hashCode);
    _$hash = $jf(_$hash);
    return _$hash;
  }

  @override
  String toString() {
    return (newBuiltValueToStringHelper(r'ExportRequestResponse')
          ..add('decision', decision)
          ..add('export_', export_)
          ..add('jobId', jobId))
        .toString();
  }
}

class ExportRequestResponseBuilder
    implements Builder<ExportRequestResponse, ExportRequestResponseBuilder> {
  _$ExportRequestResponse? _$v;

  String? _decision;
  String? get decision => _$this._decision;
  set decision(String? decision) => _$this._decision = decision;

  ExportResponseBuilder? _export_;
  ExportResponseBuilder get export_ =>
      _$this._export_ ??= ExportResponseBuilder();
  set export_(ExportResponseBuilder? export_) => _$this._export_ = export_;

  String? _jobId;
  String? get jobId => _$this._jobId;
  set jobId(String? jobId) => _$this._jobId = jobId;

  ExportRequestResponseBuilder() {
    ExportRequestResponse._defaults(this);
  }

  ExportRequestResponseBuilder get _$this {
    final $v = _$v;
    if ($v != null) {
      _decision = $v.decision;
      _export_ = $v.export_?.toBuilder();
      _jobId = $v.jobId;
      _$v = null;
    }
    return this;
  }

  @override
  void replace(ExportRequestResponse other) {
    _$v = other as _$ExportRequestResponse;
  }

  @override
  void update(void Function(ExportRequestResponseBuilder)? updates) {
    if (updates != null) updates(this);
  }

  @override
  ExportRequestResponse build() => _build();

  _$ExportRequestResponse _build() {
    _$ExportRequestResponse _$result;
    try {
      _$result = _$v ??
          _$ExportRequestResponse._(
            decision: BuiltValueNullFieldError.checkNotNull(
                decision, r'ExportRequestResponse', 'decision'),
            export_: _export_?.build(),
            jobId: jobId,
          );
    } catch (_) {
      late String _$failedField;
      try {
        _$failedField = 'export_';
        _export_?.build();
      } catch (e) {
        throw BuiltValueNestedFieldError(
            r'ExportRequestResponse', _$failedField, e.toString());
      }
      rethrow;
    }
    replace(_$result);
    return _$result;
  }
}

// ignore_for_file: deprecated_member_use_from_same_package,type=lint
