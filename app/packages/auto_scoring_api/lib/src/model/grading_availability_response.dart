//
// AUTO-GENERATED FILE, DO NOT MODIFY!
//

// ignore_for_file: unused_element
import 'package:built_value/built_value.dart';
import 'package:built_value/serializer.dart';

part 'grading_availability_response.g.dart';

/// Whether this sidecar can AI-grade at all, and if not, why (Issue #97).  The app asks once per connection and keeps a banner above every screen while ``available`` is false. That banner is the whole point: without it, a host with no credentials still imports answers, still enqueues grading jobs, and the reviewer only ever sees each question fail -- with no way to tell \"this machine cannot grade\" apart from \"the AI could not read this answer\".  ``reason`` never contains a credential: it is `UnconfiguredAIProvider. reason`, which names configuration variables and host prerequisites only (see `build_ai_provider`).
///
/// Properties:
/// * [available]
/// * [reason]
@BuiltValue()
abstract class GradingAvailabilityResponse
    implements
        Built<GradingAvailabilityResponse, GradingAvailabilityResponseBuilder> {
  @BuiltValueField(wireName: r'available')
  bool get available;

  @BuiltValueField(wireName: r'reason')
  String? get reason;

  GradingAvailabilityResponse._();

  factory GradingAvailabilityResponse(
          [void updates(GradingAvailabilityResponseBuilder b)]) =
      _$GradingAvailabilityResponse;

  @BuiltValueHook(initializeBuilder: true)
  static void _defaults(GradingAvailabilityResponseBuilder b) => b;

  @BuiltValueSerializer(custom: true)
  static Serializer<GradingAvailabilityResponse> get serializer =>
      _$GradingAvailabilityResponseSerializer();
}

class _$GradingAvailabilityResponseSerializer
    implements PrimitiveSerializer<GradingAvailabilityResponse> {
  @override
  final Iterable<Type> types = const [
    GradingAvailabilityResponse,
    _$GradingAvailabilityResponse
  ];

  @override
  final String wireName = r'GradingAvailabilityResponse';

  Iterable<Object?> _serializeProperties(
    Serializers serializers,
    GradingAvailabilityResponse object, {
    FullType specifiedType = FullType.unspecified,
  }) sync* {
    yield r'available';
    yield serializers.serialize(
      object.available,
      specifiedType: const FullType(bool),
    );
    if (object.reason != null) {
      yield r'reason';
      yield serializers.serialize(
        object.reason,
        specifiedType: const FullType.nullable(String),
      );
    }
  }

  @override
  Object serialize(
    Serializers serializers,
    GradingAvailabilityResponse object, {
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
    required GradingAvailabilityResponseBuilder result,
    required List<Object?> unhandled,
  }) {
    for (var i = 0; i < serializedList.length; i += 2) {
      final key = serializedList[i] as String;
      final value = serializedList[i + 1];
      switch (key) {
        case r'available':
          final valueDes = serializers.deserialize(
            value,
            specifiedType: const FullType(bool),
          ) as bool;
          result.available = valueDes;
          break;
        case r'reason':
          final valueDes = serializers.deserialize(
            value,
            specifiedType: const FullType.nullable(String),
          ) as String?;
          if (valueDes == null) continue;
          result.reason = valueDes;
          break;
        default:
          unhandled.add(key);
          unhandled.add(value);
          break;
      }
    }
  }

  @override
  GradingAvailabilityResponse deserialize(
    Serializers serializers,
    Object serialized, {
    FullType specifiedType = FullType.unspecified,
  }) {
    final result = GradingAvailabilityResponseBuilder();
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
