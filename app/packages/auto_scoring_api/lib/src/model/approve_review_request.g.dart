// GENERATED CODE - DO NOT MODIFY BY HAND

part of 'approve_review_request.dart';

// **************************************************************************
// BuiltValueGenerator
// **************************************************************************

class _$ApproveReviewRequest extends ApproveReviewRequest {
  @override
  final String? expectedAiGradeId;
  @override
  final int expectedVersion;
  @override
  final String? note;

  factory _$ApproveReviewRequest(
          [void Function(ApproveReviewRequestBuilder)? updates]) =>
      (ApproveReviewRequestBuilder()..update(updates))._build();

  _$ApproveReviewRequest._(
      {this.expectedAiGradeId, required this.expectedVersion, this.note})
      : super._();
  @override
  ApproveReviewRequest rebuild(
          void Function(ApproveReviewRequestBuilder) updates) =>
      (toBuilder()..update(updates)).build();

  @override
  ApproveReviewRequestBuilder toBuilder() =>
      ApproveReviewRequestBuilder()..replace(this);

  @override
  bool operator ==(Object other) {
    if (identical(other, this)) return true;
    return other is ApproveReviewRequest &&
        expectedAiGradeId == other.expectedAiGradeId &&
        expectedVersion == other.expectedVersion &&
        note == other.note;
  }

  @override
  int get hashCode {
    var _$hash = 0;
    _$hash = $jc(_$hash, expectedAiGradeId.hashCode);
    _$hash = $jc(_$hash, expectedVersion.hashCode);
    _$hash = $jc(_$hash, note.hashCode);
    _$hash = $jf(_$hash);
    return _$hash;
  }

  @override
  String toString() {
    return (newBuiltValueToStringHelper(r'ApproveReviewRequest')
          ..add('expectedAiGradeId', expectedAiGradeId)
          ..add('expectedVersion', expectedVersion)
          ..add('note', note))
        .toString();
  }
}

class ApproveReviewRequestBuilder
    implements Builder<ApproveReviewRequest, ApproveReviewRequestBuilder> {
  _$ApproveReviewRequest? _$v;

  String? _expectedAiGradeId;
  String? get expectedAiGradeId => _$this._expectedAiGradeId;
  set expectedAiGradeId(String? expectedAiGradeId) =>
      _$this._expectedAiGradeId = expectedAiGradeId;

  int? _expectedVersion;
  int? get expectedVersion => _$this._expectedVersion;
  set expectedVersion(int? expectedVersion) =>
      _$this._expectedVersion = expectedVersion;

  String? _note;
  String? get note => _$this._note;
  set note(String? note) => _$this._note = note;

  ApproveReviewRequestBuilder() {
    ApproveReviewRequest._defaults(this);
  }

  ApproveReviewRequestBuilder get _$this {
    final $v = _$v;
    if ($v != null) {
      _expectedAiGradeId = $v.expectedAiGradeId;
      _expectedVersion = $v.expectedVersion;
      _note = $v.note;
      _$v = null;
    }
    return this;
  }

  @override
  void replace(ApproveReviewRequest other) {
    _$v = other as _$ApproveReviewRequest;
  }

  @override
  void update(void Function(ApproveReviewRequestBuilder)? updates) {
    if (updates != null) updates(this);
  }

  @override
  ApproveReviewRequest build() => _build();

  _$ApproveReviewRequest _build() {
    final _$result = _$v ??
        _$ApproveReviewRequest._(
          expectedAiGradeId: expectedAiGradeId,
          expectedVersion: BuiltValueNullFieldError.checkNotNull(
              expectedVersion, r'ApproveReviewRequest', 'expectedVersion'),
          note: note,
        );
    replace(_$result);
    return _$result;
  }
}

// ignore_for_file: deprecated_member_use_from_same_package,type=lint
