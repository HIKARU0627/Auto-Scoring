// GENERATED CODE - DO NOT MODIFY BY HAND

part of 'api_key_status_model.dart';

// **************************************************************************
// BuiltValueGenerator
// **************************************************************************

class _$ApiKeyStatusModel extends ApiKeyStatusModel {
  @override
  final bool configured;
  @override
  final String consoleUrl;
  @override
  final String id;
  @override
  final ConfigurationSource keySource;
  @override
  final String keyVariable;
  @override
  final String label;
  @override
  final String model;
  @override
  final ConfigurationSource modelSource;

  factory _$ApiKeyStatusModel(
          [void Function(ApiKeyStatusModelBuilder)? updates]) =>
      (ApiKeyStatusModelBuilder()..update(updates))._build();

  _$ApiKeyStatusModel._(
      {required this.configured,
      required this.consoleUrl,
      required this.id,
      required this.keySource,
      required this.keyVariable,
      required this.label,
      required this.model,
      required this.modelSource})
      : super._();
  @override
  ApiKeyStatusModel rebuild(void Function(ApiKeyStatusModelBuilder) updates) =>
      (toBuilder()..update(updates)).build();

  @override
  ApiKeyStatusModelBuilder toBuilder() =>
      ApiKeyStatusModelBuilder()..replace(this);

  @override
  bool operator ==(Object other) {
    if (identical(other, this)) return true;
    return other is ApiKeyStatusModel &&
        configured == other.configured &&
        consoleUrl == other.consoleUrl &&
        id == other.id &&
        keySource == other.keySource &&
        keyVariable == other.keyVariable &&
        label == other.label &&
        model == other.model &&
        modelSource == other.modelSource;
  }

  @override
  int get hashCode {
    var _$hash = 0;
    _$hash = $jc(_$hash, configured.hashCode);
    _$hash = $jc(_$hash, consoleUrl.hashCode);
    _$hash = $jc(_$hash, id.hashCode);
    _$hash = $jc(_$hash, keySource.hashCode);
    _$hash = $jc(_$hash, keyVariable.hashCode);
    _$hash = $jc(_$hash, label.hashCode);
    _$hash = $jc(_$hash, model.hashCode);
    _$hash = $jc(_$hash, modelSource.hashCode);
    _$hash = $jf(_$hash);
    return _$hash;
  }

  @override
  String toString() {
    return (newBuiltValueToStringHelper(r'ApiKeyStatusModel')
          ..add('configured', configured)
          ..add('consoleUrl', consoleUrl)
          ..add('id', id)
          ..add('keySource', keySource)
          ..add('keyVariable', keyVariable)
          ..add('label', label)
          ..add('model', model)
          ..add('modelSource', modelSource))
        .toString();
  }
}

class ApiKeyStatusModelBuilder
    implements Builder<ApiKeyStatusModel, ApiKeyStatusModelBuilder> {
  _$ApiKeyStatusModel? _$v;

  bool? _configured;
  bool? get configured => _$this._configured;
  set configured(bool? configured) => _$this._configured = configured;

  String? _consoleUrl;
  String? get consoleUrl => _$this._consoleUrl;
  set consoleUrl(String? consoleUrl) => _$this._consoleUrl = consoleUrl;

  String? _id;
  String? get id => _$this._id;
  set id(String? id) => _$this._id = id;

  ConfigurationSource? _keySource;
  ConfigurationSource? get keySource => _$this._keySource;
  set keySource(ConfigurationSource? keySource) =>
      _$this._keySource = keySource;

  String? _keyVariable;
  String? get keyVariable => _$this._keyVariable;
  set keyVariable(String? keyVariable) => _$this._keyVariable = keyVariable;

  String? _label;
  String? get label => _$this._label;
  set label(String? label) => _$this._label = label;

  String? _model;
  String? get model => _$this._model;
  set model(String? model) => _$this._model = model;

  ConfigurationSource? _modelSource;
  ConfigurationSource? get modelSource => _$this._modelSource;
  set modelSource(ConfigurationSource? modelSource) =>
      _$this._modelSource = modelSource;

  ApiKeyStatusModelBuilder() {
    ApiKeyStatusModel._defaults(this);
  }

  ApiKeyStatusModelBuilder get _$this {
    final $v = _$v;
    if ($v != null) {
      _configured = $v.configured;
      _consoleUrl = $v.consoleUrl;
      _id = $v.id;
      _keySource = $v.keySource;
      _keyVariable = $v.keyVariable;
      _label = $v.label;
      _model = $v.model;
      _modelSource = $v.modelSource;
      _$v = null;
    }
    return this;
  }

  @override
  void replace(ApiKeyStatusModel other) {
    _$v = other as _$ApiKeyStatusModel;
  }

  @override
  void update(void Function(ApiKeyStatusModelBuilder)? updates) {
    if (updates != null) updates(this);
  }

  @override
  ApiKeyStatusModel build() => _build();

  _$ApiKeyStatusModel _build() {
    final _$result = _$v ??
        _$ApiKeyStatusModel._(
          configured: BuiltValueNullFieldError.checkNotNull(
              configured, r'ApiKeyStatusModel', 'configured'),
          consoleUrl: BuiltValueNullFieldError.checkNotNull(
              consoleUrl, r'ApiKeyStatusModel', 'consoleUrl'),
          id: BuiltValueNullFieldError.checkNotNull(
              id, r'ApiKeyStatusModel', 'id'),
          keySource: BuiltValueNullFieldError.checkNotNull(
              keySource, r'ApiKeyStatusModel', 'keySource'),
          keyVariable: BuiltValueNullFieldError.checkNotNull(
              keyVariable, r'ApiKeyStatusModel', 'keyVariable'),
          label: BuiltValueNullFieldError.checkNotNull(
              label, r'ApiKeyStatusModel', 'label'),
          model: BuiltValueNullFieldError.checkNotNull(
              model, r'ApiKeyStatusModel', 'model'),
          modelSource: BuiltValueNullFieldError.checkNotNull(
              modelSource, r'ApiKeyStatusModel', 'modelSource'),
        );
    replace(_$result);
    return _$result;
  }
}

// ignore_for_file: deprecated_member_use_from_same_package,type=lint
