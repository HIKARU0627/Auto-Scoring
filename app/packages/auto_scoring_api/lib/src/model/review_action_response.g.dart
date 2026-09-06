// GENERATED CODE - DO NOT MODIFY BY HAND

part of 'review_action_response.dart';

// **************************************************************************
// BuiltValueGenerator
// **************************************************************************

class _$ReviewActionResponse extends ReviewActionResponse {
  @override
  final BuiltList<AnnotationResponse>? annotations;
  @override
  final GradeResultResponse? grade;
  @override
  final String? jobId;
  @override
  final RecognitionResponseSlim? recognition;
  @override
  final ReviewResponse review;
  @override
  final String submissionState;

  factory _$ReviewActionResponse(
          [void Function(ReviewActionResponseBuilder)? updates]) =>
      (ReviewActionResponseBuilder()..update(updates))._build();

  _$ReviewActionResponse._(
      {this.annotations,
      this.grade,
      this.jobId,
      this.recognition,
      required this.review,
      required this.submissionState})
      : super._();
  @override
  ReviewActionResponse rebuild(
          void Function(ReviewActionResponseBuilder) updates) =>
      (toBuilder()..update(updates)).build();

  @override
  ReviewActionResponseBuilder toBuilder() =>
      ReviewActionResponseBuilder()..replace(this);

  @override
  bool operator ==(Object other) {
    if (identical(other, this)) return true;
    return other is ReviewActionResponse &&
        annotations == other.annotations &&
        grade == other.grade &&
        jobId == other.jobId &&
        recognition == other.recognition &&
        review == other.review &&
        submissionState == other.submissionState;
  }

  @override
  int get hashCode {
    var _$hash = 0;
    _$hash = $jc(_$hash, annotations.hashCode);
    _$hash = $jc(_$hash, grade.hashCode);
    _$hash = $jc(_$hash, jobId.hashCode);
    _$hash = $jc(_$hash, recognition.hashCode);
    _$hash = $jc(_$hash, review.hashCode);
    _$hash = $jc(_$hash, submissionState.hashCode);
    _$hash = $jf(_$hash);
    return _$hash;
  }

  @override
  String toString() {
    return (newBuiltValueToStringHelper(r'ReviewActionResponse')
          ..add('annotations', annotations)
          ..add('grade', grade)
          ..add('jobId', jobId)
          ..add('recognition', recognition)
          ..add('review', review)
          ..add('submissionState', submissionState))
        .toString();
  }
}

class ReviewActionResponseBuilder
    implements Builder<ReviewActionResponse, ReviewActionResponseBuilder> {
  _$ReviewActionResponse? _$v;

  ListBuilder<AnnotationResponse>? _annotations;
  ListBuilder<AnnotationResponse> get annotations =>
      _$this._annotations ??= ListBuilder<AnnotationResponse>();
  set annotations(ListBuilder<AnnotationResponse>? annotations) =>
      _$this._annotations = annotations;

  GradeResultResponseBuilder? _grade;
  GradeResultResponseBuilder get grade =>
      _$this._grade ??= GradeResultResponseBuilder();
  set grade(GradeResultResponseBuilder? grade) => _$this._grade = grade;

  String? _jobId;
  String? get jobId => _$this._jobId;
  set jobId(String? jobId) => _$this._jobId = jobId;

  RecognitionResponseSlimBuilder? _recognition;
  RecognitionResponseSlimBuilder get recognition =>
      _$this._recognition ??= RecognitionResponseSlimBuilder();
  set recognition(RecognitionResponseSlimBuilder? recognition) =>
      _$this._recognition = recognition;

  ReviewResponseBuilder? _review;
  ReviewResponseBuilder get review =>
      _$this._review ??= ReviewResponseBuilder();
  set review(ReviewResponseBuilder? review) => _$this._review = review;

  String? _submissionState;
  String? get submissionState => _$this._submissionState;
  set submissionState(String? submissionState) =>
      _$this._submissionState = submissionState;

  ReviewActionResponseBuilder() {
    ReviewActionResponse._defaults(this);
  }

  ReviewActionResponseBuilder get _$this {
    final $v = _$v;
    if ($v != null) {
      _annotations = $v.annotations?.toBuilder();
      _grade = $v.grade?.toBuilder();
      _jobId = $v.jobId;
      _recognition = $v.recognition?.toBuilder();
      _review = $v.review.toBuilder();
      _submissionState = $v.submissionState;
      _$v = null;
    }
    return this;
  }

  @override
  void replace(ReviewActionResponse other) {
    _$v = other as _$ReviewActionResponse;
  }

  @override
  void update(void Function(ReviewActionResponseBuilder)? updates) {
    if (updates != null) updates(this);
  }

  @override
  ReviewActionResponse build() => _build();

  _$ReviewActionResponse _build() {
    _$ReviewActionResponse _$result;
    try {
      _$result = _$v ??
          _$ReviewActionResponse._(
            annotations: _annotations?.build(),
            grade: _grade?.build(),
            jobId: jobId,
            recognition: _recognition?.build(),
            review: review.build(),
            submissionState: BuiltValueNullFieldError.checkNotNull(
                submissionState, r'ReviewActionResponse', 'submissionState'),
          );
    } catch (_) {
      late String _$failedField;
      try {
        _$failedField = 'annotations';
        _annotations?.build();
        _$failedField = 'grade';
        _grade?.build();

        _$failedField = 'recognition';
        _recognition?.build();
        _$failedField = 'review';
        review.build();
      } catch (e) {
        throw BuiltValueNestedFieldError(
            r'ReviewActionResponse', _$failedField, e.toString());
      }
      rethrow;
    }
    replace(_$result);
    return _$result;
  }
}

// ignore_for_file: deprecated_member_use_from_same_package,type=lint
