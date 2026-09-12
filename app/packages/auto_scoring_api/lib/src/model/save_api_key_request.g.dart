// GENERATED CODE - DO NOT MODIFY BY HAND

part of 'save_api_key_request.dart';

// **************************************************************************
// BuiltValueGenerator
// **************************************************************************

class _$SaveApiKeyRequest extends SaveApiKeyRequest {
  @override
  final String? value;
  @override
  final BuiltMap<String, String?>? values;

  factory _$SaveApiKeyRequest(
          [void Function(SaveApiKeyRequestBuilder)? updates]) =>
      (SaveApiKeyRequestBuilder()..update(updates))._build();

  _$SaveApiKeyRequest._({this.value, this.values}) : super._();
  @override
  SaveApiKeyRequest rebuild(void Function(SaveApiKeyRequestBuilder) updates) =>
      (toBuilder()..update(updates)).build();

  @override
  SaveApiKeyRequestBuilder toBuilder() =>
      SaveApiKeyRequestBuilder()..replace(this);

  @override
  bool operator ==(Object other) {
    if (identical(other, this)) return true;
    return other is SaveApiKeyRequest &&
        value == other.value &&
        values == other.values;
  }

  @override
  int get hashCode {
    var _$hash = 0;
    _$hash = $jc(_$hash, value.hashCode);
    _$hash = $jc(_$hash, values.hashCode);
    _$hash = $jf(_$hash);
    return _$hash;
  }

  @override
  String toString() {
    return (newBuiltValueToStringHelper(r'SaveApiKeyRequest')
          ..add('value', value)
          ..add('values', values))
        .toString();
  }
}

class SaveApiKeyRequestBuilder
    implements Builder<SaveApiKeyRequest, SaveApiKeyRequestBuilder> {
  _$SaveApiKeyRequest? _$v;

  String? _value;
  String? get value => _$this._value;
  set value(String? value) => _$this._value = value;

  MapBuilder<String, String?>? _values;
  MapBuilder<String, String?> get values =>
      _$this._values ??= MapBuilder<String, String?>();
  set values(MapBuilder<String, String?>? values) => _$this._values = values;

  SaveApiKeyRequestBuilder() {
    SaveApiKeyRequest._defaults(this);
  }

  SaveApiKeyRequestBuilder get _$this {
    final $v = _$v;
    if ($v != null) {
      _value = $v.value;
      _values = $v.values?.toBuilder();
      _$v = null;
    }
    return this;
  }

  @override
  void replace(SaveApiKeyRequest other) {
    _$v = other as _$SaveApiKeyRequest;
  }

  @override
  void update(void Function(SaveApiKeyRequestBuilder)? updates) {
    if (updates != null) updates(this);
  }

  @override
  SaveApiKeyRequest build() => _build();

  _$SaveApiKeyRequest _build() {
    _$SaveApiKeyRequest _$result;
    try {
      _$result = _$v ??
          _$SaveApiKeyRequest._(
            value: value,
            values: _values?.build(),
          );
    } catch (_) {
      late String _$failedField;
      try {
        _$failedField = 'values';
        _values?.build();
      } catch (e) {
        throw BuiltValueNestedFieldError(
            r'SaveApiKeyRequest', _$failedField, e.toString());
      }
      rethrow;
    }
    replace(_$result);
    return _$result;
  }
}

// ignore_for_file: deprecated_member_use_from_same_package,type=lint
