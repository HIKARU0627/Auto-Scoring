// GENERATED CODE - DO NOT MODIFY BY HAND

part of 'submission_review_progress_response.dart';

// **************************************************************************
// BuiltValueGenerator
// **************************************************************************

class _$SubmissionReviewProgressResponse
    extends SubmissionReviewProgressResponse {
  @override
  final int confirmedQuestions;
  @override
  final int failedQuestions;
  @override
  final String submissionId;
  @override
  final int totalQuestions;

  factory _$SubmissionReviewProgressResponse(
          [void Function(SubmissionReviewProgressResponseBuilder)? updates]) =>
      (SubmissionReviewProgressResponseBuilder()..update(updates))._build();

  _$SubmissionReviewProgressResponse._(
      {required this.confirmedQuestions,
      required this.failedQuestions,
      required this.submissionId,
      required this.totalQuestions})
      : super._();
  @override
  SubmissionReviewProgressResponse rebuild(
          void Function(SubmissionReviewProgressResponseBuilder) updates) =>
      (toBuilder()..update(updates)).build();

  @override
  SubmissionReviewProgressResponseBuilder toBuilder() =>
      SubmissionReviewProgressResponseBuilder()..replace(this);

  @override
  bool operator ==(Object other) {
    if (identical(other, this)) return true;
    return other is SubmissionReviewProgressResponse &&
        confirmedQuestions == other.confirmedQuestions &&
        failedQuestions == other.failedQuestions &&
        submissionId == other.submissionId &&
        totalQuestions == other.totalQuestions;
  }

  @override
  int get hashCode {
    var _$hash = 0;
    _$hash = $jc(_$hash, confirmedQuestions.hashCode);
    _$hash = $jc(_$hash, failedQuestions.hashCode);
    _$hash = $jc(_$hash, submissionId.hashCode);
    _$hash = $jc(_$hash, totalQuestions.hashCode);
    _$hash = $jf(_$hash);
    return _$hash;
  }

  @override
  String toString() {
    return (newBuiltValueToStringHelper(r'SubmissionReviewProgressResponse')
          ..add('confirmedQuestions', confirmedQuestions)
          ..add('failedQuestions', failedQuestions)
          ..add('submissionId', submissionId)
          ..add('totalQuestions', totalQuestions))
        .toString();
  }
}

class SubmissionReviewProgressResponseBuilder
    implements
        Builder<SubmissionReviewProgressResponse,
            SubmissionReviewProgressResponseBuilder> {
  _$SubmissionReviewProgressResponse? _$v;

  int? _confirmedQuestions;
  int? get confirmedQuestions => _$this._confirmedQuestions;
  set confirmedQuestions(int? confirmedQuestions) =>
      _$this._confirmedQuestions = confirmedQuestions;

  int? _failedQuestions;
  int? get failedQuestions => _$this._failedQuestions;
  set failedQuestions(int? failedQuestions) =>
      _$this._failedQuestions = failedQuestions;

  String? _submissionId;
  String? get submissionId => _$this._submissionId;
  set submissionId(String? submissionId) => _$this._submissionId = submissionId;

  int? _totalQuestions;
  int? get totalQuestions => _$this._totalQuestions;
  set totalQuestions(int? totalQuestions) =>
      _$this._totalQuestions = totalQuestions;

  SubmissionReviewProgressResponseBuilder() {
    SubmissionReviewProgressResponse._defaults(this);
  }

  SubmissionReviewProgressResponseBuilder get _$this {
    final $v = _$v;
    if ($v != null) {
      _confirmedQuestions = $v.confirmedQuestions;
      _failedQuestions = $v.failedQuestions;
      _submissionId = $v.submissionId;
      _totalQuestions = $v.totalQuestions;
      _$v = null;
    }
    return this;
  }

  @override
  void replace(SubmissionReviewProgressResponse other) {
    _$v = other as _$SubmissionReviewProgressResponse;
  }

  @override
  void update(void Function(SubmissionReviewProgressResponseBuilder)? updates) {
    if (updates != null) updates(this);
  }

  @override
  SubmissionReviewProgressResponse build() => _build();

  _$SubmissionReviewProgressResponse _build() {
    final _$result = _$v ??
        _$SubmissionReviewProgressResponse._(
          confirmedQuestions: BuiltValueNullFieldError.checkNotNull(
              confirmedQuestions,
              r'SubmissionReviewProgressResponse',
              'confirmedQuestions'),
          failedQuestions: BuiltValueNullFieldError.checkNotNull(
              failedQuestions,
              r'SubmissionReviewProgressResponse',
              'failedQuestions'),
          submissionId: BuiltValueNullFieldError.checkNotNull(submissionId,
              r'SubmissionReviewProgressResponse', 'submissionId'),
          totalQuestions: BuiltValueNullFieldError.checkNotNull(totalQuestions,
              r'SubmissionReviewProgressResponse', 'totalQuestions'),
        );
    replace(_$result);
    return _$result;
  }
}

// ignore_for_file: deprecated_member_use_from_same_package,type=lint
