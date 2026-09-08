//
// AUTO-GENERATED FILE, DO NOT MODIFY!
//

// ignore_for_file: unused_element
import 'package:built_collection/built_collection.dart';
import 'package:auto_scoring_api/src/model/criteria_question_model.dart';
import 'package:built_value/built_value.dart';
import 'package:built_value/serializer.dart';

part 'update_criteria_request.g.dart';

/// The reviewed question set to save.  ``declared_total_points`` is editable because the reviewer may be correcting a total the model misread, or clearing one it invented from a footer page number.
///
/// Properties:
/// * [declaredTotalPoints]
/// * [questions]
@BuiltValue()
abstract class UpdateCriteriaRequest
    implements Built<UpdateCriteriaRequest, UpdateCriteriaRequestBuilder> {
  @BuiltValueField(wireName: r'declared_total_points')
  int? get declaredTotalPoints;

  @BuiltValueField(wireName: r'questions')
  BuiltList<CriteriaQuestionModel> get questions;

  UpdateCriteriaRequest._();

  factory UpdateCriteriaRequest(
      [void updates(UpdateCriteriaRequestBuilder b)]) = _$UpdateCriteriaRequest;

  @BuiltValueHook(initializeBuilder: true)
  static void _defaults(UpdateCriteriaRequestBuilder b) => b;

  @BuiltValueSerializer(custom: true)
  static Serializer<UpdateCriteriaRequest> get serializer =>
      _$UpdateCriteriaRequestSerializer();
}

class _$UpdateCriteriaRequestSerializer
    implements PrimitiveSerializer<UpdateCriteriaRequest> {
  @override
  final Iterable<Type> types = const [
    UpdateCriteriaRequest,
    _$UpdateCriteriaRequest
  ];

  @override
  final String wireName = r'UpdateCriteriaRequest';

  Iterable<Object?> _serializeProperties(
    Serializers serializers,
    UpdateCriteriaRequest object, {
    FullType specifiedType = FullType.unspecified,
  }) sync* {
    if (object.declaredTotalPoints != null) {
      yield r'declared_total_points';
      yield serializers.serialize(
        object.declaredTotalPoints,
        specifiedType: const FullType.nullable(int),
      );
    }
    yield r'questions';
    yield serializers.serialize(
      object.questions,
      specifiedType:
          const FullType(BuiltList, [FullType(CriteriaQuestionModel)]),
    );
  }

  @override
  Object serialize(
    Serializers serializers,
    UpdateCriteriaRequest object, {
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
    required UpdateCriteriaRequestBuilder result,
    required List<Object?> unhandled,
  }) {
    for (var i = 0; i < serializedList.length; i += 2) {
      final key = serializedList[i] as String;
      final value = serializedList[i + 1];
      switch (key) {
        case r'declared_total_points':
          final valueDes = serializers.deserialize(
            value,
            specifiedType: const FullType.nullable(int),
          ) as int?;
          if (valueDes == null) continue;
          result.declaredTotalPoints = valueDes;
          break;
        case r'questions':
          final valueDes = serializers.deserialize(
            value,
            specifiedType:
                const FullType(BuiltList, [FullType(CriteriaQuestionModel)]),
          ) as BuiltList<CriteriaQuestionModel>;
          result.questions.replace(valueDes);
          break;
        default:
          unhandled.add(key);
          unhandled.add(value);
          break;
      }
    }
  }

  @override
  UpdateCriteriaRequest deserialize(
    Serializers serializers,
    Object serialized, {
    FullType specifiedType = FullType.unspecified,
  }) {
    final result = UpdateCriteriaRequestBuilder();
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
