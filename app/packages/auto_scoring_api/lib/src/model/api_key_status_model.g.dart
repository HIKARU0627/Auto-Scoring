// GENERATED CODE - DO NOT MODIFY BY HAND

part of 'api_key_status_model.dart';

// **************************************************************************
// BuiltValueGenerator
// **************************************************************************

class _$ApiKeyStatusModel extends ApiKeyStatusModel {
  @override
  final String authNote;
  @override
  final bool configured;
  @override
  final String consoleUrl;
  @override
  final bool? hostAvailable;
  @override
  final String id;
  @override
  final ConfigurationSource keySource;
  @override
  final String? keyVariable;
  @override
  final String label;
  @override
  final String model;
  @override
  final ConfigurationSource modelSource;
  @override
  final String modelVariable;
  @override
  final BuiltList<TextSettingModel> textSettings;
  @override
  final String transport;

  factory _$ApiKeyStatusModel(
          [void Function(ApiKeyStatusModelBuilder)? updates]) =>
      (ApiKeyStatusModelBuilder()..update(updates))._build();

  _$ApiKeyStatusModel._(
      {required this.authNote,
      required this.configured,
      required this.consoleUrl,
      this.hostAvailable,
      required this.id,
      required this.keySource,
      this.keyVariable,
      required this.label,
      required this.model,
      required this.modelSource,
      required this.modelVariable,
      required this.textSettings,
      required this.transport})
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
        authNote == other.authNote &&
        configured == other.configured &&
        consoleUrl == other.consoleUrl &&
        hostAvailable == other.hostAvailable &&
        id == other.id &&
        keySource == other.keySource &&
        keyVariable == other.keyVariable &&
        label == other.label &&
        model == other.model &&
        modelSource == other.modelSource &&
        modelVariable == other.modelVariable &&
        textSettings == other.textSettings &&
        transport == other.transport;
  }

  @override
  int get hashCode {
    var _$hash = 0;
    _$hash = $jc(_$hash, authNote.hashCode);
    _$hash = $jc(_$hash, configured.hashCode);
    _$hash = $jc(_$hash, consoleUrl.hashCode);
    _$hash = $jc(_$hash, hostAvailable.hashCode);
    _$hash = $jc(_$hash, id.hashCode);
    _$hash = $jc(_$hash, keySource.hashCode);
    _$hash = $jc(_$hash, keyVariable.hashCode);
    _$hash = $jc(_$hash, label.hashCode);
    _$hash = $jc(_$hash, model.hashCode);
    _$hash = $jc(_$hash, modelSource.hashCode);
    _$hash = $jc(_$hash, modelVariable.hashCode);
    _$hash = $jc(_$hash, textSettings.hashCode);
    _$hash = $jc(_$hash, transport.hashCode);
    _$hash = $jf(_$hash);
    return _$hash;
  }

  @override
  String toString() {
    return (newBuiltValueToStringHelper(r'ApiKeyStatusModel')
          ..add('authNote', authNote)
          ..add('configured', configured)
          ..add('consoleUrl', consoleUrl)
          ..add('hostAvailable', hostAvailable)
          ..add('id', id)
          ..add('keySource', keySource)
          ..add('keyVariable', keyVariable)
          ..add('label', label)
          ..add('model', model)
          ..add('modelSource', modelSource)
          ..add('modelVariable', modelVariable)
          ..add('textSettings', textSettings)
          ..add('transport', transport))
        .toString();
  }
}

class ApiKeyStatusModelBuilder
    implements Builder<ApiKeyStatusModel, ApiKeyStatusModelBuilder> {
  _$ApiKeyStatusModel? _$v;

  String? _authNote;
  String? get authNote => _$this._authNote;
  set authNote(String? authNote) => _$this._authNote = authNote;

  bool? _configured;
  bool? get configured => _$this._configured;
  set configured(bool? configured) => _$this._configured = configured;

  String? _consoleUrl;
  String? get consoleUrl => _$this._consoleUrl;
  set consoleUrl(String? consoleUrl) => _$this._consoleUrl = consoleUrl;

  bool? _hostAvailable;
  bool? get hostAvailable => _$this._hostAvailable;
  set hostAvailable(bool? hostAvailable) =>
      _$this._hostAvailable = hostAvailable;

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

  String? _modelVariable;
  String? get modelVariable => _$this._modelVariable;
  set modelVariable(String? modelVariable) =>
      _$this._modelVariable = modelVariable;

  ListBuilder<TextSettingModel>? _textSettings;
  ListBuilder<TextSettingModel> get textSettings =>
      _$this._textSettings ??= ListBuilder<TextSettingModel>();
  set textSettings(ListBuilder<TextSettingModel>? textSettings) =>
      _$this._textSettings = textSettings;

  String? _transport;
  String? get transport => _$this._transport;
  set transport(String? transport) => _$this._transport = transport;

  ApiKeyStatusModelBuilder() {
    ApiKeyStatusModel._defaults(this);
  }

  ApiKeyStatusModelBuilder get _$this {
    final $v = _$v;
    if ($v != null) {
      _authNote = $v.authNote;
      _configured = $v.configured;
      _consoleUrl = $v.consoleUrl;
      _hostAvailable = $v.hostAvailable;
      _id = $v.id;
      _keySource = $v.keySource;
      _keyVariable = $v.keyVariable;
      _label = $v.label;
      _model = $v.model;
      _modelSource = $v.modelSource;
      _modelVariable = $v.modelVariable;
      _textSettings = $v.textSettings.toBuilder();
      _transport = $v.transport;
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
    _$ApiKeyStatusModel _$result;
    try {
      _$result = _$v ??
          _$ApiKeyStatusModel._(
            authNote: BuiltValueNullFieldError.checkNotNull(
                authNote, r'ApiKeyStatusModel', 'authNote'),
            configured: BuiltValueNullFieldError.checkNotNull(
                configured, r'ApiKeyStatusModel', 'configured'),
            consoleUrl: BuiltValueNullFieldError.checkNotNull(
                consoleUrl, r'ApiKeyStatusModel', 'consoleUrl'),
            hostAvailable: hostAvailable,
            id: BuiltValueNullFieldError.checkNotNull(
                id, r'ApiKeyStatusModel', 'id'),
            keySource: BuiltValueNullFieldError.checkNotNull(
                keySource, r'ApiKeyStatusModel', 'keySource'),
            keyVariable: keyVariable,
            label: BuiltValueNullFieldError.checkNotNull(
                label, r'ApiKeyStatusModel', 'label'),
            model: BuiltValueNullFieldError.checkNotNull(
                model, r'ApiKeyStatusModel', 'model'),
            modelSource: BuiltValueNullFieldError.checkNotNull(
                modelSource, r'ApiKeyStatusModel', 'modelSource'),
            modelVariable: BuiltValueNullFieldError.checkNotNull(
                modelVariable, r'ApiKeyStatusModel', 'modelVariable'),
            textSettings: textSettings.build(),
            transport: BuiltValueNullFieldError.checkNotNull(
                transport, r'ApiKeyStatusModel', 'transport'),
          );
    } catch (_) {
      late String _$failedField;
      try {
        _$failedField = 'textSettings';
        textSettings.build();
      } catch (e) {
        throw BuiltValueNestedFieldError(
            r'ApiKeyStatusModel', _$failedField, e.toString());
      }
      rethrow;
    }
    replace(_$result);
    return _$result;
  }
}

// ignore_for_file: deprecated_member_use_from_same_package,type=lint
