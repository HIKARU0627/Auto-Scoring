//
// AUTO-GENERATED FILE, DO NOT MODIFY!
//

// ignore_for_file: unused_element
import 'package:built_value/built_value.dart';
import 'package:built_value/serializer.dart';

part 'criterion_outcome_request.g.dart';

/// CriterionOutcomeRequest
///
/// Properties:
/// * [confidence]
/// * [criterionId]
/// * [outcome]
@BuiltValue()
abstract class CriterionOutcomeRequest
    implements Built<CriterionOutcomeRequest, CriterionOutcomeRequestBuilder> {
  @BuiltValueField(wireName: r'confidence')
  num? get confidence;

  @BuiltValueField(wireName: r'criterion_id')
  String get criterionId;

  @BuiltValueField(wireName: r'outcome')
  String get outcome;

  CriterionOutcomeRequest._();

  factory CriterionOutcomeRequest(
          [void updates(CriterionOutcomeRequestBuilder b)]) =
      _$CriterionOutcomeRequest;

  @BuiltValueHook(initializeBuilder: true)
  static void _defaults(CriterionOutcomeRequestBuilder b) => b;

  @BuiltValueSerializer(custom: true)
  static Serializer<CriterionOutcomeRequest> get serializer =>
      _$CriterionOutcomeRequestSerializer();
}

class _$CriterionOutcomeRequestSerializer
    implements PrimitiveSerializer<CriterionOutcomeRequest> {
  @override
  final Iterable<Type> types = const [
    CriterionOutcomeRequest,
    _$CriterionOutcomeRequest
  ];

  @override
  final String wireName = r'CriterionOutcomeRequest';

  Iterable<Object?> _serializeProperties(
    Serializers serializers,
    CriterionOutcomeRequest object, {
    FullType specifiedType = FullType.unspecified,
  }) sync* {
    if (object.confidence != null) {
      yield r'confidence';
      yield serializers.serialize(
        object.confidence,
        specifiedType: const FullType.nullable(num),
      );
    }
    yield r'criterion_id';
    yield serializers.serialize(
      object.criterionId,
      specifiedType: const FullType(String),
    );
    yield r'outcome';
    yield serializers.serialize(
      object.outcome,
      specifiedType: const FullType(String),
    );
  }

  @override
  Object serialize(
    Serializers serializers,
    CriterionOutcomeRequest object, {
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
    required CriterionOutcomeRequestBuilder result,
    required List<Object?> unhandled,
  }) {
    for (var i = 0; i < serializedList.length; i += 2) {
      final key = serializedList[i] as String;
      final value = serializedList[i + 1];
      switch (key) {
        case r'confidence':
          final valueDes = serializers.deserialize(
            value,
            specifiedType: const FullType.nullable(num),
          ) as num?;
          if (valueDes == null) continue;
          result.confidence = valueDes;
          break;
        case r'criterion_id':
          final valueDes = serializers.deserialize(
            value,
            specifiedType: const FullType(String),
          ) as String;
          result.criterionId = valueDes;
          break;
        case r'outcome':
          final valueDes = serializers.deserialize(
            value,
            specifiedType: const FullType(String),
          ) as String;
          result.outcome = valueDes;
          break;
        default:
          unhandled.add(key);
          unhandled.add(value);
          break;
      }
    }
  }

  @override
  CriterionOutcomeRequest deserialize(
    Serializers serializers,
    Object serialized, {
    FullType specifiedType = FullType.unspecified,
  }) {
    final result = CriterionOutcomeRequestBuilder();
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
