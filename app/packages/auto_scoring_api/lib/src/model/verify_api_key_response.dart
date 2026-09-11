//
// AUTO-GENERATED FILE, DO NOT MODIFY!
//

// ignore_for_file: unused_element
import 'package:auto_scoring_api/src/model/configuration_source.dart';
import 'package:built_value/built_value.dart';
import 'package:built_value/serializer.dart';

part 'verify_api_key_response.g.dart';

/// The outcome of one live call. Fixed sentences and a status number.
///
/// Properties:
/// * [detail]
/// * [keySource]
/// * [providerAccountLimit]
/// * [providerAccountUsage]
/// * [result]
/// * [statusCode]
@BuiltValue()
abstract class VerifyApiKeyResponse
    implements Built<VerifyApiKeyResponse, VerifyApiKeyResponseBuilder> {
  @BuiltValueField(wireName: r'detail')
  String get detail;

  @BuiltValueField(wireName: r'key_source')
  ConfigurationSource get keySource;
  // enum keySourceEnum {  credential_store,  environment,  builtin_default,  none,  };

  @BuiltValueField(wireName: r'provider_account_limit')
  num? get providerAccountLimit;

  @BuiltValueField(wireName: r'provider_account_usage')
  num? get providerAccountUsage;

  @BuiltValueField(wireName: r'result')
  String get result;

  @BuiltValueField(wireName: r'status_code')
  int? get statusCode;

  VerifyApiKeyResponse._();

  factory VerifyApiKeyResponse([void updates(VerifyApiKeyResponseBuilder b)]) =
      _$VerifyApiKeyResponse;

  @BuiltValueHook(initializeBuilder: true)
  static void _defaults(VerifyApiKeyResponseBuilder b) => b;

  @BuiltValueSerializer(custom: true)
  static Serializer<VerifyApiKeyResponse> get serializer =>
      _$VerifyApiKeyResponseSerializer();
}

class _$VerifyApiKeyResponseSerializer
    implements PrimitiveSerializer<VerifyApiKeyResponse> {
  @override
  final Iterable<Type> types = const [
    VerifyApiKeyResponse,
    _$VerifyApiKeyResponse
  ];

  @override
  final String wireName = r'VerifyApiKeyResponse';

  Iterable<Object?> _serializeProperties(
    Serializers serializers,
    VerifyApiKeyResponse object, {
    FullType specifiedType = FullType.unspecified,
  }) sync* {
    yield r'detail';
    yield serializers.serialize(
      object.detail,
      specifiedType: const FullType(String),
    );
    yield r'key_source';
    yield serializers.serialize(
      object.keySource,
      specifiedType: const FullType(ConfigurationSource),
    );
    if (object.providerAccountLimit != null) {
      yield r'provider_account_limit';
      yield serializers.serialize(
        object.providerAccountLimit,
        specifiedType: const FullType.nullable(num),
      );
    }
    if (object.providerAccountUsage != null) {
      yield r'provider_account_usage';
      yield serializers.serialize(
        object.providerAccountUsage,
        specifiedType: const FullType.nullable(num),
      );
    }
    yield r'result';
    yield serializers.serialize(
      object.result,
      specifiedType: const FullType(String),
    );
    if (object.statusCode != null) {
      yield r'status_code';
      yield serializers.serialize(
        object.statusCode,
        specifiedType: const FullType.nullable(int),
      );
    }
  }

  @override
  Object serialize(
    Serializers serializers,
    VerifyApiKeyResponse object, {
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
    required VerifyApiKeyResponseBuilder result,
    required List<Object?> unhandled,
  }) {
    for (var i = 0; i < serializedList.length; i += 2) {
      final key = serializedList[i] as String;
      final value = serializedList[i + 1];
      switch (key) {
        case r'detail':
          final valueDes = serializers.deserialize(
            value,
            specifiedType: const FullType(String),
          ) as String;
          result.detail = valueDes;
          break;
        case r'key_source':
          final valueDes = serializers.deserialize(
            value,
            specifiedType: const FullType(ConfigurationSource),
          ) as ConfigurationSource;
          result.keySource = valueDes;
          break;
        case r'provider_account_limit':
          final valueDes = serializers.deserialize(
            value,
            specifiedType: const FullType.nullable(num),
          ) as num?;
          if (valueDes == null) continue;
          result.providerAccountLimit = valueDes;
          break;
        case r'provider_account_usage':
          final valueDes = serializers.deserialize(
            value,
            specifiedType: const FullType.nullable(num),
          ) as num?;
          if (valueDes == null) continue;
          result.providerAccountUsage = valueDes;
          break;
        case r'result':
          final valueDes = serializers.deserialize(
            value,
            specifiedType: const FullType(String),
          ) as String;
          result.result = valueDes;
          break;
        case r'status_code':
          final valueDes = serializers.deserialize(
            value,
            specifiedType: const FullType.nullable(int),
          ) as int?;
          if (valueDes == null) continue;
          result.statusCode = valueDes;
          break;
        default:
          unhandled.add(key);
          unhandled.add(value);
          break;
      }
    }
  }

  @override
  VerifyApiKeyResponse deserialize(
    Serializers serializers,
    Object serialized, {
    FullType specifiedType = FullType.unspecified,
  }) {
    final result = VerifyApiKeyResponseBuilder();
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
