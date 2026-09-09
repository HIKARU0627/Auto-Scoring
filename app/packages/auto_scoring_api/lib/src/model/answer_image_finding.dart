//
// AUTO-GENERATED FILE, DO NOT MODIFY!
//

// ignore_for_file: unused_element
import 'package:built_collection/built_collection.dart';
import 'package:built_value/built_value.dart';
import 'package:built_value/serializer.dart';

part 'answer_image_finding.g.dart';

/// What the grading AI reports it actually saw in the answer image it was given -- as distinct from the score it awarded (Issue #136).  Three values, not a boolean, and the reason is the whole point. On the real re-run that produced this Issue, 7 of the 14 questions that got a grade were a **wrong** 0 with confidence 1.00, and the AI's own rationale already said so in two different ways:  * 2 said the image it was given is not this question's answer at all   (one described a header field, one described another question's   label) -- :attr:`NOT_THE_ANSWER`; * 4 said only that the answer is blank -- :attr:`BLANK`.  Collapsing those into one \"something is wrong\" flag would put the same flag on a genuinely unanswered question, which is a real thing a student does and a correct 0. So the two claims stay separate values, and only :attr:`NOT_THE_ANSWER` currently stops a grade (`jobs.grading_processor`): a crop that does not show this question's answer is a *detection* failure, and no score derived from it means anything. :attr:`BLANK` is recorded and otherwise left alone until the frequency of genuinely unanswered questions has been measured -- see docs/ai-grading-pipeline.md.  ``None`` (the field's absence) is its own, fourth state everywhere this appears: the provider did not report anything. It is never read as :attr:`ANSWER` -- that would be vouching for a crop nothing looked at.
class AnswerImageFinding extends EnumClass {
  @BuiltValueEnumConst(wireName: r'answer')
  static const AnswerImageFinding answer = _$answer;
  @BuiltValueEnumConst(wireName: r'blank')
  static const AnswerImageFinding blank = _$blank;
  @BuiltValueEnumConst(wireName: r'not_the_answer')
  static const AnswerImageFinding notTheAnswer = _$notTheAnswer;

  static Serializer<AnswerImageFinding> get serializer =>
      _$answerImageFindingSerializer;

  const AnswerImageFinding._(String name) : super(name);

  static BuiltSet<AnswerImageFinding> get values => _$values;
  static AnswerImageFinding valueOf(String name) => _$valueOf(name);
}

/// Optionally, enum_class can generate a mixin to go with your enum for use
/// with Angular. It exposes your enum constants as getters. So, if you mix it
/// in to your Dart component class, the values become available to the
/// corresponding Angular template.
///
/// Trigger mixin generation by writing a line like this one next to your enum.
abstract class AnswerImageFindingMixin = Object with _$AnswerImageFindingMixin;
