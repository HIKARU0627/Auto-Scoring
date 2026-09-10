// GENERATED CODE - DO NOT MODIFY BY HAND

part of 'api_key_settings_response.dart';

// **************************************************************************
// BuiltValueGenerator
// **************************************************************************

class _$ApiKeySettingsResponse extends ApiKeySettingsResponse {
  @override
  final BuiltList<ApiKeyStatusModel> keys;
  @override
  final bool restartRequired;
  @override
  final String? storeUnavailableReason;
  @override
  final String transportOrder;
  @override
  final ConfigurationSource transportSource;

  factory _$ApiKeySettingsResponse(
          [void Function(ApiKeySettingsResponseBuilder)? updates]) =>
      (ApiKeySettingsResponseBuilder()..update(updates))._build();

  _$ApiKeySettingsResponse._(
      {required this.keys,
      required this.restartRequired,
      this.storeUnavailableReason,
      required this.transportOrder,
      required this.transportSource})
      : super._();
  @override
  ApiKeySettingsResponse rebuild(
          void Function(ApiKeySettingsResponseBuilder) updates) =>
      (toBuilder()..update(updates)).build();

  @override
  ApiKeySettingsResponseBuilder toBuilder() =>
      ApiKeySettingsResponseBuilder()..replace(this);

  @override
  bool operator ==(Object other) {
    if (identical(other, this)) return true;
    return other is ApiKeySettingsResponse &&
        keys == other.keys &&
        restartRequired == other.restartRequired &&
        storeUnavailableReason == other.storeUnavailableReason &&
        transportOrder == other.transportOrder &&
        transportSource == other.transportSource;
  }

  @override
  int get hashCode {
    var _$hash = 0;
    _$hash = $jc(_$hash, keys.hashCode);
    _$hash = $jc(_$hash, restartRequired.hashCode);
    _$hash = $jc(_$hash, storeUnavailableReason.hashCode);
    _$hash = $jc(_$hash, transportOrder.hashCode);
    _$hash = $jc(_$hash, transportSource.hashCode);
    _$hash = $jf(_$hash);
    return _$hash;
  }

  @override
  String toString() {
    return (newBuiltValueToStringHelper(r'ApiKeySettingsResponse')
          ..add('keys', keys)
          ..add('restartRequired', restartRequired)
          ..add('storeUnavailableReason', storeUnavailableReason)
          ..add('transportOrder', transportOrder)
          ..add('transportSource', transportSource))
        .toString();
  }
}

class ApiKeySettingsResponseBuilder
    implements Builder<ApiKeySettingsResponse, ApiKeySettingsResponseBuilder> {
  _$ApiKeySettingsResponse? _$v;

  ListBuilder<ApiKeyStatusModel>? _keys;
  ListBuilder<ApiKeyStatusModel> get keys =>
      _$this._keys ??= ListBuilder<ApiKeyStatusModel>();
  set keys(ListBuilder<ApiKeyStatusModel>? keys) => _$this._keys = keys;

  bool? _restartRequired;
  bool? get restartRequired => _$this._restartRequired;
  set restartRequired(bool? restartRequired) =>
      _$this._restartRequired = restartRequired;

  String? _storeUnavailableReason;
  String? get storeUnavailableReason => _$this._storeUnavailableReason;
  set storeUnavailableReason(String? storeUnavailableReason) =>
      _$this._storeUnavailableReason = storeUnavailableReason;

  String? _transportOrder;
  String? get transportOrder => _$this._transportOrder;
  set transportOrder(String? transportOrder) =>
      _$this._transportOrder = transportOrder;

  ConfigurationSource? _transportSource;
  ConfigurationSource? get transportSource => _$this._transportSource;
  set transportSource(ConfigurationSource? transportSource) =>
      _$this._transportSource = transportSource;

  ApiKeySettingsResponseBuilder() {
    ApiKeySettingsResponse._defaults(this);
  }

  ApiKeySettingsResponseBuilder get _$this {
    final $v = _$v;
    if ($v != null) {
      _keys = $v.keys.toBuilder();
      _restartRequired = $v.restartRequired;
      _storeUnavailableReason = $v.storeUnavailableReason;
      _transportOrder = $v.transportOrder;
      _transportSource = $v.transportSource;
      _$v = null;
    }
    return this;
  }

  @override
  void replace(ApiKeySettingsResponse other) {
    _$v = other as _$ApiKeySettingsResponse;
  }

  @override
  void update(void Function(ApiKeySettingsResponseBuilder)? updates) {
    if (updates != null) updates(this);
  }

  @override
  ApiKeySettingsResponse build() => _build();

  _$ApiKeySettingsResponse _build() {
    _$ApiKeySettingsResponse _$result;
    try {
      _$result = _$v ??
          _$ApiKeySettingsResponse._(
            keys: keys.build(),
            restartRequired: BuiltValueNullFieldError.checkNotNull(
                restartRequired, r'ApiKeySettingsResponse', 'restartRequired'),
            storeUnavailableReason: storeUnavailableReason,
            transportOrder: BuiltValueNullFieldError.checkNotNull(
                transportOrder, r'ApiKeySettingsResponse', 'transportOrder'),
            transportSource: BuiltValueNullFieldError.checkNotNull(
                transportSource, r'ApiKeySettingsResponse', 'transportSource'),
          );
    } catch (_) {
      late String _$failedField;
      try {
        _$failedField = 'keys';
        keys.build();
      } catch (e) {
        throw BuiltValueNestedFieldError(
            r'ApiKeySettingsResponse', _$failedField, e.toString());
      }
      rethrow;
    }
    replace(_$result);
    return _$result;
  }
}

// ignore_for_file: deprecated_member_use_from_same_package,type=lint
