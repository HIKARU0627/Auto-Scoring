// GENERATED CODE - DO NOT MODIFY BY HAND

part of 'grading_availability_response.dart';

// **************************************************************************
// BuiltValueGenerator
// **************************************************************************

class _$GradingAvailabilityResponse extends GradingAvailabilityResponse {
  @override
  final bool available;
  @override
  final String? reason;

  factory _$GradingAvailabilityResponse(
          [void Function(GradingAvailabilityResponseBuilder)? updates]) =>
      (GradingAvailabilityResponseBuilder()..update(updates))._build();

  _$GradingAvailabilityResponse._({required this.available, this.reason})
      : super._();
  @override
  GradingAvailabilityResponse rebuild(
          void Function(GradingAvailabilityResponseBuilder) updates) =>
      (toBuilder()..update(updates)).build();

  @override
  GradingAvailabilityResponseBuilder toBuilder() =>
      GradingAvailabilityResponseBuilder()..replace(this);

  @override
  bool operator ==(Object other) {
    if (identical(other, this)) return true;
    return other is GradingAvailabilityResponse &&
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
    return (newBuiltValueToStringHelper(r'GradingAvailabilityResponse')
          ..add('available', available)
          ..add('reason', reason))
        .toString();
  }
}

class GradingAvailabilityResponseBuilder
    implements
        Builder<GradingAvailabilityResponse,
            GradingAvailabilityResponseBuilder> {
  _$GradingAvailabilityResponse? _$v;

  bool? _available;
  bool? get available => _$this._available;
  set available(bool? available) => _$this._available = available;

  String? _reason;
  String? get reason => _$this._reason;
  set reason(String? reason) => _$this._reason = reason;

  GradingAvailabilityResponseBuilder() {
    GradingAvailabilityResponse._defaults(this);
  }

  GradingAvailabilityResponseBuilder get _$this {
    final $v = _$v;
    if ($v != null) {
      _available = $v.available;
      _reason = $v.reason;
      _$v = null;
    }
    return this;
  }

  @override
  void replace(GradingAvailabilityResponse other) {
    _$v = other as _$GradingAvailabilityResponse;
  }

  @override
  void update(void Function(GradingAvailabilityResponseBuilder)? updates) {
    if (updates != null) updates(this);
  }

  @override
  GradingAvailabilityResponse build() => _build();

  _$GradingAvailabilityResponse _build() {
    final _$result = _$v ??
        _$GradingAvailabilityResponse._(
          available: BuiltValueNullFieldError.checkNotNull(
              available, r'GradingAvailabilityResponse', 'available'),
          reason: reason,
        );
    replace(_$result);
    return _$result;
  }
}

// ignore_for_file: deprecated_member_use_from_same_package,type=lint
