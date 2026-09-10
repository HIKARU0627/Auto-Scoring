//
// AUTO-GENERATED FILE, DO NOT MODIFY!
//

// ignore_for_file: unused_element
import 'package:built_value/built_value.dart';
import 'package:built_value/serializer.dart';

part 'save_api_key_request.g.dart';

/// SaveApiKeyRequest
///
/// Properties:
/// * [value]
@BuiltValue()
abstract class SaveApiKeyRequest
    implements Built<SaveApiKeyRequest, SaveApiKeyRequestBuilder> {
  @BuiltValueField(wireName: r'value')
  String get value;

  SaveApiKeyRequest._();

  factory SaveApiKeyRequest([void updates(SaveApiKeyRequestBuilder b)]) =
      _$SaveApiKeyRequest;

  @BuiltValueHook(initializeBuilder: true)
  static void _defaults(SaveApiKeyRequestBuilder b) => b;

  @BuiltValueSerializer(custom: true)
  static Serializer<SaveApiKeyRequest> get serializer =>
      _$SaveApiKeyRequestSerializer();
}

class _$SaveApiKeyRequestSerializer
    implements PrimitiveSerializer<SaveApiKeyRequest> {
  @override
  final Iterable<Type> types = const [SaveApiKeyRequest, _$SaveApiKeyRequest];

  @override
  final String wireName = r'SaveApiKeyRequest';

  Iterable<Object?> _serializeProperties(
    Serializers serializers,
    SaveApiKeyRequest object, {
    FullType specifiedType = FullType.unspecified,
  }) sync* {
    yield r'value';
    yield serializers.serialize(
      object.value,
      specifiedType: const FullType(String),
    );
  }

  @override
  Object serialize(
    Serializers serializers,
    SaveApiKeyRequest object, {
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
    required SaveApiKeyRequestBuilder result,
    required List<Object?> unhandled,
  }) {
    for (var i = 0; i < serializedList.length; i += 2) {
      final key = serializedList[i] as String;
      final value = serializedList[i + 1];
      switch (key) {
        case r'value':
          final valueDes = serializers.deserialize(
            value,
            specifiedType: const FullType(String),
          ) as String;
          result.value = valueDes;
          break;
        default:
          unhandled.add(key);
          unhandled.add(value);
          break;
      }
    }
  }

  @override
  SaveApiKeyRequest deserialize(
    Serializers serializers,
    Object serialized, {
    FullType specifiedType = FullType.unspecified,
  }) {
    final result = SaveApiKeyRequestBuilder();
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
