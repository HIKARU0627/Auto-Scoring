// GENERATED CODE - DO NOT MODIFY BY HAND

part of 'planned_file_model.dart';

// **************************************************************************
// BuiltValueGenerator
// **************************************************************************

class _$PlannedFileModel extends PlannedFileModel {
  @override
  final ClassificationNeed classification;
  @override
  final String relativePath;
  @override
  final MaterialRole? role;
  @override
  final RoleSource roleSource;
  @override
  final String sha256;
  @override
  final int sizeBytes;

  factory _$PlannedFileModel(
          [void Function(PlannedFileModelBuilder)? updates]) =>
      (PlannedFileModelBuilder()..update(updates))._build();

  _$PlannedFileModel._(
      {required this.classification,
      required this.relativePath,
      this.role,
      required this.roleSource,
      required this.sha256,
      required this.sizeBytes})
      : super._();
  @override
  PlannedFileModel rebuild(void Function(PlannedFileModelBuilder) updates) =>
      (toBuilder()..update(updates)).build();

  @override
  PlannedFileModelBuilder toBuilder() =>
      PlannedFileModelBuilder()..replace(this);

  @override
  bool operator ==(Object other) {
    if (identical(other, this)) return true;
    return other is PlannedFileModel &&
        classification == other.classification &&
        relativePath == other.relativePath &&
        role == other.role &&
        roleSource == other.roleSource &&
        sha256 == other.sha256 &&
        sizeBytes == other.sizeBytes;
  }

  @override
  int get hashCode {
    var _$hash = 0;
    _$hash = $jc(_$hash, classification.hashCode);
    _$hash = $jc(_$hash, relativePath.hashCode);
    _$hash = $jc(_$hash, role.hashCode);
    _$hash = $jc(_$hash, roleSource.hashCode);
    _$hash = $jc(_$hash, sha256.hashCode);
    _$hash = $jc(_$hash, sizeBytes.hashCode);
    _$hash = $jf(_$hash);
    return _$hash;
  }

  @override
  String toString() {
    return (newBuiltValueToStringHelper(r'PlannedFileModel')
          ..add('classification', classification)
          ..add('relativePath', relativePath)
          ..add('role', role)
          ..add('roleSource', roleSource)
          ..add('sha256', sha256)
          ..add('sizeBytes', sizeBytes))
        .toString();
  }
}

class PlannedFileModelBuilder
    implements Builder<PlannedFileModel, PlannedFileModelBuilder> {
  _$PlannedFileModel? _$v;

  ClassificationNeed? _classification;
  ClassificationNeed? get classification => _$this._classification;
  set classification(ClassificationNeed? classification) =>
      _$this._classification = classification;

  String? _relativePath;
  String? get relativePath => _$this._relativePath;
  set relativePath(String? relativePath) => _$this._relativePath = relativePath;

  MaterialRole? _role;
  MaterialRole? get role => _$this._role;
  set role(MaterialRole? role) => _$this._role = role;

  RoleSource? _roleSource;
  RoleSource? get roleSource => _$this._roleSource;
  set roleSource(RoleSource? roleSource) => _$this._roleSource = roleSource;

  String? _sha256;
  String? get sha256 => _$this._sha256;
  set sha256(String? sha256) => _$this._sha256 = sha256;

  int? _sizeBytes;
  int? get sizeBytes => _$this._sizeBytes;
  set sizeBytes(int? sizeBytes) => _$this._sizeBytes = sizeBytes;

  PlannedFileModelBuilder() {
    PlannedFileModel._defaults(this);
  }

  PlannedFileModelBuilder get _$this {
    final $v = _$v;
    if ($v != null) {
      _classification = $v.classification;
      _relativePath = $v.relativePath;
      _role = $v.role;
      _roleSource = $v.roleSource;
      _sha256 = $v.sha256;
      _sizeBytes = $v.sizeBytes;
      _$v = null;
    }
    return this;
  }

  @override
  void replace(PlannedFileModel other) {
    _$v = other as _$PlannedFileModel;
  }

  @override
  void update(void Function(PlannedFileModelBuilder)? updates) {
    if (updates != null) updates(this);
  }

  @override
  PlannedFileModel build() => _build();

  _$PlannedFileModel _build() {
    final _$result = _$v ??
        _$PlannedFileModel._(
          classification: BuiltValueNullFieldError.checkNotNull(
              classification, r'PlannedFileModel', 'classification'),
          relativePath: BuiltValueNullFieldError.checkNotNull(
              relativePath, r'PlannedFileModel', 'relativePath'),
          role: role,
          roleSource: BuiltValueNullFieldError.checkNotNull(
              roleSource, r'PlannedFileModel', 'roleSource'),
          sha256: BuiltValueNullFieldError.checkNotNull(
              sha256, r'PlannedFileModel', 'sha256'),
          sizeBytes: BuiltValueNullFieldError.checkNotNull(
              sizeBytes, r'PlannedFileModel', 'sizeBytes'),
        );
    replace(_$result);
    return _$result;
  }
}

// ignore_for_file: deprecated_member_use_from_same_package,type=lint
