//
// AUTO-GENERATED FILE, DO NOT MODIFY!
//

// ignore_for_file: unused_element
import 'package:auto_scoring_api/src/model/configuration_source.dart';
import 'package:built_value/built_value.dart';
import 'package:built_value/serializer.dart';

part 'api_key_status_model.g.dart';

/// One provider's key, described without disclosing it.
///
/// Properties:
/// * [configured]
/// * [consoleUrl]
/// * [id]
/// * [keySource]
/// * [keyVariable]
/// * [label]
/// * [model]
/// * [modelSource]
@BuiltValue()
abstract class ApiKeyStatusModel
    implements Built<ApiKeyStatusModel, ApiKeyStatusModelBuilder> {
  @BuiltValueField(wireName: r'configured')
  bool get configured;

  @BuiltValueField(wireName: r'console_url')
  String get consoleUrl;

  @BuiltValueField(wireName: r'id')
  String get id;

  @BuiltValueField(wireName: r'key_source')
  ConfigurationSource get keySource;
  // enum keySourceEnum {  credential_store,  environment,  builtin_default,  none,  };

  @BuiltValueField(wireName: r'key_variable')
  String get keyVariable;

  @BuiltValueField(wireName: r'label')
  String get label;

  @BuiltValueField(wireName: r'model')
  String get model;

  @BuiltValueField(wireName: r'model_source')
  ConfigurationSource get modelSource;
  // enum modelSourceEnum {  credential_store,  environment,  builtin_default,  none,  };

  ApiKeyStatusModel._();

  factory ApiKeyStatusModel([void updates(ApiKeyStatusModelBuilder b)]) =
      _$ApiKeyStatusModel;

  @BuiltValueHook(initializeBuilder: true)
  static void _defaults(ApiKeyStatusModelBuilder b) => b;

  @BuiltValueSerializer(custom: true)
  static Serializer<ApiKeyStatusModel> get serializer =>
      _$ApiKeyStatusModelSerializer();
}

class _$ApiKeyStatusModelSerializer
    implements PrimitiveSerializer<ApiKeyStatusModel> {
  @override
  final Iterable<Type> types = const [ApiKeyStatusModel, _$ApiKeyStatusModel];

  @override
  final String wireName = r'ApiKeyStatusModel';

  Iterable<Object?> _serializeProperties(
    Serializers serializers,
    ApiKeyStatusModel object, {
    FullType specifiedType = FullType.unspecified,
  }) sync* {
    yield r'configured';
    yield serializers.serialize(
      object.configured,
      specifiedType: const FullType(bool),
    );
    yield r'console_url';
    yield serializers.serialize(
      object.consoleUrl,
      specifiedType: const FullType(String),
    );
    yield r'id';
    yield serializers.serialize(
      object.id,
      specifiedType: const FullType(String),
    );
    yield r'key_source';
    yield serializers.serialize(
      object.keySource,
      specifiedType: const FullType(ConfigurationSource),
    );
    yield r'key_variable';
    yield serializers.serialize(
      object.keyVariable,
      specifiedType: const FullType(String),
    );
    yield r'label';
    yield serializers.serialize(
      object.label,
      specifiedType: const FullType(String),
    );
    yield r'model';
    yield serializers.serialize(
      object.model,
      specifiedType: const FullType(String),
    );
    yield r'model_source';
    yield serializers.serialize(
      object.modelSource,
      specifiedType: const FullType(ConfigurationSource),
    );
  }

  @override
  Object serialize(
    Serializers serializers,
    ApiKeyStatusModel object, {
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
    required ApiKeyStatusModelBuilder result,
    required List<Object?> unhandled,
  }) {
    for (var i = 0; i < serializedList.length; i += 2) {
      final key = serializedList[i] as String;
      final value = serializedList[i + 1];
      switch (key) {
        case r'configured':
          final valueDes = serializers.deserialize(
            value,
            specifiedType: const FullType(bool),
          ) as bool;
          result.configured = valueDes;
          break;
        case r'console_url':
          final valueDes = serializers.deserialize(
            value,
            specifiedType: const FullType(String),
          ) as String;
          result.consoleUrl = valueDes;
          break;
        case r'id':
          final valueDes = serializers.deserialize(
            value,
            specifiedType: const FullType(String),
          ) as String;
          result.id = valueDes;
          break;
        case r'key_source':
          final valueDes = serializers.deserialize(
            value,
            specifiedType: const FullType(ConfigurationSource),
          ) as ConfigurationSource;
          result.keySource = valueDes;
          break;
        case r'key_variable':
          final valueDes = serializers.deserialize(
            value,
            specifiedType: const FullType(String),
          ) as String;
          result.keyVariable = valueDes;
          break;
        case r'label':
          final valueDes = serializers.deserialize(
            value,
            specifiedType: const FullType(String),
          ) as String;
          result.label = valueDes;
          break;
        case r'model':
          final valueDes = serializers.deserialize(
            value,
            specifiedType: const FullType(String),
          ) as String;
          result.model = valueDes;
          break;
        case r'model_source':
          final valueDes = serializers.deserialize(
            value,
            specifiedType: const FullType(ConfigurationSource),
          ) as ConfigurationSource;
          result.modelSource = valueDes;
          break;
        default:
          unhandled.add(key);
          unhandled.add(value);
          break;
      }
    }
  }

  @override
  ApiKeyStatusModel deserialize(
    Serializers serializers,
    Object serialized, {
    FullType specifiedType = FullType.unspecified,
  }) {
    final result = ApiKeyStatusModelBuilder();
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
