//
// AUTO-GENERATED FILE, DO NOT MODIFY!
//

// ignore_for_file: unused_element
import 'package:auto_scoring_api/src/model/test_response.dart';
import 'package:built_value/built_value.dart';
import 'package:built_value/serializer.dart';

part 'complete_registration_response.g.dart';

/// CompleteRegistrationResponse
///
/// Properties:
/// * [dependencyGraphConfirmed]
/// * [profileConfirmed]
/// * [test]
@BuiltValue()
abstract class CompleteRegistrationResponse
    implements
        Built<CompleteRegistrationResponse,
            CompleteRegistrationResponseBuilder> {
  @BuiltValueField(wireName: r'dependency_graph_confirmed')
  bool get dependencyGraphConfirmed;

  @BuiltValueField(wireName: r'profile_confirmed')
  bool get profileConfirmed;

  @BuiltValueField(wireName: r'test')
  TestResponse get test;

  CompleteRegistrationResponse._();

  factory CompleteRegistrationResponse(
          [void updates(CompleteRegistrationResponseBuilder b)]) =
      _$CompleteRegistrationResponse;

  @BuiltValueHook(initializeBuilder: true)
  static void _defaults(CompleteRegistrationResponseBuilder b) => b;

  @BuiltValueSerializer(custom: true)
  static Serializer<CompleteRegistrationResponse> get serializer =>
      _$CompleteRegistrationResponseSerializer();
}

class _$CompleteRegistrationResponseSerializer
    implements PrimitiveSerializer<CompleteRegistrationResponse> {
  @override
  final Iterable<Type> types = const [
    CompleteRegistrationResponse,
    _$CompleteRegistrationResponse
  ];

  @override
  final String wireName = r'CompleteRegistrationResponse';

  Iterable<Object?> _serializeProperties(
    Serializers serializers,
    CompleteRegistrationResponse object, {
    FullType specifiedType = FullType.unspecified,
  }) sync* {
    yield r'dependency_graph_confirmed';
    yield serializers.serialize(
      object.dependencyGraphConfirmed,
      specifiedType: const FullType(bool),
    );
    yield r'profile_confirmed';
    yield serializers.serialize(
      object.profileConfirmed,
      specifiedType: const FullType(bool),
    );
    yield r'test';
    yield serializers.serialize(
      object.test,
      specifiedType: const FullType(TestResponse),
    );
  }

  @override
  Object serialize(
    Serializers serializers,
    CompleteRegistrationResponse object, {
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
    required CompleteRegistrationResponseBuilder result,
    required List<Object?> unhandled,
  }) {
    for (var i = 0; i < serializedList.length; i += 2) {
      final key = serializedList[i] as String;
      final value = serializedList[i + 1];
      switch (key) {
        case r'dependency_graph_confirmed':
          final valueDes = serializers.deserialize(
            value,
            specifiedType: const FullType(bool),
          ) as bool;
          result.dependencyGraphConfirmed = valueDes;
          break;
        case r'profile_confirmed':
          final valueDes = serializers.deserialize(
            value,
            specifiedType: const FullType(bool),
          ) as bool;
          result.profileConfirmed = valueDes;
          break;
        case r'test':
          final valueDes = serializers.deserialize(
            value,
            specifiedType: const FullType(TestResponse),
          ) as TestResponse;
          result.test.replace(valueDes);
          break;
        default:
          unhandled.add(key);
          unhandled.add(value);
          break;
      }
    }
  }

  @override
  CompleteRegistrationResponse deserialize(
    Serializers serializers,
    Object serialized, {
    FullType specifiedType = FullType.unspecified,
  }) {
    final result = CompleteRegistrationResponseBuilder();
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
