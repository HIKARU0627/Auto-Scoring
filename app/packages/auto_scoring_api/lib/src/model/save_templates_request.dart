//
// AUTO-GENERATED FILE, DO NOT MODIFY!
//

// ignore_for_file: unused_element
import 'package:built_collection/built_collection.dart';
import 'package:auto_scoring_api/src/model/intake_template_model.dart';
import 'package:built_value/built_value.dart';
import 'package:built_value/serializer.dart';

part 'save_templates_request.g.dart';

/// SaveTemplatesRequest
///
/// Properties:
/// * [templates]
@BuiltValue()
abstract class SaveTemplatesRequest
    implements Built<SaveTemplatesRequest, SaveTemplatesRequestBuilder> {
  @BuiltValueField(wireName: r'templates')
  BuiltList<IntakeTemplateModel> get templates;

  SaveTemplatesRequest._();

  factory SaveTemplatesRequest([void updates(SaveTemplatesRequestBuilder b)]) =
      _$SaveTemplatesRequest;

  @BuiltValueHook(initializeBuilder: true)
  static void _defaults(SaveTemplatesRequestBuilder b) => b;

  @BuiltValueSerializer(custom: true)
  static Serializer<SaveTemplatesRequest> get serializer =>
      _$SaveTemplatesRequestSerializer();
}

class _$SaveTemplatesRequestSerializer
    implements PrimitiveSerializer<SaveTemplatesRequest> {
  @override
  final Iterable<Type> types = const [
    SaveTemplatesRequest,
    _$SaveTemplatesRequest
  ];

  @override
  final String wireName = r'SaveTemplatesRequest';

  Iterable<Object?> _serializeProperties(
    Serializers serializers,
    SaveTemplatesRequest object, {
    FullType specifiedType = FullType.unspecified,
  }) sync* {
    yield r'templates';
    yield serializers.serialize(
      object.templates,
      specifiedType: const FullType(BuiltList, [FullType(IntakeTemplateModel)]),
    );
  }

  @override
  Object serialize(
    Serializers serializers,
    SaveTemplatesRequest object, {
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
    required SaveTemplatesRequestBuilder result,
    required List<Object?> unhandled,
  }) {
    for (var i = 0; i < serializedList.length; i += 2) {
      final key = serializedList[i] as String;
      final value = serializedList[i + 1];
      switch (key) {
        case r'templates':
          final valueDes = serializers.deserialize(
            value,
            specifiedType:
                const FullType(BuiltList, [FullType(IntakeTemplateModel)]),
          ) as BuiltList<IntakeTemplateModel>;
          result.templates.replace(valueDes);
          break;
        default:
          unhandled.add(key);
          unhandled.add(value);
          break;
      }
    }
  }

  @override
  SaveTemplatesRequest deserialize(
    Serializers serializers,
    Object serialized, {
    FullType specifiedType = FullType.unspecified,
  }) {
    final result = SaveTemplatesRequestBuilder();
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
