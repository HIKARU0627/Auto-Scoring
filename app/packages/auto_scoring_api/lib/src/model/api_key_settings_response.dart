//
// AUTO-GENERATED FILE, DO NOT MODIFY!
//

// ignore_for_file: unused_element
import 'package:auto_scoring_api/src/model/configuration_source.dart';
import 'package:built_collection/built_collection.dart';
import 'package:auto_scoring_api/src/model/api_key_status_model.dart';
import 'package:built_value/built_value.dart';
import 'package:built_value/serializer.dart';

part 'api_key_settings_response.g.dart';

/// The whole screen's state, so one round trip refreshes all of it.
///
/// Properties:
/// * [keys]
/// * [restartRequired]
/// * [storeUnavailableReason]
/// * [transportOrder]
/// * [transportSource]
@BuiltValue()
abstract class ApiKeySettingsResponse
    implements Built<ApiKeySettingsResponse, ApiKeySettingsResponseBuilder> {
  @BuiltValueField(wireName: r'keys')
  BuiltList<ApiKeyStatusModel> get keys;

  @BuiltValueField(wireName: r'restart_required')
  bool get restartRequired;

  @BuiltValueField(wireName: r'store_unavailable_reason')
  String? get storeUnavailableReason;

  @BuiltValueField(wireName: r'transport_order')
  String get transportOrder;

  @BuiltValueField(wireName: r'transport_source')
  ConfigurationSource get transportSource;
  // enum transportSourceEnum {  credential_store,  environment,  builtin_default,  none,  };

  ApiKeySettingsResponse._();

  factory ApiKeySettingsResponse(
          [void updates(ApiKeySettingsResponseBuilder b)]) =
      _$ApiKeySettingsResponse;

  @BuiltValueHook(initializeBuilder: true)
  static void _defaults(ApiKeySettingsResponseBuilder b) => b;

  @BuiltValueSerializer(custom: true)
  static Serializer<ApiKeySettingsResponse> get serializer =>
      _$ApiKeySettingsResponseSerializer();
}

class _$ApiKeySettingsResponseSerializer
    implements PrimitiveSerializer<ApiKeySettingsResponse> {
  @override
  final Iterable<Type> types = const [
    ApiKeySettingsResponse,
    _$ApiKeySettingsResponse
  ];

  @override
  final String wireName = r'ApiKeySettingsResponse';

  Iterable<Object?> _serializeProperties(
    Serializers serializers,
    ApiKeySettingsResponse object, {
    FullType specifiedType = FullType.unspecified,
  }) sync* {
    yield r'keys';
    yield serializers.serialize(
      object.keys,
      specifiedType: const FullType(BuiltList, [FullType(ApiKeyStatusModel)]),
    );
    yield r'restart_required';
    yield serializers.serialize(
      object.restartRequired,
      specifiedType: const FullType(bool),
    );
    if (object.storeUnavailableReason != null) {
      yield r'store_unavailable_reason';
      yield serializers.serialize(
        object.storeUnavailableReason,
        specifiedType: const FullType.nullable(String),
      );
    }
    yield r'transport_order';
    yield serializers.serialize(
      object.transportOrder,
      specifiedType: const FullType(String),
    );
    yield r'transport_source';
    yield serializers.serialize(
      object.transportSource,
      specifiedType: const FullType(ConfigurationSource),
    );
  }

  @override
  Object serialize(
    Serializers serializers,
    ApiKeySettingsResponse object, {
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
    required ApiKeySettingsResponseBuilder result,
    required List<Object?> unhandled,
  }) {
    for (var i = 0; i < serializedList.length; i += 2) {
      final key = serializedList[i] as String;
      final value = serializedList[i + 1];
      switch (key) {
        case r'keys':
          final valueDes = serializers.deserialize(
            value,
            specifiedType:
                const FullType(BuiltList, [FullType(ApiKeyStatusModel)]),
          ) as BuiltList<ApiKeyStatusModel>;
          result.keys.replace(valueDes);
          break;
        case r'restart_required':
          final valueDes = serializers.deserialize(
            value,
            specifiedType: const FullType(bool),
          ) as bool;
          result.restartRequired = valueDes;
          break;
        case r'store_unavailable_reason':
          final valueDes = serializers.deserialize(
            value,
            specifiedType: const FullType.nullable(String),
          ) as String?;
          if (valueDes == null) continue;
          result.storeUnavailableReason = valueDes;
          break;
        case r'transport_order':
          final valueDes = serializers.deserialize(
            value,
            specifiedType: const FullType(String),
          ) as String;
          result.transportOrder = valueDes;
          break;
        case r'transport_source':
          final valueDes = serializers.deserialize(
            value,
            specifiedType: const FullType(ConfigurationSource),
          ) as ConfigurationSource;
          result.transportSource = valueDes;
          break;
        default:
          unhandled.add(key);
          unhandled.add(value);
          break;
      }
    }
  }

  @override
  ApiKeySettingsResponse deserialize(
    Serializers serializers,
    Object serialized, {
    FullType specifiedType = FullType.unspecified,
  }) {
    final result = ApiKeySettingsResponseBuilder();
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
