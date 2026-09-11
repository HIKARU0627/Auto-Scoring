//
// AUTO-GENERATED FILE, DO NOT MODIFY!
//

// ignore_for_file: unused_element
import 'package:auto_scoring_api/src/model/usage_availability.dart';
import 'package:built_value/built_value.dart';
import 'package:built_value/serializer.dart';

part 'submission_ai_usage_response.g.dart';

/// SubmissionAiUsageResponse
///
/// Properties:
/// * [estimatedCost]
/// * [inputTokens]
/// * [outputTokens]
/// * [tokenUnitCost]
/// * [usageAvailability]
@BuiltValue()
abstract class SubmissionAiUsageResponse
    implements
        Built<SubmissionAiUsageResponse, SubmissionAiUsageResponseBuilder> {
  @BuiltValueField(wireName: r'estimated_cost')
  num? get estimatedCost;

  @BuiltValueField(wireName: r'input_tokens')
  int? get inputTokens;

  @BuiltValueField(wireName: r'output_tokens')
  int? get outputTokens;

  @BuiltValueField(wireName: r'token_unit_cost')
  num? get tokenUnitCost;

  @BuiltValueField(wireName: r'usage_availability')
  UsageAvailability get usageAvailability;
  // enum usageAvailabilityEnum {  known,  partial,  unknown,  };

  SubmissionAiUsageResponse._();

  factory SubmissionAiUsageResponse(
          [void updates(SubmissionAiUsageResponseBuilder b)]) =
      _$SubmissionAiUsageResponse;

  @BuiltValueHook(initializeBuilder: true)
  static void _defaults(SubmissionAiUsageResponseBuilder b) => b;

  @BuiltValueSerializer(custom: true)
  static Serializer<SubmissionAiUsageResponse> get serializer =>
      _$SubmissionAiUsageResponseSerializer();
}

class _$SubmissionAiUsageResponseSerializer
    implements PrimitiveSerializer<SubmissionAiUsageResponse> {
  @override
  final Iterable<Type> types = const [
    SubmissionAiUsageResponse,
    _$SubmissionAiUsageResponse
  ];

  @override
  final String wireName = r'SubmissionAiUsageResponse';

  Iterable<Object?> _serializeProperties(
    Serializers serializers,
    SubmissionAiUsageResponse object, {
    FullType specifiedType = FullType.unspecified,
  }) sync* {
    if (object.estimatedCost != null) {
      yield r'estimated_cost';
      yield serializers.serialize(
        object.estimatedCost,
        specifiedType: const FullType.nullable(num),
      );
    }
    if (object.inputTokens != null) {
      yield r'input_tokens';
      yield serializers.serialize(
        object.inputTokens,
        specifiedType: const FullType.nullable(int),
      );
    }
    if (object.outputTokens != null) {
      yield r'output_tokens';
      yield serializers.serialize(
        object.outputTokens,
        specifiedType: const FullType.nullable(int),
      );
    }
    if (object.tokenUnitCost != null) {
      yield r'token_unit_cost';
      yield serializers.serialize(
        object.tokenUnitCost,
        specifiedType: const FullType.nullable(num),
      );
    }
    yield r'usage_availability';
    yield serializers.serialize(
      object.usageAvailability,
      specifiedType: const FullType(UsageAvailability),
    );
  }

  @override
  Object serialize(
    Serializers serializers,
    SubmissionAiUsageResponse object, {
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
    required SubmissionAiUsageResponseBuilder result,
    required List<Object?> unhandled,
  }) {
    for (var i = 0; i < serializedList.length; i += 2) {
      final key = serializedList[i] as String;
      final value = serializedList[i + 1];
      switch (key) {
        case r'estimated_cost':
          final valueDes = serializers.deserialize(
            value,
            specifiedType: const FullType.nullable(num),
          ) as num?;
          if (valueDes == null) continue;
          result.estimatedCost = valueDes;
          break;
        case r'input_tokens':
          final valueDes = serializers.deserialize(
            value,
            specifiedType: const FullType.nullable(int),
          ) as int?;
          if (valueDes == null) continue;
          result.inputTokens = valueDes;
          break;
        case r'output_tokens':
          final valueDes = serializers.deserialize(
            value,
            specifiedType: const FullType.nullable(int),
          ) as int?;
          if (valueDes == null) continue;
          result.outputTokens = valueDes;
          break;
        case r'token_unit_cost':
          final valueDes = serializers.deserialize(
            value,
            specifiedType: const FullType.nullable(num),
          ) as num?;
          if (valueDes == null) continue;
          result.tokenUnitCost = valueDes;
          break;
        case r'usage_availability':
          final valueDes = serializers.deserialize(
            value,
            specifiedType: const FullType(UsageAvailability),
          ) as UsageAvailability;
          result.usageAvailability = valueDes;
          break;
        default:
          unhandled.add(key);
          unhandled.add(value);
          break;
      }
    }
  }

  @override
  SubmissionAiUsageResponse deserialize(
    Serializers serializers,
    Object serialized, {
    FullType specifiedType = FullType.unspecified,
  }) {
    final result = SubmissionAiUsageResponseBuilder();
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
