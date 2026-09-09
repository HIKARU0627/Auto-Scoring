// GENERATED CODE - DO NOT MODIFY BY HAND

part of 'criteria_response.dart';

// **************************************************************************
// BuiltValueGenerator
// **************************************************************************

class _$CriteriaResponse extends CriteriaResponse {
  @override
  final int? declaredTotalPoints;
  @override
  final bool extracted;
  @override
  final String? note;
  @override
  final BuiltList<CriteriaQuestionModel> questions;
  @override
  final int revision;
  @override
  final CriteriaStatus status;
  @override
  final String testId;
  @override
  final CriteriaTotalsModel totals;
  @override
  final BuiltList<int> unreadablePages;

  factory _$CriteriaResponse(
          [void Function(CriteriaResponseBuilder)? updates]) =>
      (CriteriaResponseBuilder()..update(updates))._build();

  _$CriteriaResponse._(
      {this.declaredTotalPoints,
      required this.extracted,
      this.note,
      required this.questions,
      required this.revision,
      required this.status,
      required this.testId,
      required this.totals,
      required this.unreadablePages})
      : super._();
  @override
  CriteriaResponse rebuild(void Function(CriteriaResponseBuilder) updates) =>
      (toBuilder()..update(updates)).build();

  @override
  CriteriaResponseBuilder toBuilder() =>
      CriteriaResponseBuilder()..replace(this);

  @override
  bool operator ==(Object other) {
    if (identical(other, this)) return true;
    return other is CriteriaResponse &&
        declaredTotalPoints == other.declaredTotalPoints &&
        extracted == other.extracted &&
        note == other.note &&
        questions == other.questions &&
        revision == other.revision &&
        status == other.status &&
        testId == other.testId &&
        totals == other.totals &&
        unreadablePages == other.unreadablePages;
  }

  @override
  int get hashCode {
    var _$hash = 0;
    _$hash = $jc(_$hash, declaredTotalPoints.hashCode);
    _$hash = $jc(_$hash, extracted.hashCode);
    _$hash = $jc(_$hash, note.hashCode);
    _$hash = $jc(_$hash, questions.hashCode);
    _$hash = $jc(_$hash, revision.hashCode);
    _$hash = $jc(_$hash, status.hashCode);
    _$hash = $jc(_$hash, testId.hashCode);
    _$hash = $jc(_$hash, totals.hashCode);
    _$hash = $jc(_$hash, unreadablePages.hashCode);
    _$hash = $jf(_$hash);
    return _$hash;
  }

  @override
  String toString() {
    return (newBuiltValueToStringHelper(r'CriteriaResponse')
          ..add('declaredTotalPoints', declaredTotalPoints)
          ..add('extracted', extracted)
          ..add('note', note)
          ..add('questions', questions)
          ..add('revision', revision)
          ..add('status', status)
          ..add('testId', testId)
          ..add('totals', totals)
          ..add('unreadablePages', unreadablePages))
        .toString();
  }
}

class CriteriaResponseBuilder
    implements Builder<CriteriaResponse, CriteriaResponseBuilder> {
  _$CriteriaResponse? _$v;

  int? _declaredTotalPoints;
  int? get declaredTotalPoints => _$this._declaredTotalPoints;
  set declaredTotalPoints(int? declaredTotalPoints) =>
      _$this._declaredTotalPoints = declaredTotalPoints;

  bool? _extracted;
  bool? get extracted => _$this._extracted;
  set extracted(bool? extracted) => _$this._extracted = extracted;

  String? _note;
  String? get note => _$this._note;
  set note(String? note) => _$this._note = note;

  ListBuilder<CriteriaQuestionModel>? _questions;
  ListBuilder<CriteriaQuestionModel> get questions =>
      _$this._questions ??= ListBuilder<CriteriaQuestionModel>();
  set questions(ListBuilder<CriteriaQuestionModel>? questions) =>
      _$this._questions = questions;

  int? _revision;
  int? get revision => _$this._revision;
  set revision(int? revision) => _$this._revision = revision;

  CriteriaStatus? _status;
  CriteriaStatus? get status => _$this._status;
  set status(CriteriaStatus? status) => _$this._status = status;

  String? _testId;
  String? get testId => _$this._testId;
  set testId(String? testId) => _$this._testId = testId;

  CriteriaTotalsModelBuilder? _totals;
  CriteriaTotalsModelBuilder get totals =>
      _$this._totals ??= CriteriaTotalsModelBuilder();
  set totals(CriteriaTotalsModelBuilder? totals) => _$this._totals = totals;

  ListBuilder<int>? _unreadablePages;
  ListBuilder<int> get unreadablePages =>
      _$this._unreadablePages ??= ListBuilder<int>();
  set unreadablePages(ListBuilder<int>? unreadablePages) =>
      _$this._unreadablePages = unreadablePages;

  CriteriaResponseBuilder() {
    CriteriaResponse._defaults(this);
  }

  CriteriaResponseBuilder get _$this {
    final $v = _$v;
    if ($v != null) {
      _declaredTotalPoints = $v.declaredTotalPoints;
      _extracted = $v.extracted;
      _note = $v.note;
      _questions = $v.questions.toBuilder();
      _revision = $v.revision;
      _status = $v.status;
      _testId = $v.testId;
      _totals = $v.totals.toBuilder();
      _unreadablePages = $v.unreadablePages.toBuilder();
      _$v = null;
    }
    return this;
  }

  @override
  void replace(CriteriaResponse other) {
    _$v = other as _$CriteriaResponse;
  }

  @override
  void update(void Function(CriteriaResponseBuilder)? updates) {
    if (updates != null) updates(this);
  }

  @override
  CriteriaResponse build() => _build();

  _$CriteriaResponse _build() {
    _$CriteriaResponse _$result;
    try {
      _$result = _$v ??
          _$CriteriaResponse._(
            declaredTotalPoints: declaredTotalPoints,
            extracted: BuiltValueNullFieldError.checkNotNull(
                extracted, r'CriteriaResponse', 'extracted'),
            note: note,
            questions: questions.build(),
            revision: BuiltValueNullFieldError.checkNotNull(
                revision, r'CriteriaResponse', 'revision'),
            status: BuiltValueNullFieldError.checkNotNull(
                status, r'CriteriaResponse', 'status'),
            testId: BuiltValueNullFieldError.checkNotNull(
                testId, r'CriteriaResponse', 'testId'),
            totals: totals.build(),
            unreadablePages: unreadablePages.build(),
          );
    } catch (_) {
      late String _$failedField;
      try {
        _$failedField = 'questions';
        questions.build();

        _$failedField = 'totals';
        totals.build();
        _$failedField = 'unreadablePages';
        unreadablePages.build();
      } catch (e) {
        throw BuiltValueNestedFieldError(
            r'CriteriaResponse', _$failedField, e.toString());
      }
      rethrow;
    }
    replace(_$result);
    return _$result;
  }
}

// ignore_for_file: deprecated_member_use_from_same_package,type=lint
