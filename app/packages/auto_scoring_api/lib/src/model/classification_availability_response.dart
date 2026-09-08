//
// AUTO-GENERATED FILE, DO NOT MODIFY!
//

// ignore_for_file: unused_element
import 'package:built_value/built_value.dart';
import 'package:built_value/serializer.dart';

part 'classification_availability_response.g.dart';

/// ClassificationAvailabilityResponse
///
/// Properties:
/// * [available]
/// * [reason]
@BuiltValue()
abstract class ClassificationAvailabilityResponse
    implements
        Built<ClassificationAvailabilityResponse,
            ClassificationAvailabilityResponseBuilder> {
  @BuiltValueField(wireName: r'available')
  bool get available;

  @BuiltValueField(wireName: r'reason')
  String? get reason;

  ClassificationAvailabilityResponse._();

  factory ClassificationAvailabilityResponse(
          [void updates(ClassificationAvailabilityResponseBuilder b)]) =
      _$ClassificationAvailabilityResponse;

  @BuiltValueHook(initializeBuilder: true)
  static void _defaults(ClassificationAvailabilityResponseBuilder b) => b;

  @BuiltValueSerializer(custom: true)
  static Serializer<ClassificationAvailabilityResponse> get serializer =>
      _$ClassificationAvailabilityResponseSerializer();
}

class _$ClassificationAvailabilityResponseSerializer
    implements PrimitiveSerializer<ClassificationAvailabilityResponse> {
  @override
  final Iterable<Type> types = const [
    ClassificationAvailabilityResponse,
    _$ClassificationAvailabilityResponse
  ];

  @override
  final String wireName = r'ClassificationAvailabilityResponse';

  Iterable<Object?> _serializeProperties(
    Serializers serializers,
    ClassificationAvailabilityResponse object, {
    FullType specifiedType = FullType.unspecified,
  }) sync* {
    yield r'available';
    yield serializers.serialize(
      object.available,
      specifiedType: const FullType(bool),
    );
    if (object.reason != null) {
      yield r'reason';
      yield serializers.serialize(
        object.reason,
        specifiedType: const FullType.nullable(String),
      );
    }
  }

  @override
  Object serialize(
    Serializers serializers,
    ClassificationAvailabilityResponse object, {
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
    required ClassificationAvailabilityResponseBuilder result,
    required List<Object?> unhandled,
  }) {
    for (var i = 0; i < serializedList.length; i += 2) {
      final key = serializedList[i] as String;
      final value = serializedList[i + 1];
      switch (key) {
        case r'available':
          final valueDes = serializers.deserialize(
            value,
            specifiedType: const FullType(bool),
          ) as bool;
          result.available = valueDes;
          break;
        case r'reason':
          final valueDes = serializers.deserialize(
            value,
            specifiedType: const FullType.nullable(String),
          ) as String?;
          if (valueDes == null) continue;
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
  ClassificationAvailabilityResponse deserialize(
    Serializers serializers,
    Object serialized, {
    FullType specifiedType = FullType.unspecified,
  }) {
    final result = ClassificationAvailabilityResponseBuilder();
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
