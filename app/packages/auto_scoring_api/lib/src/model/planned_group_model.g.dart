// GENERATED CODE - DO NOT MODIFY BY HAND

part of 'planned_group_model.dart';

// **************************************************************************
// BuiltValueGenerator
// **************************************************************************

class _$PlannedGroupModel extends PlannedGroupModel {
  @override
  final BuiltList<PlannedFileModel> files;
  @override
  final String key;
  @override
  final BuiltList<MaterialRole> missingRequiredRolesIfNew;
  @override
  final String suggestedName;

  factory _$PlannedGroupModel(
          [void Function(PlannedGroupModelBuilder)? updates]) =>
      (PlannedGroupModelBuilder()..update(updates))._build();

  _$PlannedGroupModel._(
      {required this.files,
      required this.key,
      required this.missingRequiredRolesIfNew,
      required this.suggestedName})
      : super._();
  @override
  PlannedGroupModel rebuild(void Function(PlannedGroupModelBuilder) updates) =>
      (toBuilder()..update(updates)).build();

  @override
  PlannedGroupModelBuilder toBuilder() =>
      PlannedGroupModelBuilder()..replace(this);

  @override
  bool operator ==(Object other) {
    if (identical(other, this)) return true;
    return other is PlannedGroupModel &&
        files == other.files &&
        key == other.key &&
        missingRequiredRolesIfNew == other.missingRequiredRolesIfNew &&
        suggestedName == other.suggestedName;
  }

  @override
  int get hashCode {
    var _$hash = 0;
    _$hash = $jc(_$hash, files.hashCode);
    _$hash = $jc(_$hash, key.hashCode);
    _$hash = $jc(_$hash, missingRequiredRolesIfNew.hashCode);
    _$hash = $jc(_$hash, suggestedName.hashCode);
    _$hash = $jf(_$hash);
    return _$hash;
  }

  @override
  String toString() {
    return (newBuiltValueToStringHelper(r'PlannedGroupModel')
          ..add('files', files)
          ..add('key', key)
          ..add('missingRequiredRolesIfNew', missingRequiredRolesIfNew)
          ..add('suggestedName', suggestedName))
        .toString();
  }
}

class PlannedGroupModelBuilder
    implements Builder<PlannedGroupModel, PlannedGroupModelBuilder> {
  _$PlannedGroupModel? _$v;

  ListBuilder<PlannedFileModel>? _files;
  ListBuilder<PlannedFileModel> get files =>
      _$this._files ??= ListBuilder<PlannedFileModel>();
  set files(ListBuilder<PlannedFileModel>? files) => _$this._files = files;

  String? _key;
  String? get key => _$this._key;
  set key(String? key) => _$this._key = key;

  ListBuilder<MaterialRole>? _missingRequiredRolesIfNew;
  ListBuilder<MaterialRole> get missingRequiredRolesIfNew =>
      _$this._missingRequiredRolesIfNew ??= ListBuilder<MaterialRole>();
  set missingRequiredRolesIfNew(
          ListBuilder<MaterialRole>? missingRequiredRolesIfNew) =>
      _$this._missingRequiredRolesIfNew = missingRequiredRolesIfNew;

  String? _suggestedName;
  String? get suggestedName => _$this._suggestedName;
  set suggestedName(String? suggestedName) =>
      _$this._suggestedName = suggestedName;

  PlannedGroupModelBuilder() {
    PlannedGroupModel._defaults(this);
  }

  PlannedGroupModelBuilder get _$this {
    final $v = _$v;
    if ($v != null) {
      _files = $v.files.toBuilder();
      _key = $v.key;
      _missingRequiredRolesIfNew = $v.missingRequiredRolesIfNew.toBuilder();
      _suggestedName = $v.suggestedName;
      _$v = null;
    }
    return this;
  }

  @override
  void replace(PlannedGroupModel other) {
    _$v = other as _$PlannedGroupModel;
  }

  @override
  void update(void Function(PlannedGroupModelBuilder)? updates) {
    if (updates != null) updates(this);
  }

  @override
  PlannedGroupModel build() => _build();

  _$PlannedGroupModel _build() {
    _$PlannedGroupModel _$result;
    try {
      _$result = _$v ??
          _$PlannedGroupModel._(
            files: files.build(),
            key: BuiltValueNullFieldError.checkNotNull(
                key, r'PlannedGroupModel', 'key'),
            missingRequiredRolesIfNew: missingRequiredRolesIfNew.build(),
            suggestedName: BuiltValueNullFieldError.checkNotNull(
                suggestedName, r'PlannedGroupModel', 'suggestedName'),
          );
    } catch (_) {
      late String _$failedField;
      try {
        _$failedField = 'files';
        files.build();

        _$failedField = 'missingRequiredRolesIfNew';
        missingRequiredRolesIfNew.build();
      } catch (e) {
        throw BuiltValueNestedFieldError(
            r'PlannedGroupModel', _$failedField, e.toString());
      }
      rethrow;
    }
    replace(_$result);
    return _$result;
  }
}

// ignore_for_file: deprecated_member_use_from_same_package,type=lint
