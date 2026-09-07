// GENERATED CODE - DO NOT MODIFY BY HAND

part of 'reasoned_review_request.dart';

// **************************************************************************
// BuiltValueGenerator
// **************************************************************************

class _$ReasonedReviewRequest extends ReasonedReviewRequest {
  @override
  final int expectedVersion;
  @override
  final String? reason;

  factory _$ReasonedReviewRequest(
          [void Function(ReasonedReviewRequestBuilder)? updates]) =>
      (ReasonedReviewRequestBuilder()..update(updates))._build();

  _$ReasonedReviewRequest._({required this.expectedVersion, this.reason})
      : super._();
  @override
  ReasonedReviewRequest rebuild(
          void Function(ReasonedReviewRequestBuilder) updates) =>
      (toBuilder()..update(updates)).build();

  @override
  ReasonedReviewRequestBuilder toBuilder() =>
      ReasonedReviewRequestBuilder()..replace(this);

  @override
  bool operator ==(Object other) {
    if (identical(other, this)) return true;
    return other is ReasonedReviewRequest &&
        expectedVersion == other.expectedVersion &&
        reason == other.reason;
  }

  @override
  int get hashCode {
    var _$hash = 0;
    _$hash = $jc(_$hash, expectedVersion.hashCode);
    _$hash = $jc(_$hash, reason.hashCode);
    _$hash = $jf(_$hash);
    return _$hash;
  }

  @override
  String toString() {
    return (newBuiltValueToStringHelper(r'ReasonedReviewRequest')
          ..add('expectedVersion', expectedVersion)
          ..add('reason', reason))
        .toString();
  }
}

class ReasonedReviewRequestBuilder
    implements Builder<ReasonedReviewRequest, ReasonedReviewRequestBuilder> {
  _$ReasonedReviewRequest? _$v;

  int? _expectedVersion;
  int? get expectedVersion => _$this._expectedVersion;
  set expectedVersion(int? expectedVersion) =>
      _$this._expectedVersion = expectedVersion;

  String? _reason;
  String? get reason => _$this._reason;
  set reason(String? reason) => _$this._reason = reason;

  ReasonedReviewRequestBuilder() {
    ReasonedReviewRequest._defaults(this);
  }

  ReasonedReviewRequestBuilder get _$this {
    final $v = _$v;
    if ($v != null) {
      _expectedVersion = $v.expectedVersion;
      _reason = $v.reason;
      _$v = null;
    }
    return this;
  }

  @override
  void replace(ReasonedReviewRequest other) {
    _$v = other as _$ReasonedReviewRequest;
  }

  @override
  void update(void Function(ReasonedReviewRequestBuilder)? updates) {
    if (updates != null) updates(this);
  }

  @override
  ReasonedReviewRequest build() => _build();

  _$ReasonedReviewRequest _build() {
    final _$result = _$v ??
        _$ReasonedReviewRequest._(
          expectedVersion: BuiltValueNullFieldError.checkNotNull(
              expectedVersion, r'ReasonedReviewRequest', 'expectedVersion'),
          reason: reason,
        );
    replace(_$result);
    return _$result;
  }
}

// ignore_for_file: deprecated_member_use_from_same_package,type=lint
