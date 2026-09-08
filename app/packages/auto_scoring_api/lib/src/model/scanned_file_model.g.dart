// GENERATED CODE - DO NOT MODIFY BY HAND

part of 'scanned_file_model.dart';

// **************************************************************************
// BuiltValueGenerator
// **************************************************************************

class _$ScannedFileModel extends ScannedFileModel {
  @override
  final String relativePath;
  @override
  final String sha256;
  @override
  final int sizeBytes;

  factory _$ScannedFileModel(
          [void Function(ScannedFileModelBuilder)? updates]) =>
      (ScannedFileModelBuilder()..update(updates))._build();

  _$ScannedFileModel._(
      {required this.relativePath,
      required this.sha256,
      required this.sizeBytes})
      : super._();
  @override
  ScannedFileModel rebuild(void Function(ScannedFileModelBuilder) updates) =>
      (toBuilder()..update(updates)).build();

  @override
  ScannedFileModelBuilder toBuilder() =>
      ScannedFileModelBuilder()..replace(this);

  @override
  bool operator ==(Object other) {
    if (identical(other, this)) return true;
    return other is ScannedFileModel &&
        relativePath == other.relativePath &&
        sha256 == other.sha256 &&
        sizeBytes == other.sizeBytes;
  }

  @override
  int get hashCode {
    var _$hash = 0;
    _$hash = $jc(_$hash, relativePath.hashCode);
    _$hash = $jc(_$hash, sha256.hashCode);
    _$hash = $jc(_$hash, sizeBytes.hashCode);
    _$hash = $jf(_$hash);
    return _$hash;
  }

  @override
  String toString() {
    return (newBuiltValueToStringHelper(r'ScannedFileModel')
          ..add('relativePath', relativePath)
          ..add('sha256', sha256)
          ..add('sizeBytes', sizeBytes))
        .toString();
  }
}

class ScannedFileModelBuilder
    implements Builder<ScannedFileModel, ScannedFileModelBuilder> {
  _$ScannedFileModel? _$v;

  String? _relativePath;
  String? get relativePath => _$this._relativePath;
  set relativePath(String? relativePath) => _$this._relativePath = relativePath;

  String? _sha256;
  String? get sha256 => _$this._sha256;
  set sha256(String? sha256) => _$this._sha256 = sha256;

  int? _sizeBytes;
  int? get sizeBytes => _$this._sizeBytes;
  set sizeBytes(int? sizeBytes) => _$this._sizeBytes = sizeBytes;

  ScannedFileModelBuilder() {
    ScannedFileModel._defaults(this);
  }

  ScannedFileModelBuilder get _$this {
    final $v = _$v;
    if ($v != null) {
      _relativePath = $v.relativePath;
      _sha256 = $v.sha256;
      _sizeBytes = $v.sizeBytes;
      _$v = null;
    }
    return this;
  }

  @override
  void replace(ScannedFileModel other) {
    _$v = other as _$ScannedFileModel;
  }

  @override
  void update(void Function(ScannedFileModelBuilder)? updates) {
    if (updates != null) updates(this);
  }

  @override
  ScannedFileModel build() => _build();

  _$ScannedFileModel _build() {
    final _$result = _$v ??
        _$ScannedFileModel._(
          relativePath: BuiltValueNullFieldError.checkNotNull(
              relativePath, r'ScannedFileModel', 'relativePath'),
          sha256: BuiltValueNullFieldError.checkNotNull(
              sha256, r'ScannedFileModel', 'sha256'),
          sizeBytes: BuiltValueNullFieldError.checkNotNull(
              sizeBytes, r'ScannedFileModel', 'sizeBytes'),
        );
    replace(_$result);
    return _$result;
  }
}

// ignore_for_file: deprecated_member_use_from_same_package,type=lint
