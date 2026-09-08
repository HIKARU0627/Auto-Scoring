//
// AUTO-GENERATED FILE, DO NOT MODIFY!
//

// ignore_for_file: unused_element
import 'package:built_collection/built_collection.dart';
import 'package:auto_scoring_api/src/model/intake_rule_model.dart';
import 'package:built_value/built_value.dart';
import 'package:built_value/serializer.dart';

part 'intake_template_model.g.dart';

/// IntakeTemplateModel
///
/// Properties:
/// * [id]
/// * [name]
/// * [rules]
/// * [splitChildDirectories]
@BuiltValue()
abstract class IntakeTemplateModel
    implements Built<IntakeTemplateModel, IntakeTemplateModelBuilder> {
  @BuiltValueField(wireName: r'id')
  String get id;

  @BuiltValueField(wireName: r'name')
  String get name;

  @BuiltValueField(wireName: r'rules')
  BuiltList<IntakeRuleModel> get rules;

  @BuiltValueField(wireName: r'split_child_directories')
  bool? get splitChildDirectories;

  IntakeTemplateModel._();

  factory IntakeTemplateModel([void updates(IntakeTemplateModelBuilder b)]) =
      _$IntakeTemplateModel;

  @BuiltValueHook(initializeBuilder: true)
  static void _defaults(IntakeTemplateModelBuilder b) =>
      b..splitChildDirectories = true;

  @BuiltValueSerializer(custom: true)
  static Serializer<IntakeTemplateModel> get serializer =>
      _$IntakeTemplateModelSerializer();
}

class _$IntakeTemplateModelSerializer
    implements PrimitiveSerializer<IntakeTemplateModel> {
  @override
  final Iterable<Type> types = const [
    IntakeTemplateModel,
    _$IntakeTemplateModel
  ];

  @override
  final String wireName = r'IntakeTemplateModel';

  Iterable<Object?> _serializeProperties(
    Serializers serializers,
    IntakeTemplateModel object, {
    FullType specifiedType = FullType.unspecified,
  }) sync* {
    yield r'id';
    yield serializers.serialize(
      object.id,
      specifiedType: const FullType(String),
    );
    yield r'name';
    yield serializers.serialize(
      object.name,
      specifiedType: const FullType(String),
    );
    yield r'rules';
    yield serializers.serialize(
      object.rules,
      specifiedType: const FullType(BuiltList, [FullType(IntakeRuleModel)]),
    );
    if (object.splitChildDirectories != null) {
      yield r'split_child_directories';
      yield serializers.serialize(
        object.splitChildDirectories,
        specifiedType: const FullType(bool),
      );
    }
  }

  @override
  Object serialize(
    Serializers serializers,
    IntakeTemplateModel object, {
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
    required IntakeTemplateModelBuilder result,
    required List<Object?> unhandled,
  }) {
    for (var i = 0; i < serializedList.length; i += 2) {
      final key = serializedList[i] as String;
      final value = serializedList[i + 1];
      switch (key) {
        case r'id':
          final valueDes = serializers.deserialize(
            value,
            specifiedType: const FullType(String),
          ) as String;
          result.id = valueDes;
          break;
        case r'name':
          final valueDes = serializers.deserialize(
            value,
            specifiedType: const FullType(String),
          ) as String;
          result.name = valueDes;
          break;
        case r'rules':
          final valueDes = serializers.deserialize(
            value,
            specifiedType:
                const FullType(BuiltList, [FullType(IntakeRuleModel)]),
          ) as BuiltList<IntakeRuleModel>;
          result.rules.replace(valueDes);
          break;
        case r'split_child_directories':
          final valueDes = serializers.deserialize(
            value,
            specifiedType: const FullType.nullable(bool),
          ) as bool?;
          if (valueDes == null) continue;
          result.splitChildDirectories = valueDes;
          break;
        default:
          unhandled.add(key);
          unhandled.add(value);
          break;
      }
    }
  }

  @override
  IntakeTemplateModel deserialize(
    Serializers serializers,
    Object serialized, {
    FullType specifiedType = FullType.unspecified,
  }) {
    final result = IntakeTemplateModelBuilder();
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
