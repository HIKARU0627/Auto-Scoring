// GENERATED CODE - DO NOT MODIFY BY HAND

part of 'question_text_override.dart';

// **************************************************************************
// BuiltValueGenerator
// **************************************************************************

class _$QuestionTextOverride extends QuestionTextOverride {
  @override
  final String? promptText;
  @override
  final String questionId;
  @override
  final String? rubricText;

  factory _$QuestionTextOverride(
          [void Function(QuestionTextOverrideBuilder)? updates]) =>
      (QuestionTextOverrideBuilder()..update(updates))._build();

  _$QuestionTextOverride._(
      {this.promptText, required this.questionId, this.rubricText})
      : super._();
  @override
  QuestionTextOverride rebuild(
          void Function(QuestionTextOverrideBuilder) updates) =>
      (toBuilder()..update(updates)).build();

  @override
  QuestionTextOverrideBuilder toBuilder() =>
      QuestionTextOverrideBuilder()..replace(this);

  @override
  bool operator ==(Object other) {
    if (identical(other, this)) return true;
    return other is QuestionTextOverride &&
        promptText == other.promptText &&
        questionId == other.questionId &&
        rubricText == other.rubricText;
  }

  @override
  int get hashCode {
    var _$hash = 0;
    _$hash = $jc(_$hash, promptText.hashCode);
    _$hash = $jc(_$hash, questionId.hashCode);
    _$hash = $jc(_$hash, rubricText.hashCode);
    _$hash = $jf(_$hash);
    return _$hash;
  }

  @override
  String toString() {
    return (newBuiltValueToStringHelper(r'QuestionTextOverride')
          ..add('promptText', promptText)
          ..add('questionId', questionId)
          ..add('rubricText', rubricText))
        .toString();
  }
}

class QuestionTextOverrideBuilder
    implements Builder<QuestionTextOverride, QuestionTextOverrideBuilder> {
  _$QuestionTextOverride? _$v;

  String? _promptText;
  String? get promptText => _$this._promptText;
  set promptText(String? promptText) => _$this._promptText = promptText;

  String? _questionId;
  String? get questionId => _$this._questionId;
  set questionId(String? questionId) => _$this._questionId = questionId;

  String? _rubricText;
  String? get rubricText => _$this._rubricText;
  set rubricText(String? rubricText) => _$this._rubricText = rubricText;

  QuestionTextOverrideBuilder() {
    QuestionTextOverride._defaults(this);
  }

  QuestionTextOverrideBuilder get _$this {
    final $v = _$v;
    if ($v != null) {
      _promptText = $v.promptText;
      _questionId = $v.questionId;
      _rubricText = $v.rubricText;
      _$v = null;
    }
    return this;
  }

  @override
  void replace(QuestionTextOverride other) {
    _$v = other as _$QuestionTextOverride;
  }

  @override
  void update(void Function(QuestionTextOverrideBuilder)? updates) {
    if (updates != null) updates(this);
  }

  @override
  QuestionTextOverride build() => _build();

  _$QuestionTextOverride _build() {
    final _$result = _$v ??
        _$QuestionTextOverride._(
          promptText: promptText,
          questionId: BuiltValueNullFieldError.checkNotNull(
              questionId, r'QuestionTextOverride', 'questionId'),
          rubricText: rubricText,
        );
    replace(_$result);
    return _$result;
  }
}

// ignore_for_file: deprecated_member_use_from_same_package,type=lint
