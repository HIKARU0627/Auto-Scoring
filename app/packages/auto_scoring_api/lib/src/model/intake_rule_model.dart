//
// AUTO-GENERATED FILE, DO NOT MODIFY!
//

// ignore_for_file: unused_element
import 'package:auto_scoring_api/src/model/material_role.dart';
import 'package:auto_scoring_api/src/model/requirement.dart';
import 'package:auto_scoring_api/src/model/rule_scope.dart';
import 'package:built_value/built_value.dart';
import 'package:built_value/serializer.dart';

part 'intake_rule_model.g.dart';

/// IntakeRuleModel
///
/// Properties:
/// * [pattern]
/// * [requirement]
/// * [role]
/// * [scope]
@BuiltValue()
abstract class IntakeRuleModel
    implements Built<IntakeRuleModel, IntakeRuleModelBuilder> {
  @BuiltValueField(wireName: r'pattern')
  String get pattern;

  @BuiltValueField(wireName: r'requirement')
  Requirement? get requirement;
  // enum requirementEnum {  required,  recommended,  optional,  };

  @BuiltValueField(wireName: r'role')
  MaterialRole get role;
  // enum roleEnum {  student_answer,  grading_criteria,  annotation_resource,  annotation_sample,  reference,  ignore,  };

  @BuiltValueField(wireName: r'scope')
  RuleScope get scope;
  // enum scopeEnum {  file,  folder,  };

  IntakeRuleModel._();

  factory IntakeRuleModel([void updates(IntakeRuleModelBuilder b)]) =
      _$IntakeRuleModel;

  @BuiltValueHook(initializeBuilder: true)
  static void _defaults(IntakeRuleModelBuilder b) =>
      b..requirement = Requirement.optional;

  @BuiltValueSerializer(custom: true)
  static Serializer<IntakeRuleModel> get serializer =>
      _$IntakeRuleModelSerializer();
}

class _$IntakeRuleModelSerializer
    implements PrimitiveSerializer<IntakeRuleModel> {
  @override
  final Iterable<Type> types = const [IntakeRuleModel, _$IntakeRuleModel];

  @override
  final String wireName = r'IntakeRuleModel';

  Iterable<Object?> _serializeProperties(
    Serializers serializers,
    IntakeRuleModel object, {
    FullType specifiedType = FullType.unspecified,
  }) sync* {
    yield r'pattern';
    yield serializers.serialize(
      object.pattern,
      specifiedType: const FullType(String),
    );
    if (object.requirement != null) {
      yield r'requirement';
      yield serializers.serialize(
        object.requirement,
        specifiedType: const FullType(Requirement),
      );
    }
    yield r'role';
    yield serializers.serialize(
      object.role,
      specifiedType: const FullType(MaterialRole),
    );
    yield r'scope';
    yield serializers.serialize(
      object.scope,
      specifiedType: const FullType(RuleScope),
    );
  }

  @override
  Object serialize(
    Serializers serializers,
    IntakeRuleModel object, {
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
    required IntakeRuleModelBuilder result,
    required List<Object?> unhandled,
  }) {
    for (var i = 0; i < serializedList.length; i += 2) {
      final key = serializedList[i] as String;
      final value = serializedList[i + 1];
      switch (key) {
        case r'pattern':
          final valueDes = serializers.deserialize(
            value,
            specifiedType: const FullType(String),
          ) as String;
          result.pattern = valueDes;
          break;
        case r'requirement':
          final valueDes = serializers.deserialize(
            value,
            specifiedType: const FullType.nullable(Requirement),
          ) as Requirement?;
          if (valueDes == null) continue;
          result.requirement = valueDes;
          break;
        case r'role':
          final valueDes = serializers.deserialize(
            value,
            specifiedType: const FullType(MaterialRole),
          ) as MaterialRole;
          result.role = valueDes;
          break;
        case r'scope':
          final valueDes = serializers.deserialize(
            value,
            specifiedType: const FullType(RuleScope),
          ) as RuleScope;
          result.scope = valueDes;
          break;
        default:
          unhandled.add(key);
          unhandled.add(value);
          break;
      }
    }
  }

  @override
  IntakeRuleModel deserialize(
    Serializers serializers,
    Object serialized, {
    FullType specifiedType = FullType.unspecified,
  }) {
    final result = IntakeRuleModelBuilder();
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
