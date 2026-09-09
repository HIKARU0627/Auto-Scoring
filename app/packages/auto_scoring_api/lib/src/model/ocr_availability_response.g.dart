// GENERATED CODE - DO NOT MODIFY BY HAND

part of 'ocr_availability_response.dart';

// **************************************************************************
// BuiltValueGenerator
// **************************************************************************

class _$OcrAvailabilityResponse extends OcrAvailabilityResponse {
  @override
  final bool available;
  @override
  final String? reason;

  factory _$OcrAvailabilityResponse(
          [void Function(OcrAvailabilityResponseBuilder)? updates]) =>
      (OcrAvailabilityResponseBuilder()..update(updates))._build();

  _$OcrAvailabilityResponse._({required this.available, this.reason})
      : super._();
  @override
  OcrAvailabilityResponse rebuild(
          void Function(OcrAvailabilityResponseBuilder) updates) =>
      (toBuilder()..update(updates)).build();

  @override
  OcrAvailabilityResponseBuilder toBuilder() =>
      OcrAvailabilityResponseBuilder()..replace(this);

  @override
  bool operator ==(Object other) {
    if (identical(other, this)) return true;
    return other is OcrAvailabilityResponse &&
        available == other.available &&
        reason == other.reason;
  }

  @override
  int get hashCode {
    var _$hash = 0;
    _$hash = $jc(_$hash, available.hashCode);
    _$hash = $jc(_$hash, reason.hashCode);
    _$hash = $jf(_$hash);
    return _$hash;
  }

  @override
  String toString() {
    return (newBuiltValueToStringHelper(r'OcrAvailabilityResponse')
          ..add('available', available)
          ..add('reason', reason))
        .toString();
  }
}

class OcrAvailabilityResponseBuilder
    implements
        Builder<OcrAvailabilityResponse, OcrAvailabilityResponseBuilder> {
  _$OcrAvailabilityResponse? _$v;

  bool? _available;
  bool? get available => _$this._available;
  set available(bool? available) => _$this._available = available;

  String? _reason;
  String? get reason => _$this._reason;
  set reason(String? reason) => _$this._reason = reason;

  OcrAvailabilityResponseBuilder() {
    OcrAvailabilityResponse._defaults(this);
  }

  OcrAvailabilityResponseBuilder get _$this {
    final $v = _$v;
    if ($v != null) {
      _available = $v.available;
      _reason = $v.reason;
      _$v = null;
    }
    return this;
  }

  @override
  void replace(OcrAvailabilityResponse other) {
    _$v = other as _$OcrAvailabilityResponse;
  }

  @override
  void update(void Function(OcrAvailabilityResponseBuilder)? updates) {
    if (updates != null) updates(this);
  }

  @override
  OcrAvailabilityResponse build() => _build();

  _$OcrAvailabilityResponse _build() {
    final _$result = _$v ??
        _$OcrAvailabilityResponse._(
          available: BuiltValueNullFieldError.checkNotNull(
              available, r'OcrAvailabilityResponse', 'available'),
          reason: reason,
        );
    replace(_$result);
    return _$result;
  }
}

// ignore_for_file: deprecated_member_use_from_same_package,type=lint
