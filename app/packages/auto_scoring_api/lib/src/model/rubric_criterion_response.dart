//
// AUTO-GENERATED FILE, DO NOT MODIFY!
//

// ignore_for_file: unused_element
import 'package:built_value/built_value.dart';
import 'package:built_value/serializer.dart';

part 'rubric_criterion_response.g.dart';

/// RubricCriterionResponse
///
/// Properties:
/// * [description]
/// * [id]
/// * [maxPoints]
/// * [position]
@BuiltValue()
abstract class RubricCriterionResponse
    implements Built<RubricCriterionResponse, RubricCriterionResponseBuilder> {
  @BuiltValueField(wireName: r'description')
  String get description;

  @BuiltValueField(wireName: r'id')
  String get id;

  @BuiltValueField(wireName: r'max_points')
  int get maxPoints;

  @BuiltValueField(wireName: r'position')
  int get position;

  RubricCriterionResponse._();

  factory RubricCriterionResponse(
          [void updates(RubricCriterionResponseBuilder b)]) =
      _$RubricCriterionResponse;

  @BuiltValueHook(initializeBuilder: true)
  static void _defaults(RubricCriterionResponseBuilder b) => b;

  @BuiltValueSerializer(custom: true)
  static Serializer<RubricCriterionResponse> get serializer =>
      _$RubricCriterionResponseSerializer();
}

class _$RubricCriterionResponseSerializer
    implements PrimitiveSerializer<RubricCriterionResponse> {
  @override
  final Iterable<Type> types = const [
    RubricCriterionResponse,
    _$RubricCriterionResponse
  ];

  @override
  final String wireName = r'RubricCriterionResponse';

  Iterable<Object?> _serializeProperties(
    Serializers serializers,
    RubricCriterionResponse object, {
    FullType specifiedType = FullType.unspecified,
  }) sync* {
    yield r'description';
    yield serializers.serialize(
      object.description,
      specifiedType: const FullType(String),
    );
    yield r'id';
    yield serializers.serialize(
      object.id,
      specifiedType: const FullType(String),
    );
    yield r'max_points';
    yield serializers.serialize(
      object.maxPoints,
      specifiedType: const FullType(int),
    );
    yield r'position';
    yield serializers.serialize(
      object.position,
      specifiedType: const FullType(int),
    );
  }

  @override
  Object serialize(
    Serializers serializers,
    RubricCriterionResponse object, {
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
    required RubricCriterionResponseBuilder result,
    required List<Object?> unhandled,
  }) {
    for (var i = 0; i < serializedList.length; i += 2) {
      final key = serializedList[i] as String;
      final value = serializedList[i + 1];
      switch (key) {
        case r'description':
          final valueDes = serializers.deserialize(
            value,
            specifiedType: const FullType(String),
          ) as String;
          result.description = valueDes;
          break;
        case r'id':
          final valueDes = serializers.deserialize(
            value,
            specifiedType: const FullType(String),
          ) as String;
          result.id = valueDes;
          break;
        case r'max_points':
          final valueDes = serializers.deserialize(
            value,
            specifiedType: const FullType(int),
          ) as int;
          result.maxPoints = valueDes;
          break;
        case r'position':
          final valueDes = serializers.deserialize(
            value,
            specifiedType: const FullType(int),
          ) as int;
          result.position = valueDes;
          break;
        default:
          unhandled.add(key);
          unhandled.add(value);
          break;
      }
    }
  }

  @override
  RubricCriterionResponse deserialize(
    Serializers serializers,
    Object serialized, {
    FullType specifiedType = FullType.unspecified,
  }) {
    final result = RubricCriterionResponseBuilder();
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
