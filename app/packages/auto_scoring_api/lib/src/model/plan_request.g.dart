// GENERATED CODE - DO NOT MODIFY BY HAND

part of 'plan_request.dart';

// **************************************************************************
// BuiltValueGenerator
// **************************************************************************

class _$PlanRequest extends PlanRequest {
  @override
  final BuiltList<ScannedFileModel> files;
  @override
  final String rootName;
  @override
  final String templateId;

  factory _$PlanRequest([void Function(PlanRequestBuilder)? updates]) =>
      (PlanRequestBuilder()..update(updates))._build();

  _$PlanRequest._(
      {required this.files, required this.rootName, required this.templateId})
      : super._();
  @override
  PlanRequest rebuild(void Function(PlanRequestBuilder) updates) =>
      (toBuilder()..update(updates)).build();

  @override
  PlanRequestBuilder toBuilder() => PlanRequestBuilder()..replace(this);

  @override
  bool operator ==(Object other) {
    if (identical(other, this)) return true;
    return other is PlanRequest &&
        files == other.files &&
        rootName == other.rootName &&
        templateId == other.templateId;
  }

  @override
  int get hashCode {
    var _$hash = 0;
    _$hash = $jc(_$hash, files.hashCode);
    _$hash = $jc(_$hash, rootName.hashCode);
    _$hash = $jc(_$hash, templateId.hashCode);
    _$hash = $jf(_$hash);
    return _$hash;
  }

  @override
  String toString() {
    return (newBuiltValueToStringHelper(r'PlanRequest')
          ..add('files', files)
          ..add('rootName', rootName)
          ..add('templateId', templateId))
        .toString();
  }
}

class PlanRequestBuilder implements Builder<PlanRequest, PlanRequestBuilder> {
  _$PlanRequest? _$v;

  ListBuilder<ScannedFileModel>? _files;
  ListBuilder<ScannedFileModel> get files =>
      _$this._files ??= ListBuilder<ScannedFileModel>();
  set files(ListBuilder<ScannedFileModel>? files) => _$this._files = files;

  String? _rootName;
  String? get rootName => _$this._rootName;
  set rootName(String? rootName) => _$this._rootName = rootName;

  String? _templateId;
  String? get templateId => _$this._templateId;
  set templateId(String? templateId) => _$this._templateId = templateId;

  PlanRequestBuilder() {
    PlanRequest._defaults(this);
  }

  PlanRequestBuilder get _$this {
    final $v = _$v;
    if ($v != null) {
      _files = $v.files.toBuilder();
      _rootName = $v.rootName;
      _templateId = $v.templateId;
      _$v = null;
    }
    return this;
  }

  @override
  void replace(PlanRequest other) {
    _$v = other as _$PlanRequest;
  }

  @override
  void update(void Function(PlanRequestBuilder)? updates) {
    if (updates != null) updates(this);
  }

  @override
  PlanRequest build() => _build();

  _$PlanRequest _build() {
    _$PlanRequest _$result;
    try {
      _$result = _$v ??
          _$PlanRequest._(
            files: files.build(),
            rootName: BuiltValueNullFieldError.checkNotNull(
                rootName, r'PlanRequest', 'rootName'),
            templateId: BuiltValueNullFieldError.checkNotNull(
                templateId, r'PlanRequest', 'templateId'),
          );
    } catch (_) {
      late String _$failedField;
      try {
        _$failedField = 'files';
        files.build();
      } catch (e) {
        throw BuiltValueNestedFieldError(
            r'PlanRequest', _$failedField, e.toString());
      }
      rethrow;
    }
    replace(_$result);
    return _$result;
  }
}

// ignore_for_file: deprecated_member_use_from_same_package,type=lint
