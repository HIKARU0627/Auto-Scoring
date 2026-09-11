// GENERATED CODE - DO NOT MODIFY BY HAND

part of 'verify_api_key_response.dart';

// **************************************************************************
// BuiltValueGenerator
// **************************************************************************

class _$VerifyApiKeyResponse extends VerifyApiKeyResponse {
  @override
  final String detail;
  @override
  final ConfigurationSource keySource;
  @override
  final num? providerAccountLimit;
  @override
  final num? providerAccountUsage;
  @override
  final String result;
  @override
  final int? statusCode;

  factory _$VerifyApiKeyResponse(
          [void Function(VerifyApiKeyResponseBuilder)? updates]) =>
      (VerifyApiKeyResponseBuilder()..update(updates))._build();

  _$VerifyApiKeyResponse._(
      {required this.detail,
      required this.keySource,
      this.providerAccountLimit,
      this.providerAccountUsage,
      required this.result,
      this.statusCode})
      : super._();
  @override
  VerifyApiKeyResponse rebuild(
          void Function(VerifyApiKeyResponseBuilder) updates) =>
      (toBuilder()..update(updates)).build();

  @override
  VerifyApiKeyResponseBuilder toBuilder() =>
      VerifyApiKeyResponseBuilder()..replace(this);

  @override
  bool operator ==(Object other) {
    if (identical(other, this)) return true;
    return other is VerifyApiKeyResponse &&
        detail == other.detail &&
        keySource == other.keySource &&
        providerAccountLimit == other.providerAccountLimit &&
        providerAccountUsage == other.providerAccountUsage &&
        result == other.result &&
        statusCode == other.statusCode;
  }

  @override
  int get hashCode {
    var _$hash = 0;
    _$hash = $jc(_$hash, detail.hashCode);
    _$hash = $jc(_$hash, keySource.hashCode);
    _$hash = $jc(_$hash, providerAccountLimit.hashCode);
    _$hash = $jc(_$hash, providerAccountUsage.hashCode);
    _$hash = $jc(_$hash, result.hashCode);
    _$hash = $jc(_$hash, statusCode.hashCode);
    _$hash = $jf(_$hash);
    return _$hash;
  }

  @override
  String toString() {
    return (newBuiltValueToStringHelper(r'VerifyApiKeyResponse')
          ..add('detail', detail)
          ..add('keySource', keySource)
          ..add('providerAccountLimit', providerAccountLimit)
          ..add('providerAccountUsage', providerAccountUsage)
          ..add('result', result)
          ..add('statusCode', statusCode))
        .toString();
  }
}

class VerifyApiKeyResponseBuilder
    implements Builder<VerifyApiKeyResponse, VerifyApiKeyResponseBuilder> {
  _$VerifyApiKeyResponse? _$v;

  String? _detail;
  String? get detail => _$this._detail;
  set detail(String? detail) => _$this._detail = detail;

  ConfigurationSource? _keySource;
  ConfigurationSource? get keySource => _$this._keySource;
  set keySource(ConfigurationSource? keySource) =>
      _$this._keySource = keySource;

  num? _providerAccountLimit;
  num? get providerAccountLimit => _$this._providerAccountLimit;
  set providerAccountLimit(num? providerAccountLimit) =>
      _$this._providerAccountLimit = providerAccountLimit;

  num? _providerAccountUsage;
  num? get providerAccountUsage => _$this._providerAccountUsage;
  set providerAccountUsage(num? providerAccountUsage) =>
      _$this._providerAccountUsage = providerAccountUsage;

  String? _result;
  String? get result => _$this._result;
  set result(String? result) => _$this._result = result;

  int? _statusCode;
  int? get statusCode => _$this._statusCode;
  set statusCode(int? statusCode) => _$this._statusCode = statusCode;

  VerifyApiKeyResponseBuilder() {
    VerifyApiKeyResponse._defaults(this);
  }

  VerifyApiKeyResponseBuilder get _$this {
    final $v = _$v;
    if ($v != null) {
      _detail = $v.detail;
      _keySource = $v.keySource;
      _providerAccountLimit = $v.providerAccountLimit;
      _providerAccountUsage = $v.providerAccountUsage;
      _result = $v.result;
      _statusCode = $v.statusCode;
      _$v = null;
    }
    return this;
  }

  @override
  void replace(VerifyApiKeyResponse other) {
    _$v = other as _$VerifyApiKeyResponse;
  }

  @override
  void update(void Function(VerifyApiKeyResponseBuilder)? updates) {
    if (updates != null) updates(this);
  }

  @override
  VerifyApiKeyResponse build() => _build();

  _$VerifyApiKeyResponse _build() {
    final _$result = _$v ??
        _$VerifyApiKeyResponse._(
          detail: BuiltValueNullFieldError.checkNotNull(
              detail, r'VerifyApiKeyResponse', 'detail'),
          keySource: BuiltValueNullFieldError.checkNotNull(
              keySource, r'VerifyApiKeyResponse', 'keySource'),
          providerAccountLimit: providerAccountLimit,
          providerAccountUsage: providerAccountUsage,
          result: BuiltValueNullFieldError.checkNotNull(
              result, r'VerifyApiKeyResponse', 'result'),
          statusCode: statusCode,
        );
    replace(_$result);
    return _$result;
  }
}

// ignore_for_file: deprecated_member_use_from_same_package,type=lint
