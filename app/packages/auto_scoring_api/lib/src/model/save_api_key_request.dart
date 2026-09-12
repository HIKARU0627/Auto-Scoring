//
// AUTO-GENERATED FILE, DO NOT MODIFY!
//

// ignore_for_file: unused_element
import 'package:built_collection/built_collection.dart';
import 'package:built_value/built_value.dart';
import 'package:built_value/serializer.dart';

part 'save_api_key_request.g.dart';

/// Values submitted for one slot; a blank value clears that setting.  Named for the screen it comes from rather than \"slot\", so the generated Dart/TS clients stay legible. ``value`` is kept as a key-only shorthand for backward compatibility with the Issue #96 clients.
///
/// Properties:
/// * [value]
/// * [values]
@BuiltValue()
abstract class SaveApiKeyRequest
    implements Built<SaveApiKeyRequest, SaveApiKeyRequestBuilder> {
  @BuiltValueField(wireName: r'value')
  String? get value;

  @BuiltValueField(wireName: r'values')
  BuiltMap<String, String?>? get values;

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
    if (object.value != null) {
      yield r'value';
      yield serializers.serialize(
        object.value,
        specifiedType: const FullType.nullable(String),
      );
    }
    if (object.values != null) {
      yield r'values';
      yield serializers.serialize(
        object.values,
        specifiedType: const FullType(
            BuiltMap, [FullType(String), FullType.nullable(String)]),
      );
    }
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
            specifiedType: const FullType.nullable(String),
          ) as String?;
          if (valueDes == null) continue;
          result.value = valueDes;
          break;
        case r'values':
          final valueDes = serializers.deserialize(
            value,
            specifiedType: const FullType.nullable(
                BuiltMap, [FullType(String), FullType.nullable(String)]),
          ) as BuiltMap<String, String?>?;
          if (valueDes == null) continue;
          result.values.replace(valueDes);
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
