//
// AUTO-GENERATED FILE, DO NOT MODIFY!
//

// ignore_for_file: unused_element
import 'package:auto_scoring_api/src/model/text_setting_model.dart';
import 'package:auto_scoring_api/src/model/configuration_source.dart';
import 'package:built_collection/built_collection.dart';
import 'package:built_value/built_value.dart';
import 'package:built_value/serializer.dart';

part 'api_key_status_model.g.dart';

/// One provider, described without disclosing its key.
///
/// Properties:
/// * [authNote]
/// * [configured]
/// * [consoleUrl]
/// * [hostAvailable]
/// * [id]
/// * [keySource]
/// * [keyVariable]
/// * [label]
/// * [model]
/// * [modelSource]
/// * [modelVariable]
/// * [textSettings]
/// * [transport]
@BuiltValue()
abstract class ApiKeyStatusModel
    implements Built<ApiKeyStatusModel, ApiKeyStatusModelBuilder> {
  @BuiltValueField(wireName: r'auth_note')
  String get authNote;

  @BuiltValueField(wireName: r'configured')
  bool get configured;

  @BuiltValueField(wireName: r'console_url')
  String get consoleUrl;

  @BuiltValueField(wireName: r'host_available')
  bool? get hostAvailable;

  @BuiltValueField(wireName: r'id')
  String get id;

  @BuiltValueField(wireName: r'key_source')
  ConfigurationSource get keySource;
  // enum keySourceEnum {  credential_store,  environment,  builtin_default,  none,  };

  @BuiltValueField(wireName: r'key_variable')
  String? get keyVariable;

  @BuiltValueField(wireName: r'label')
  String get label;

  @BuiltValueField(wireName: r'model')
  String get model;

  @BuiltValueField(wireName: r'model_source')
  ConfigurationSource get modelSource;
  // enum modelSourceEnum {  credential_store,  environment,  builtin_default,  none,  };

  @BuiltValueField(wireName: r'model_variable')
  String get modelVariable;

  @BuiltValueField(wireName: r'text_settings')
  BuiltList<TextSettingModel> get textSettings;

  @BuiltValueField(wireName: r'transport')
  String get transport;

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
    yield r'auth_note';
    yield serializers.serialize(
      object.authNote,
      specifiedType: const FullType(String),
    );
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
    yield r'host_available';
    yield object.hostAvailable == null
        ? null
        : serializers.serialize(
            object.hostAvailable,
            specifiedType: const FullType.nullable(bool),
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
    yield object.keyVariable == null
        ? null
        : serializers.serialize(
            object.keyVariable,
            specifiedType: const FullType.nullable(String),
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
    yield r'model_variable';
    yield serializers.serialize(
      object.modelVariable,
      specifiedType: const FullType(String),
    );
    yield r'text_settings';
    yield serializers.serialize(
      object.textSettings,
      specifiedType: const FullType(BuiltList, [FullType(TextSettingModel)]),
    );
    yield r'transport';
    yield serializers.serialize(
      object.transport,
      specifiedType: const FullType(String),
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
        case r'auth_note':
          final valueDes = serializers.deserialize(
            value,
            specifiedType: const FullType(String),
          ) as String;
          result.authNote = valueDes;
          break;
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
        case r'host_available':
          final valueDes = serializers.deserialize(
            value,
            specifiedType: const FullType.nullable(bool),
          ) as bool?;
          if (valueDes == null) continue;
          result.hostAvailable = valueDes;
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
            specifiedType: const FullType.nullable(String),
          ) as String?;
          if (valueDes == null) continue;
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
        case r'model_variable':
          final valueDes = serializers.deserialize(
            value,
            specifiedType: const FullType(String),
          ) as String;
          result.modelVariable = valueDes;
          break;
        case r'text_settings':
          final valueDes = serializers.deserialize(
            value,
            specifiedType:
                const FullType(BuiltList, [FullType(TextSettingModel)]),
          ) as BuiltList<TextSettingModel>;
          result.textSettings.replace(valueDes);
          break;
        case r'transport':
          final valueDes = serializers.deserialize(
            value,
            specifiedType: const FullType(String),
          ) as String;
          result.transport = valueDes;
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
