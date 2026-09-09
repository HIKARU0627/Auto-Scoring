// GENERATED CODE - DO NOT MODIFY BY HAND

part of 'grade_result_response.dart';

// **************************************************************************
// BuiltValueGenerator
// **************************************************************************

class _$GradeResultResponse extends GradeResultResponse {
  @override
  final AnswerImageFinding? answerImageFinding;
  @override
  final String? comment;
  @override
  final num confidence;
  @override
  final DateTime createdAt;
  @override
  final BuiltList<CriterionResultResponse> criteria;
  @override
  final String id;
  @override
  final String questionId;
  @override
  final String? rationale;
  @override
  final ScoreValueResponse score;
  @override
  final String source_;
  @override
  final String submissionId;

  factory _$GradeResultResponse(
          [void Function(GradeResultResponseBuilder)? updates]) =>
      (GradeResultResponseBuilder()..update(updates))._build();

  _$GradeResultResponse._(
      {this.answerImageFinding,
      this.comment,
      required this.confidence,
      required this.createdAt,
      required this.criteria,
      required this.id,
      required this.questionId,
      this.rationale,
      required this.score,
      required this.source_,
      required this.submissionId})
      : super._();
  @override
  GradeResultResponse rebuild(
          void Function(GradeResultResponseBuilder) updates) =>
      (toBuilder()..update(updates)).build();

  @override
  GradeResultResponseBuilder toBuilder() =>
      GradeResultResponseBuilder()..replace(this);

  @override
  bool operator ==(Object other) {
    if (identical(other, this)) return true;
    return other is GradeResultResponse &&
        answerImageFinding == other.answerImageFinding &&
        comment == other.comment &&
        confidence == other.confidence &&
        createdAt == other.createdAt &&
        criteria == other.criteria &&
        id == other.id &&
        questionId == other.questionId &&
        rationale == other.rationale &&
        score == other.score &&
        source_ == other.source_ &&
        submissionId == other.submissionId;
  }

  @override
  int get hashCode {
    var _$hash = 0;
    _$hash = $jc(_$hash, answerImageFinding.hashCode);
    _$hash = $jc(_$hash, comment.hashCode);
    _$hash = $jc(_$hash, confidence.hashCode);
    _$hash = $jc(_$hash, createdAt.hashCode);
    _$hash = $jc(_$hash, criteria.hashCode);
    _$hash = $jc(_$hash, id.hashCode);
    _$hash = $jc(_$hash, questionId.hashCode);
    _$hash = $jc(_$hash, rationale.hashCode);
    _$hash = $jc(_$hash, score.hashCode);
    _$hash = $jc(_$hash, source_.hashCode);
    _$hash = $jc(_$hash, submissionId.hashCode);
    _$hash = $jf(_$hash);
    return _$hash;
  }

  @override
  String toString() {
    return (newBuiltValueToStringHelper(r'GradeResultResponse')
          ..add('answerImageFinding', answerImageFinding)
          ..add('comment', comment)
          ..add('confidence', confidence)
          ..add('createdAt', createdAt)
          ..add('criteria', criteria)
          ..add('id', id)
          ..add('questionId', questionId)
          ..add('rationale', rationale)
          ..add('score', score)
          ..add('source_', source_)
          ..add('submissionId', submissionId))
        .toString();
  }
}

class GradeResultResponseBuilder
    implements Builder<GradeResultResponse, GradeResultResponseBuilder> {
  _$GradeResultResponse? _$v;

  AnswerImageFinding? _answerImageFinding;
  AnswerImageFinding? get answerImageFinding => _$this._answerImageFinding;
  set answerImageFinding(AnswerImageFinding? answerImageFinding) =>
      _$this._answerImageFinding = answerImageFinding;

  String? _comment;
  String? get comment => _$this._comment;
  set comment(String? comment) => _$this._comment = comment;

  num? _confidence;
  num? get confidence => _$this._confidence;
  set confidence(num? confidence) => _$this._confidence = confidence;

  DateTime? _createdAt;
  DateTime? get createdAt => _$this._createdAt;
  set createdAt(DateTime? createdAt) => _$this._createdAt = createdAt;

  ListBuilder<CriterionResultResponse>? _criteria;
  ListBuilder<CriterionResultResponse> get criteria =>
      _$this._criteria ??= ListBuilder<CriterionResultResponse>();
  set criteria(ListBuilder<CriterionResultResponse>? criteria) =>
      _$this._criteria = criteria;

  String? _id;
  String? get id => _$this._id;
  set id(String? id) => _$this._id = id;

  String? _questionId;
  String? get questionId => _$this._questionId;
  set questionId(String? questionId) => _$this._questionId = questionId;

  String? _rationale;
  String? get rationale => _$this._rationale;
  set rationale(String? rationale) => _$this._rationale = rationale;

  ScoreValueResponseBuilder? _score;
  ScoreValueResponseBuilder get score =>
      _$this._score ??= ScoreValueResponseBuilder();
  set score(ScoreValueResponseBuilder? score) => _$this._score = score;

  String? _source_;
  String? get source_ => _$this._source_;
  set source_(String? source_) => _$this._source_ = source_;

  String? _submissionId;
  String? get submissionId => _$this._submissionId;
  set submissionId(String? submissionId) => _$this._submissionId = submissionId;

  GradeResultResponseBuilder() {
    GradeResultResponse._defaults(this);
  }

  GradeResultResponseBuilder get _$this {
    final $v = _$v;
    if ($v != null) {
      _answerImageFinding = $v.answerImageFinding;
      _comment = $v.comment;
      _confidence = $v.confidence;
      _createdAt = $v.createdAt;
      _criteria = $v.criteria.toBuilder();
      _id = $v.id;
      _questionId = $v.questionId;
      _rationale = $v.rationale;
      _score = $v.score.toBuilder();
      _source_ = $v.source_;
      _submissionId = $v.submissionId;
      _$v = null;
    }
    return this;
  }

  @override
  void replace(GradeResultResponse other) {
    _$v = other as _$GradeResultResponse;
  }

  @override
  void update(void Function(GradeResultResponseBuilder)? updates) {
    if (updates != null) updates(this);
  }

  @override
  GradeResultResponse build() => _build();

  _$GradeResultResponse _build() {
    _$GradeResultResponse _$result;
    try {
      _$result = _$v ??
          _$GradeResultResponse._(
            answerImageFinding: answerImageFinding,
            comment: comment,
            confidence: BuiltValueNullFieldError.checkNotNull(
                confidence, r'GradeResultResponse', 'confidence'),
            createdAt: BuiltValueNullFieldError.checkNotNull(
                createdAt, r'GradeResultResponse', 'createdAt'),
            criteria: criteria.build(),
            id: BuiltValueNullFieldError.checkNotNull(
                id, r'GradeResultResponse', 'id'),
            questionId: BuiltValueNullFieldError.checkNotNull(
                questionId, r'GradeResultResponse', 'questionId'),
            rationale: rationale,
            score: score.build(),
            source_: BuiltValueNullFieldError.checkNotNull(
                source_, r'GradeResultResponse', 'source_'),
            submissionId: BuiltValueNullFieldError.checkNotNull(
                submissionId, r'GradeResultResponse', 'submissionId'),
          );
    } catch (_) {
      late String _$failedField;
      try {
        _$failedField = 'criteria';
        criteria.build();

        _$failedField = 'score';
        score.build();
      } catch (e) {
        throw BuiltValueNestedFieldError(
            r'GradeResultResponse', _$failedField, e.toString());
      }
      rethrow;
    }
    replace(_$result);
    return _$result;
  }
}

// ignore_for_file: deprecated_member_use_from_same_package,type=lint
