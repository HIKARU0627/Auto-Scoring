// GENERATED CODE - DO NOT MODIFY BY HAND

part of 'manual_grade_request.dart';

// **************************************************************************
// BuiltValueGenerator
// **************************************************************************

class _$ManualGradeRequest extends ManualGradeRequest {
  @override
  final BuiltList<AnnotationEditRequest>? annotations;
  @override
  final String? comment;
  @override
  final num? confidence;
  @override
  final BuiltList<CriterionOutcomeRequest>? criteria;
  @override
  final int expectedVersion;
  @override
  final String? note;
  @override
  final String? rationale;
  @override
  final String? recognizedText;
  @override
  final int scoreAwarded;
  @override
  final int scoreMaximum;

  factory _$ManualGradeRequest(
          [void Function(ManualGradeRequestBuilder)? updates]) =>
      (ManualGradeRequestBuilder()..update(updates))._build();

  _$ManualGradeRequest._(
      {this.annotations,
      this.comment,
      this.confidence,
      this.criteria,
      required this.expectedVersion,
      this.note,
      this.rationale,
      this.recognizedText,
      required this.scoreAwarded,
      required this.scoreMaximum})
      : super._();
  @override
  ManualGradeRequest rebuild(
          void Function(ManualGradeRequestBuilder) updates) =>
      (toBuilder()..update(updates)).build();

  @override
  ManualGradeRequestBuilder toBuilder() =>
      ManualGradeRequestBuilder()..replace(this);

  @override
  bool operator ==(Object other) {
    if (identical(other, this)) return true;
    return other is ManualGradeRequest &&
        annotations == other.annotations &&
        comment == other.comment &&
        confidence == other.confidence &&
        criteria == other.criteria &&
        expectedVersion == other.expectedVersion &&
        note == other.note &&
        rationale == other.rationale &&
        recognizedText == other.recognizedText &&
        scoreAwarded == other.scoreAwarded &&
        scoreMaximum == other.scoreMaximum;
  }

  @override
  int get hashCode {
    var _$hash = 0;
    _$hash = $jc(_$hash, annotations.hashCode);
    _$hash = $jc(_$hash, comment.hashCode);
    _$hash = $jc(_$hash, confidence.hashCode);
    _$hash = $jc(_$hash, criteria.hashCode);
    _$hash = $jc(_$hash, expectedVersion.hashCode);
    _$hash = $jc(_$hash, note.hashCode);
    _$hash = $jc(_$hash, rationale.hashCode);
    _$hash = $jc(_$hash, recognizedText.hashCode);
    _$hash = $jc(_$hash, scoreAwarded.hashCode);
    _$hash = $jc(_$hash, scoreMaximum.hashCode);
    _$hash = $jf(_$hash);
    return _$hash;
  }

  @override
  String toString() {
    return (newBuiltValueToStringHelper(r'ManualGradeRequest')
          ..add('annotations', annotations)
          ..add('comment', comment)
          ..add('confidence', confidence)
          ..add('criteria', criteria)
          ..add('expectedVersion', expectedVersion)
          ..add('note', note)
          ..add('rationale', rationale)
          ..add('recognizedText', recognizedText)
          ..add('scoreAwarded', scoreAwarded)
          ..add('scoreMaximum', scoreMaximum))
        .toString();
  }
}

class ManualGradeRequestBuilder
    implements Builder<ManualGradeRequest, ManualGradeRequestBuilder> {
  _$ManualGradeRequest? _$v;

  ListBuilder<AnnotationEditRequest>? _annotations;
  ListBuilder<AnnotationEditRequest> get annotations =>
      _$this._annotations ??= ListBuilder<AnnotationEditRequest>();
  set annotations(ListBuilder<AnnotationEditRequest>? annotations) =>
      _$this._annotations = annotations;

  String? _comment;
  String? get comment => _$this._comment;
  set comment(String? comment) => _$this._comment = comment;

  num? _confidence;
  num? get confidence => _$this._confidence;
  set confidence(num? confidence) => _$this._confidence = confidence;

  ListBuilder<CriterionOutcomeRequest>? _criteria;
  ListBuilder<CriterionOutcomeRequest> get criteria =>
      _$this._criteria ??= ListBuilder<CriterionOutcomeRequest>();
  set criteria(ListBuilder<CriterionOutcomeRequest>? criteria) =>
      _$this._criteria = criteria;

  int? _expectedVersion;
  int? get expectedVersion => _$this._expectedVersion;
  set expectedVersion(int? expectedVersion) =>
      _$this._expectedVersion = expectedVersion;

  String? _note;
  String? get note => _$this._note;
  set note(String? note) => _$this._note = note;

  String? _rationale;
  String? get rationale => _$this._rationale;
  set rationale(String? rationale) => _$this._rationale = rationale;

  String? _recognizedText;
  String? get recognizedText => _$this._recognizedText;
  set recognizedText(String? recognizedText) =>
      _$this._recognizedText = recognizedText;

  int? _scoreAwarded;
  int? get scoreAwarded => _$this._scoreAwarded;
  set scoreAwarded(int? scoreAwarded) => _$this._scoreAwarded = scoreAwarded;

  int? _scoreMaximum;
  int? get scoreMaximum => _$this._scoreMaximum;
  set scoreMaximum(int? scoreMaximum) => _$this._scoreMaximum = scoreMaximum;

  ManualGradeRequestBuilder() {
    ManualGradeRequest._defaults(this);
  }

  ManualGradeRequestBuilder get _$this {
    final $v = _$v;
    if ($v != null) {
      _annotations = $v.annotations?.toBuilder();
      _comment = $v.comment;
      _confidence = $v.confidence;
      _criteria = $v.criteria?.toBuilder();
      _expectedVersion = $v.expectedVersion;
      _note = $v.note;
      _rationale = $v.rationale;
      _recognizedText = $v.recognizedText;
      _scoreAwarded = $v.scoreAwarded;
      _scoreMaximum = $v.scoreMaximum;
      _$v = null;
    }
    return this;
  }

  @override
  void replace(ManualGradeRequest other) {
    _$v = other as _$ManualGradeRequest;
  }

  @override
  void update(void Function(ManualGradeRequestBuilder)? updates) {
    if (updates != null) updates(this);
  }

  @override
  ManualGradeRequest build() => _build();

  _$ManualGradeRequest _build() {
    _$ManualGradeRequest _$result;
    try {
      _$result = _$v ??
          _$ManualGradeRequest._(
            annotations: _annotations?.build(),
            comment: comment,
            confidence: confidence,
            criteria: _criteria?.build(),
            expectedVersion: BuiltValueNullFieldError.checkNotNull(
                expectedVersion, r'ManualGradeRequest', 'expectedVersion'),
            note: note,
            rationale: rationale,
            recognizedText: recognizedText,
            scoreAwarded: BuiltValueNullFieldError.checkNotNull(
                scoreAwarded, r'ManualGradeRequest', 'scoreAwarded'),
            scoreMaximum: BuiltValueNullFieldError.checkNotNull(
                scoreMaximum, r'ManualGradeRequest', 'scoreMaximum'),
          );
    } catch (_) {
      late String _$failedField;
      try {
        _$failedField = 'annotations';
        _annotations?.build();

        _$failedField = 'criteria';
        _criteria?.build();
      } catch (e) {
        throw BuiltValueNestedFieldError(
            r'ManualGradeRequest', _$failedField, e.toString());
      }
      rethrow;
    }
    replace(_$result);
    return _$result;
  }
}

// ignore_for_file: deprecated_member_use_from_same_package,type=lint
