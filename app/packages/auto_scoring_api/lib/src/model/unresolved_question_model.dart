//
// AUTO-GENERATED FILE, DO NOT MODIFY!
//

// ignore_for_file: unused_element
import 'package:built_value/built_value.dart';
import 'package:built_value/serializer.dart';

part 'unresolved_question_model.g.dart';

/// UnresolvedQuestionModel
///
/// Properties:
/// * [questionId]
/// * [reason]
@BuiltValue()
abstract class UnresolvedQuestionModel
    implements Built<UnresolvedQuestionModel, UnresolvedQuestionModelBuilder> {
  @BuiltValueField(wireName: r'question_id')
  String get questionId;

  @BuiltValueField(wireName: r'reason')
  String get reason;

  UnresolvedQuestionModel._();

  factory UnresolvedQuestionModel(
          [void updates(UnresolvedQuestionModelBuilder b)]) =
      _$UnresolvedQuestionModel;

  @BuiltValueHook(initializeBuilder: true)
  static void _defaults(UnresolvedQuestionModelBuilder b) => b;

  @BuiltValueSerializer(custom: true)
  static Serializer<UnresolvedQuestionModel> get serializer =>
      _$UnresolvedQuestionModelSerializer();
}

class _$UnresolvedQuestionModelSerializer
    implements PrimitiveSerializer<UnresolvedQuestionModel> {
  @override
  final Iterable<Type> types = const [
    UnresolvedQuestionModel,
    _$UnresolvedQuestionModel
  ];

  @override
  final String wireName = r'UnresolvedQuestionModel';

  Iterable<Object?> _serializeProperties(
    Serializers serializers,
    UnresolvedQuestionModel object, {
    FullType specifiedType = FullType.unspecified,
  }) sync* {
    yield r'question_id';
    yield serializers.serialize(
      object.questionId,
      specifiedType: const FullType(String),
    );
    yield r'reason';
    yield serializers.serialize(
      object.reason,
      specifiedType: const FullType(String),
    );
  }

  @override
  Object serialize(
    Serializers serializers,
    UnresolvedQuestionModel object, {
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
    required UnresolvedQuestionModelBuilder result,
    required List<Object?> unhandled,
  }) {
    for (var i = 0; i < serializedList.length; i += 2) {
      final key = serializedList[i] as String;
      final value = serializedList[i + 1];
      switch (key) {
        case r'question_id':
          final valueDes = serializers.deserialize(
            value,
            specifiedType: const FullType(String),
          ) as String;
          result.questionId = valueDes;
          break;
        case r'reason':
          final valueDes = serializers.deserialize(
            value,
            specifiedType: const FullType(String),
          ) as String;
          result.reason = valueDes;
          break;
        default:
          unhandled.add(key);
          unhandled.add(value);
          break;
      }
    }
  }

  @override
  UnresolvedQuestionModel deserialize(
    Serializers serializers,
    Object serialized, {
    FullType specifiedType = FullType.unspecified,
  }) {
    final result = UnresolvedQuestionModelBuilder();
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
