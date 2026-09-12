//
// AUTO-GENERATED FILE, DO NOT MODIFY!
//

// ignore_for_file: unused_element
import 'package:auto_scoring_api/src/model/configuration_source.dart';
import 'package:built_value/built_value.dart';
import 'package:built_value/serializer.dart';

part 'text_setting_model.g.dart';

/// One readable (non-secret) setting: its effective value and source.
///
/// Properties:
/// * [defaultValue]
/// * [helpText]
/// * [label]
/// * [placeholder]
/// * [source_]
/// * [value]
/// * [variable]
@BuiltValue()
abstract class TextSettingModel
    implements Built<TextSettingModel, TextSettingModelBuilder> {
  @BuiltValueField(wireName: r'default_value')
  String get defaultValue;

  @BuiltValueField(wireName: r'help_text')
  String get helpText;

  @BuiltValueField(wireName: r'label')
  String get label;

  @BuiltValueField(wireName: r'placeholder')
  String get placeholder;

  @BuiltValueField(wireName: r'source')
  ConfigurationSource get source_;
  // enum source_Enum {  credential_store,  environment,  builtin_default,  none,  };

  @BuiltValueField(wireName: r'value')
  String get value;

  @BuiltValueField(wireName: r'variable')
  String get variable;

  TextSettingModel._();

  factory TextSettingModel([void updates(TextSettingModelBuilder b)]) =
      _$TextSettingModel;

  @BuiltValueHook(initializeBuilder: true)
  static void _defaults(TextSettingModelBuilder b) => b;

  @BuiltValueSerializer(custom: true)
  static Serializer<TextSettingModel> get serializer =>
      _$TextSettingModelSerializer();
}

class _$TextSettingModelSerializer
    implements PrimitiveSerializer<TextSettingModel> {
  @override
  final Iterable<Type> types = const [TextSettingModel, _$TextSettingModel];

  @override
  final String wireName = r'TextSettingModel';

  Iterable<Object?> _serializeProperties(
    Serializers serializers,
    TextSettingModel object, {
    FullType specifiedType = FullType.unspecified,
  }) sync* {
    yield r'default_value';
    yield serializers.serialize(
      object.defaultValue,
      specifiedType: const FullType(String),
    );
    yield r'help_text';
    yield serializers.serialize(
      object.helpText,
      specifiedType: const FullType(String),
    );
    yield r'label';
    yield serializers.serialize(
      object.label,
      specifiedType: const FullType(String),
    );
    yield r'placeholder';
    yield serializers.serialize(
      object.placeholder,
      specifiedType: const FullType(String),
    );
    yield r'source';
    yield serializers.serialize(
      object.source_,
      specifiedType: const FullType(ConfigurationSource),
    );
    yield r'value';
    yield serializers.serialize(
      object.value,
      specifiedType: const FullType(String),
    );
    yield r'variable';
    yield serializers.serialize(
      object.variable,
      specifiedType: const FullType(String),
    );
  }

  @override
  Object serialize(
    Serializers serializers,
    TextSettingModel object, {
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
    required TextSettingModelBuilder result,
    required List<Object?> unhandled,
  }) {
    for (var i = 0; i < serializedList.length; i += 2) {
      final key = serializedList[i] as String;
      final value = serializedList[i + 1];
      switch (key) {
        case r'default_value':
          final valueDes = serializers.deserialize(
            value,
            specifiedType: const FullType(String),
          ) as String;
          result.defaultValue = valueDes;
          break;
        case r'help_text':
          final valueDes = serializers.deserialize(
            value,
            specifiedType: const FullType(String),
          ) as String;
          result.helpText = valueDes;
          break;
        case r'label':
          final valueDes = serializers.deserialize(
            value,
            specifiedType: const FullType(String),
          ) as String;
          result.label = valueDes;
          break;
        case r'placeholder':
          final valueDes = serializers.deserialize(
            value,
            specifiedType: const FullType(String),
          ) as String;
          result.placeholder = valueDes;
          break;
        case r'source':
          final valueDes = serializers.deserialize(
            value,
            specifiedType: const FullType(ConfigurationSource),
          ) as ConfigurationSource;
          result.source_ = valueDes;
          break;
        case r'value':
          final valueDes = serializers.deserialize(
            value,
            specifiedType: const FullType(String),
          ) as String;
          result.value = valueDes;
          break;
        case r'variable':
          final valueDes = serializers.deserialize(
            value,
            specifiedType: const FullType(String),
          ) as String;
          result.variable = valueDes;
          break;
        default:
          unhandled.add(key);
          unhandled.add(value);
          break;
      }
    }
  }

  @override
  TextSettingModel deserialize(
    Serializers serializers,
    Object serialized, {
    FullType specifiedType = FullType.unspecified,
  }) {
    final result = TextSettingModelBuilder();
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
