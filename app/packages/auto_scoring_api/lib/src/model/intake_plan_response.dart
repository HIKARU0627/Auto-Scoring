//
// AUTO-GENERATED FILE, DO NOT MODIFY!
//

// ignore_for_file: unused_element
import 'package:built_collection/built_collection.dart';
import 'package:auto_scoring_api/src/model/planned_group_model.dart';
import 'package:auto_scoring_api/src/model/classification_estimate_model.dart';
import 'package:built_value/built_value.dart';
import 'package:built_value/serializer.dart';

part 'intake_plan_response.g.dart';

/// IntakePlanResponse
///
/// Properties:
/// * [estimate]
/// * [groups]
@BuiltValue()
abstract class IntakePlanResponse
    implements Built<IntakePlanResponse, IntakePlanResponseBuilder> {
  @BuiltValueField(wireName: r'estimate')
  ClassificationEstimateModel get estimate;

  @BuiltValueField(wireName: r'groups')
  BuiltList<PlannedGroupModel> get groups;

  IntakePlanResponse._();

  factory IntakePlanResponse([void updates(IntakePlanResponseBuilder b)]) =
      _$IntakePlanResponse;

  @BuiltValueHook(initializeBuilder: true)
  static void _defaults(IntakePlanResponseBuilder b) => b;

  @BuiltValueSerializer(custom: true)
  static Serializer<IntakePlanResponse> get serializer =>
      _$IntakePlanResponseSerializer();
}

class _$IntakePlanResponseSerializer
    implements PrimitiveSerializer<IntakePlanResponse> {
  @override
  final Iterable<Type> types = const [IntakePlanResponse, _$IntakePlanResponse];

  @override
  final String wireName = r'IntakePlanResponse';

  Iterable<Object?> _serializeProperties(
    Serializers serializers,
    IntakePlanResponse object, {
    FullType specifiedType = FullType.unspecified,
  }) sync* {
    yield r'estimate';
    yield serializers.serialize(
      object.estimate,
      specifiedType: const FullType(ClassificationEstimateModel),
    );
    yield r'groups';
    yield serializers.serialize(
      object.groups,
      specifiedType: const FullType(BuiltList, [FullType(PlannedGroupModel)]),
    );
  }

  @override
  Object serialize(
    Serializers serializers,
    IntakePlanResponse object, {
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
    required IntakePlanResponseBuilder result,
    required List<Object?> unhandled,
  }) {
    for (var i = 0; i < serializedList.length; i += 2) {
      final key = serializedList[i] as String;
      final value = serializedList[i + 1];
      switch (key) {
        case r'estimate':
          final valueDes = serializers.deserialize(
            value,
            specifiedType: const FullType(ClassificationEstimateModel),
          ) as ClassificationEstimateModel;
          result.estimate.replace(valueDes);
          break;
        case r'groups':
          final valueDes = serializers.deserialize(
            value,
            specifiedType:
                const FullType(BuiltList, [FullType(PlannedGroupModel)]),
          ) as BuiltList<PlannedGroupModel>;
          result.groups.replace(valueDes);
          break;
        default:
          unhandled.add(key);
          unhandled.add(value);
          break;
      }
    }
  }

  @override
  IntakePlanResponse deserialize(
    Serializers serializers,
    Object serialized, {
    FullType specifiedType = FullType.unspecified,
  }) {
    final result = IntakePlanResponseBuilder();
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
