//
// AUTO-GENERATED FILE, DO NOT MODIFY!
//

// ignore_for_file: unused_element
import 'package:built_value/built_value.dart';
import 'package:built_value/serializer.dart';

part 'confirm_profile_request.g.dart';

/// ConfirmProfileRequest
///
/// Properties:
/// * [revision]
@BuiltValue()
abstract class ConfirmProfileRequest
    implements Built<ConfirmProfileRequest, ConfirmProfileRequestBuilder> {
  @BuiltValueField(wireName: r'revision')
  int get revision;

  ConfirmProfileRequest._();

  factory ConfirmProfileRequest(
      [void updates(ConfirmProfileRequestBuilder b)]) = _$ConfirmProfileRequest;

  @BuiltValueHook(initializeBuilder: true)
  static void _defaults(ConfirmProfileRequestBuilder b) => b;

  @BuiltValueSerializer(custom: true)
  static Serializer<ConfirmProfileRequest> get serializer =>
      _$ConfirmProfileRequestSerializer();
}

class _$ConfirmProfileRequestSerializer
    implements PrimitiveSerializer<ConfirmProfileRequest> {
  @override
  final Iterable<Type> types = const [
    ConfirmProfileRequest,
    _$ConfirmProfileRequest
  ];

  @override
  final String wireName = r'ConfirmProfileRequest';

  Iterable<Object?> _serializeProperties(
    Serializers serializers,
    ConfirmProfileRequest object, {
    FullType specifiedType = FullType.unspecified,
  }) sync* {
    yield r'revision';
    yield serializers.serialize(
      object.revision,
      specifiedType: const FullType(int),
    );
  }

  @override
  Object serialize(
    Serializers serializers,
    ConfirmProfileRequest object, {
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
    required ConfirmProfileRequestBuilder result,
    required List<Object?> unhandled,
  }) {
    for (var i = 0; i < serializedList.length; i += 2) {
      final key = serializedList[i] as String;
      final value = serializedList[i + 1];
      switch (key) {
        case r'revision':
          final valueDes = serializers.deserialize(
            value,
            specifiedType: const FullType(int),
          ) as int;
          result.revision = valueDes;
          break;
        default:
          unhandled.add(key);
          unhandled.add(value);
          break;
      }
    }
  }

  @override
  ConfirmProfileRequest deserialize(
    Serializers serializers,
    Object serialized, {
    FullType specifiedType = FullType.unspecified,
  }) {
    final result = ConfirmProfileRequestBuilder();
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
