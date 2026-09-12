// GENERATED CODE - DO NOT MODIFY BY HAND

part of 'question_response.dart';

// **************************************************************************
// BuiltValueGenerator
// **************************************************************************

class _$QuestionResponse extends QuestionResponse {
  @override
  final NormalizedRectResponse? answerArea;
  @override
  final NormalizedRectResponse? commentArea;
  @override
  final String id;
  @override
  final bool? isScoringTarget;
  @override
  final String? modelAnswer;
  @override
  final String number;
  @override
  final int page;
  @override
  final int points;
  @override
  final BuiltList<RubricCriterionResponse> rubric;
  @override
  final NormalizedRectResponse? scoreArea;
  @override
  final QuestionScorePlacementResponse? scorePlacement;
  @override
  final String scoringMethod;
  @override
  final String testId;

  factory _$QuestionResponse(
          [void Function(QuestionResponseBuilder)? updates]) =>
      (QuestionResponseBuilder()..update(updates))._build();

  _$QuestionResponse._(
      {this.answerArea,
      this.commentArea,
      required this.id,
      this.isScoringTarget,
      this.modelAnswer,
      required this.number,
      required this.page,
      required this.points,
      required this.rubric,
      this.scoreArea,
      this.scorePlacement,
      required this.scoringMethod,
      required this.testId})
      : super._();
  @override
  QuestionResponse rebuild(void Function(QuestionResponseBuilder) updates) =>
      (toBuilder()..update(updates)).build();

  @override
  QuestionResponseBuilder toBuilder() =>
      QuestionResponseBuilder()..replace(this);

  @override
  bool operator ==(Object other) {
    if (identical(other, this)) return true;
    return other is QuestionResponse &&
        answerArea == other.answerArea &&
        commentArea == other.commentArea &&
        id == other.id &&
        isScoringTarget == other.isScoringTarget &&
        modelAnswer == other.modelAnswer &&
        number == other.number &&
        page == other.page &&
        points == other.points &&
        rubric == other.rubric &&
        scoreArea == other.scoreArea &&
        scorePlacement == other.scorePlacement &&
        scoringMethod == other.scoringMethod &&
        testId == other.testId;
  }

  @override
  int get hashCode {
    var _$hash = 0;
    _$hash = $jc(_$hash, answerArea.hashCode);
    _$hash = $jc(_$hash, commentArea.hashCode);
    _$hash = $jc(_$hash, id.hashCode);
    _$hash = $jc(_$hash, isScoringTarget.hashCode);
    _$hash = $jc(_$hash, modelAnswer.hashCode);
    _$hash = $jc(_$hash, number.hashCode);
    _$hash = $jc(_$hash, page.hashCode);
    _$hash = $jc(_$hash, points.hashCode);
    _$hash = $jc(_$hash, rubric.hashCode);
    _$hash = $jc(_$hash, scoreArea.hashCode);
    _$hash = $jc(_$hash, scorePlacement.hashCode);
    _$hash = $jc(_$hash, scoringMethod.hashCode);
    _$hash = $jc(_$hash, testId.hashCode);
    _$hash = $jf(_$hash);
    return _$hash;
  }

  @override
  String toString() {
    return (newBuiltValueToStringHelper(r'QuestionResponse')
          ..add('answerArea', answerArea)
          ..add('commentArea', commentArea)
          ..add('id', id)
          ..add('isScoringTarget', isScoringTarget)
          ..add('modelAnswer', modelAnswer)
          ..add('number', number)
          ..add('page', page)
          ..add('points', points)
          ..add('rubric', rubric)
          ..add('scoreArea', scoreArea)
          ..add('scorePlacement', scorePlacement)
          ..add('scoringMethod', scoringMethod)
          ..add('testId', testId))
        .toString();
  }
}

class QuestionResponseBuilder
    implements Builder<QuestionResponse, QuestionResponseBuilder> {
  _$QuestionResponse? _$v;

  NormalizedRectResponseBuilder? _answerArea;
  NormalizedRectResponseBuilder get answerArea =>
      _$this._answerArea ??= NormalizedRectResponseBuilder();
  set answerArea(NormalizedRectResponseBuilder? answerArea) =>
      _$this._answerArea = answerArea;

  NormalizedRectResponseBuilder? _commentArea;
  NormalizedRectResponseBuilder get commentArea =>
      _$this._commentArea ??= NormalizedRectResponseBuilder();
  set commentArea(NormalizedRectResponseBuilder? commentArea) =>
      _$this._commentArea = commentArea;

  String? _id;
  String? get id => _$this._id;
  set id(String? id) => _$this._id = id;

  bool? _isScoringTarget;
  bool? get isScoringTarget => _$this._isScoringTarget;
  set isScoringTarget(bool? isScoringTarget) =>
      _$this._isScoringTarget = isScoringTarget;

  String? _modelAnswer;
  String? get modelAnswer => _$this._modelAnswer;
  set modelAnswer(String? modelAnswer) => _$this._modelAnswer = modelAnswer;

  String? _number;
  String? get number => _$this._number;
  set number(String? number) => _$this._number = number;

  int? _page;
  int? get page => _$this._page;
  set page(int? page) => _$this._page = page;

  int? _points;
  int? get points => _$this._points;
  set points(int? points) => _$this._points = points;

  ListBuilder<RubricCriterionResponse>? _rubric;
  ListBuilder<RubricCriterionResponse> get rubric =>
      _$this._rubric ??= ListBuilder<RubricCriterionResponse>();
  set rubric(ListBuilder<RubricCriterionResponse>? rubric) =>
      _$this._rubric = rubric;

  NormalizedRectResponseBuilder? _scoreArea;
  NormalizedRectResponseBuilder get scoreArea =>
      _$this._scoreArea ??= NormalizedRectResponseBuilder();
  set scoreArea(NormalizedRectResponseBuilder? scoreArea) =>
      _$this._scoreArea = scoreArea;

  QuestionScorePlacementResponseBuilder? _scorePlacement;
  QuestionScorePlacementResponseBuilder get scorePlacement =>
      _$this._scorePlacement ??= QuestionScorePlacementResponseBuilder();
  set scorePlacement(QuestionScorePlacementResponseBuilder? scorePlacement) =>
      _$this._scorePlacement = scorePlacement;

  String? _scoringMethod;
  String? get scoringMethod => _$this._scoringMethod;
  set scoringMethod(String? scoringMethod) =>
      _$this._scoringMethod = scoringMethod;

  String? _testId;
  String? get testId => _$this._testId;
  set testId(String? testId) => _$this._testId = testId;

  QuestionResponseBuilder() {
    QuestionResponse._defaults(this);
  }

  QuestionResponseBuilder get _$this {
    final $v = _$v;
    if ($v != null) {
      _answerArea = $v.answerArea?.toBuilder();
      _commentArea = $v.commentArea?.toBuilder();
      _id = $v.id;
      _isScoringTarget = $v.isScoringTarget;
      _modelAnswer = $v.modelAnswer;
      _number = $v.number;
      _page = $v.page;
      _points = $v.points;
      _rubric = $v.rubric.toBuilder();
      _scoreArea = $v.scoreArea?.toBuilder();
      _scorePlacement = $v.scorePlacement?.toBuilder();
      _scoringMethod = $v.scoringMethod;
      _testId = $v.testId;
      _$v = null;
    }
    return this;
  }

  @override
  void replace(QuestionResponse other) {
    _$v = other as _$QuestionResponse;
  }

  @override
  void update(void Function(QuestionResponseBuilder)? updates) {
    if (updates != null) updates(this);
  }

  @override
  QuestionResponse build() => _build();

  _$QuestionResponse _build() {
    _$QuestionResponse _$result;
    try {
      _$result = _$v ??
          _$QuestionResponse._(
            answerArea: _answerArea?.build(),
            commentArea: _commentArea?.build(),
            id: BuiltValueNullFieldError.checkNotNull(
                id, r'QuestionResponse', 'id'),
            isScoringTarget: isScoringTarget,
            modelAnswer: modelAnswer,
            number: BuiltValueNullFieldError.checkNotNull(
                number, r'QuestionResponse', 'number'),
            page: BuiltValueNullFieldError.checkNotNull(
                page, r'QuestionResponse', 'page'),
            points: BuiltValueNullFieldError.checkNotNull(
                points, r'QuestionResponse', 'points'),
            rubric: rubric.build(),
            scoreArea: _scoreArea?.build(),
            scorePlacement: _scorePlacement?.build(),
            scoringMethod: BuiltValueNullFieldError.checkNotNull(
                scoringMethod, r'QuestionResponse', 'scoringMethod'),
            testId: BuiltValueNullFieldError.checkNotNull(
                testId, r'QuestionResponse', 'testId'),
          );
    } catch (_) {
      late String _$failedField;
      try {
        _$failedField = 'answerArea';
        _answerArea?.build();
        _$failedField = 'commentArea';
        _commentArea?.build();

        _$failedField = 'rubric';
        rubric.build();
        _$failedField = 'scoreArea';
        _scoreArea?.build();
        _$failedField = 'scorePlacement';
        _scorePlacement?.build();
      } catch (e) {
        throw BuiltValueNestedFieldError(
            r'QuestionResponse', _$failedField, e.toString());
      }
      rethrow;
    }
    replace(_$result);
    return _$result;
  }
}

// ignore_for_file: deprecated_member_use_from_same_package,type=lint
