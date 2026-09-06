//
// AUTO-GENERATED FILE, DO NOT MODIFY!
//

// ignore_for_file: unused_element
import 'package:built_value/built_value.dart';
import 'package:built_value/serializer.dart';

part 'question_text_override.g.dart';

/// Extracted PDF text for one question, supplied by the caller.  The MVP question record (Issue #11) does not yet store 問題文 text extracted from the model-answer/manual PDFs, so the analyze request carries it explicitly -- once PDF text extraction exists this becomes the default and overrides stay optional.
///
/// Properties:
/// * [promptText]
/// * [questionId]
/// * [rubricText]
@BuiltValue()
abstract class QuestionTextOverride
    implements Built<QuestionTextOverride, QuestionTextOverrideBuilder> {
  @BuiltValueField(wireName: r'prompt_text')
  String? get promptText;

  @BuiltValueField(wireName: r'question_id')
  String get questionId;

  @BuiltValueField(wireName: r'rubric_text')
  String? get rubricText;

  QuestionTextOverride._();

  factory QuestionTextOverride([void updates(QuestionTextOverrideBuilder b)]) =
      _$QuestionTextOverride;

  @BuiltValueHook(initializeBuilder: true)
  static void _defaults(QuestionTextOverrideBuilder b) => b;

  @BuiltValueSerializer(custom: true)
  static Serializer<QuestionTextOverride> get serializer =>
      _$QuestionTextOverrideSerializer();
}

class _$QuestionTextOverrideSerializer
    implements PrimitiveSerializer<QuestionTextOverride> {
  @override
  final Iterable<Type> types = const [
    QuestionTextOverride,
    _$QuestionTextOverride
  ];

  @override
  final String wireName = r'QuestionTextOverride';

  Iterable<Object?> _serializeProperties(
    Serializers serializers,
    QuestionTextOverride object, {
    FullType specifiedType = FullType.unspecified,
  }) sync* {
    if (object.promptText != null) {
      yield r'prompt_text';
      yield serializers.serialize(
        object.promptText,
        specifiedType: const FullType.nullable(String),
      );
    }
    yield r'question_id';
    yield serializers.serialize(
      object.questionId,
      specifiedType: const FullType(String),
    );
    if (object.rubricText != null) {
      yield r'rubric_text';
      yield serializers.serialize(
        object.rubricText,
        specifiedType: const FullType.nullable(String),
      );
    }
  }

  @override
  Object serialize(
    Serializers serializers,
    QuestionTextOverride object, {
    FullType specifiedType = FullType.unspecified,
  }) {
    return _serializeProperties(serializers, object,
            specifiedType: specifiedType)
        .toList();
  }

  void _deserializeProperties(
    Serializers serializers,
    Object serialized, {
    FullType specifiedType = FullType.unspecified,
    required List<Object?> serializedList,
    required QuestionTextOverrideBuilder result,
    required List<Object?> unhandled,
  }) {
    for (var i = 0; i < serializedList.length; i += 2) {
      final key = serializedList[i] as String;
      final value = serializedList[i + 1];
      switch (key) {
        case r'prompt_text':
          final valueDes = serializers.deserialize(
            value,
            specifiedType: const FullType.nullable(String),
          ) as String?;
          if (valueDes == null) continue;
          result.promptText = valueDes;
          break;
        case r'question_id':
          final valueDes = serializers.deserialize(
            value,
            specifiedType: const FullType(String),
          ) as String;
          result.questionId = valueDes;
          break;
        case r'rubric_text':
          final valueDes = serializers.deserialize(
            value,
            specifiedType: const FullType.nullable(String),
          ) as String?;
          if (valueDes == null) continue;
          result.rubricText = valueDes;
          break;
        default:
          unhandled.add(key);
          unhandled.add(value);
          break;
      }
    }
  }

  @override
  QuestionTextOverride deserialize(
    Serializers serializers,
    Object serialized, {
    FullType specifiedType = FullType.unspecified,
  }) {
    final result = QuestionTextOverrideBuilder();
    final serializedList = (serialized as Iterable<Object?>).toList();
    final unhandled = <Object?>[];
    _deserializeProperties(
      serializers,
      serialized,
      specifiedType: specifiedType,
      serializedList: serializedList,
      unhandled: unhandled,
      result: result,
    );
    return result.build();
  }
}
