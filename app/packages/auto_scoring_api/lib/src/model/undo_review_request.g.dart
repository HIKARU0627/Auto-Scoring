// GENERATED CODE - DO NOT MODIFY BY HAND

part of 'undo_review_request.dart';

// **************************************************************************
// BuiltValueGenerator
// **************************************************************************

class _$UndoReviewRequest extends UndoReviewRequest {
  @override
  final int expectedVersion;

  factory _$UndoReviewRequest(
          [void Function(UndoReviewRequestBuilder)? updates]) =>
      (UndoReviewRequestBuilder()..update(updates))._build();

  _$UndoReviewRequest._({required this.expectedVersion}) : super._();
  @override
  UndoReviewRequest rebuild(void Function(UndoReviewRequestBuilder) updates) =>
      (toBuilder()..update(updates)).build();

  @override
  UndoReviewRequestBuilder toBuilder() =>
      UndoReviewRequestBuilder()..replace(this);

  @override
  bool operator ==(Object other) {
    if (identical(other, this)) return true;
    return other is UndoReviewRequest &&
        expectedVersion == other.expectedVersion;
  }

  @override
  int get hashCode {
    var _$hash = 0;
    _$hash = $jc(_$hash, expectedVersion.hashCode);
    _$hash = $jf(_$hash);
    return _$hash;
  }

  @override
  String toString() {
    return (newBuiltValueToStringHelper(r'UndoReviewRequest')
          ..add('expectedVersion', expectedVersion))
        .toString();
  }
}

class UndoReviewRequestBuilder
    implements Builder<UndoReviewRequest, UndoReviewRequestBuilder> {
  _$UndoReviewRequest? _$v;

  int? _expectedVersion;
  int? get expectedVersion => _$this._expectedVersion;
  set expectedVersion(int? expectedVersion) =>
      _$this._expectedVersion = expectedVersion;

  UndoReviewRequestBuilder() {
    UndoReviewRequest._defaults(this);
  }

  UndoReviewRequestBuilder get _$this {
    final $v = _$v;
    if ($v != null) {
      _expectedVersion = $v.expectedVersion;
      _$v = null;
    }
    return this;
  }

  @override
  void replace(UndoReviewRequest other) {
    _$v = other as _$UndoReviewRequest;
  }

  @override
  void update(void Function(UndoReviewRequestBuilder)? updates) {
    if (updates != null) updates(this);
  }

  @override
  UndoReviewRequest build() => _build();

  _$UndoReviewRequest _build() {
    final _$result = _$v ??
        _$UndoReviewRequest._(
          expectedVersion: BuiltValueNullFieldError.checkNotNull(
              expectedVersion, r'UndoReviewRequest', 'expectedVersion'),
        );
    replace(_$result);
    return _$result;
  }
}

// ignore_for_file: deprecated_member_use_from_same_package,type=lint
