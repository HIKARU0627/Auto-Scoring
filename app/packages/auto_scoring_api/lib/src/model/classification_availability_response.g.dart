// GENERATED CODE - DO NOT MODIFY BY HAND

part of 'classification_availability_response.dart';

// **************************************************************************
// BuiltValueGenerator
// **************************************************************************

class _$ClassificationAvailabilityResponse
    extends ClassificationAvailabilityResponse {
  @override
  final bool available;
  @override
  final String? reason;

  factory _$ClassificationAvailabilityResponse(
          [void Function(ClassificationAvailabilityResponseBuilder)?
              updates]) =>
      (ClassificationAvailabilityResponseBuilder()..update(updates))._build();

  _$ClassificationAvailabilityResponse._({required this.available, this.reason})
      : super._();
  @override
  ClassificationAvailabilityResponse rebuild(
          void Function(ClassificationAvailabilityResponseBuilder) updates) =>
      (toBuilder()..update(updates)).build();

  @override
  ClassificationAvailabilityResponseBuilder toBuilder() =>
      ClassificationAvailabilityResponseBuilder()..replace(this);

  @override
  bool operator ==(Object other) {
    if (identical(other, this)) return true;
    return other is ClassificationAvailabilityResponse &&
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
    return (newBuiltValueToStringHelper(r'ClassificationAvailabilityResponse')
          ..add('available', available)
          ..add('reason', reason))
        .toString();
  }
}

class ClassificationAvailabilityResponseBuilder
    implements
        Builder<ClassificationAvailabilityResponse,
            ClassificationAvailabilityResponseBuilder> {
  _$ClassificationAvailabilityResponse? _$v;

  bool? _available;
  bool? get available => _$this._available;
  set available(bool? available) => _$this._available = available;

  String? _reason;
  String? get reason => _$this._reason;
  set reason(String? reason) => _$this._reason = reason;

  ClassificationAvailabilityResponseBuilder() {
    ClassificationAvailabilityResponse._defaults(this);
  }

  ClassificationAvailabilityResponseBuilder get _$this {
    final $v = _$v;
    if ($v != null) {
      _available = $v.available;
      _reason = $v.reason;
      _$v = null;
    }
    return this;
  }

  @override
  void replace(ClassificationAvailabilityResponse other) {
    _$v = other as _$ClassificationAvailabilityResponse;
  }

  @override
  void update(
      void Function(ClassificationAvailabilityResponseBuilder)? updates) {
    if (updates != null) updates(this);
  }

  @override
  ClassificationAvailabilityResponse build() => _build();

  _$ClassificationAvailabilityResponse _build() {
    final _$result = _$v ??
        _$ClassificationAvailabilityResponse._(
          available: BuiltValueNullFieldError.checkNotNull(
              available, r'ClassificationAvailabilityResponse', 'available'),
          reason: reason,
        );
    replace(_$result);
    return _$result;
  }
}

// ignore_for_file: deprecated_member_use_from_same_package,type=lint
