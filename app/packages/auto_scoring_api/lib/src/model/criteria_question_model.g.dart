// GENERATED CODE - DO NOT MODIFY BY HAND

part of 'criteria_question_model.dart';

// **************************************************************************
// BuiltValueGenerator
// **************************************************************************

class _$CriteriaQuestionModel extends CriteriaQuestionModel {
  @override
  final BuiltList<CriteriaItemModel> criteria;
  @override
  final String? modelAnswer;
  @override
  final String? note;
  @override
  final String number;
  @override
  final int? points;
  @override
  final BuiltList<int> sourcePages;

  factory _$CriteriaQuestionModel(
          [void Function(CriteriaQuestionModelBuilder)? updates]) =>
      (CriteriaQuestionModelBuilder()..update(updates))._build();

  _$CriteriaQuestionModel._(
      {required this.criteria,
      this.modelAnswer,
      this.note,
      required this.number,
      this.points,
      required this.sourcePages})
      : super._();
  @override
  CriteriaQuestionModel rebuild(
          void Function(CriteriaQuestionModelBuilder) updates) =>
      (toBuilder()..update(updates)).build();

  @override
  CriteriaQuestionModelBuilder toBuilder() =>
      CriteriaQuestionModelBuilder()..replace(this);

  @override
  bool operator ==(Object other) {
    if (identical(other, this)) return true;
    return other is CriteriaQuestionModel &&
        criteria == other.criteria &&
        modelAnswer == other.modelAnswer &&
        note == other.note &&
        number == other.number &&
        points == other.points &&
        sourcePages == other.sourcePages;
  }

  @override
  int get hashCode {
    var _$hash = 0;
    _$hash = $jc(_$hash, criteria.hashCode);
    _$hash = $jc(_$hash, modelAnswer.hashCode);
    _$hash = $jc(_$hash, note.hashCode);
    _$hash = $jc(_$hash, number.hashCode);
    _$hash = $jc(_$hash, points.hashCode);
    _$hash = $jc(_$hash, sourcePages.hashCode);
    _$hash = $jf(_$hash);
    return _$hash;
  }

  @override
  String toString() {
    return (newBuiltValueToStringHelper(r'CriteriaQuestionModel')
          ..add('criteria', criteria)
          ..add('modelAnswer', modelAnswer)
          ..add('note', note)
          ..add('number', number)
          ..add('points', points)
          ..add('sourcePages', sourcePages))
        .toString();
  }
}

class CriteriaQuestionModelBuilder
    implements Builder<CriteriaQuestionModel, CriteriaQuestionModelBuilder> {
  _$CriteriaQuestionModel? _$v;

  ListBuilder<CriteriaItemModel>? _criteria;
  ListBuilder<CriteriaItemModel> get criteria =>
      _$this._criteria ??= ListBuilder<CriteriaItemModel>();
  set criteria(ListBuilder<CriteriaItemModel>? criteria) =>
      _$this._criteria = criteria;

  String? _modelAnswer;
  String? get modelAnswer => _$this._modelAnswer;
  set modelAnswer(String? modelAnswer) => _$this._modelAnswer = modelAnswer;

  String? _note;
  String? get note => _$this._note;
  set note(String? note) => _$this._note = note;

  String? _number;
  String? get number => _$this._number;
  set number(String? number) => _$this._number = number;

  int? _points;
  int? get points => _$this._points;
  set points(int? points) => _$this._points = points;

  ListBuilder<int>? _sourcePages;
  ListBuilder<int> get sourcePages =>
      _$this._sourcePages ??= ListBuilder<int>();
  set sourcePages(ListBuilder<int>? sourcePages) =>
      _$this._sourcePages = sourcePages;

  CriteriaQuestionModelBuilder() {
    CriteriaQuestionModel._defaults(this);
  }

  CriteriaQuestionModelBuilder get _$this {
    final $v = _$v;
    if ($v != null) {
      _criteria = $v.criteria.toBuilder();
      _modelAnswer = $v.modelAnswer;
      _note = $v.note;
      _number = $v.number;
      _points = $v.points;
      _sourcePages = $v.sourcePages.toBuilder();
      _$v = null;
    }
    return this;
  }

  @override
  void replace(CriteriaQuestionModel other) {
    _$v = other as _$CriteriaQuestionModel;
  }

  @override
  void update(void Function(CriteriaQuestionModelBuilder)? updates) {
    if (updates != null) updates(this);
  }

  @override
  CriteriaQuestionModel build() => _build();

  _$CriteriaQuestionModel _build() {
    _$CriteriaQuestionModel _$result;
    try {
      _$result = _$v ??
          _$CriteriaQuestionModel._(
            criteria: criteria.build(),
            modelAnswer: modelAnswer,
            note: note,
            number: BuiltValueNullFieldError.checkNotNull(
                number, r'CriteriaQuestionModel', 'number'),
            points: points,
            sourcePages: sourcePages.build(),
          );
    } catch (_) {
      late String _$failedField;
      try {
        _$failedField = 'criteria';
        criteria.build();

        _$failedField = 'sourcePages';
        sourcePages.build();
      } catch (e) {
        throw BuiltValueNestedFieldError(
            r'CriteriaQuestionModel', _$failedField, e.toString());
      }
      rethrow;
    }
    replace(_$result);
    return _$result;
  }
}

// ignore_for_file: deprecated_member_use_from_same_package,type=lint
