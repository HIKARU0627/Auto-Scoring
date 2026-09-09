//
// AUTO-GENERATED FILE, DO NOT MODIFY!
//

// ignore_for_file: unused_element
import 'package:built_value/built_value.dart';
import 'package:built_value/serializer.dart';

part 'ocr_availability_response.g.dart';

/// Whether this sidecar can OCR at all, and if not, why (Issue #114).  The counterpart of `GradingAvailabilityResponse`, and it exists for the same reason: without it, \"usable=False\" on a question is the same shape whether the OCR read the answer and was unsure or this machine has no OCR at all -- and those are different facts that call for different actions (Issue #114 acceptance 8).  Unlike grading, ``available=False`` here does not stop anything: design section 24 has grading carry on without a reading. What is lost is stated in section 8.1.5 -- the cross-check against the grading AI's own reading, and text-anchored annotation positions -- so this is an \"OCR is off, verification is weaker\" notice, never a blocker.  ``reason`` never contains a credential: it is `UnconfiguredOCRProvider.reason`, which names configuration variables and host prerequisites only (see `build_ocr_provider`).
///
/// Properties:
/// * [available]
/// * [reason]
@BuiltValue()
abstract class OcrAvailabilityResponse
    implements Built<OcrAvailabilityResponse, OcrAvailabilityResponseBuilder> {
  @BuiltValueField(wireName: r'available')
  bool get available;

  @BuiltValueField(wireName: r'reason')
  String? get reason;

  OcrAvailabilityResponse._();

  factory OcrAvailabilityResponse(
          [void updates(OcrAvailabilityResponseBuilder b)]) =
      _$OcrAvailabilityResponse;

  @BuiltValueHook(initializeBuilder: true)
  static void _defaults(OcrAvailabilityResponseBuilder b) => b;

  @BuiltValueSerializer(custom: true)
  static Serializer<OcrAvailabilityResponse> get serializer =>
      _$OcrAvailabilityResponseSerializer();
}

class _$OcrAvailabilityResponseSerializer
    implements PrimitiveSerializer<OcrAvailabilityResponse> {
  @override
  final Iterable<Type> types = const [
    OcrAvailabilityResponse,
    _$OcrAvailabilityResponse
  ];

  @override
  final String wireName = r'OcrAvailabilityResponse';

  Iterable<Object?> _serializeProperties(
    Serializers serializers,
    OcrAvailabilityResponse object, {
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
    OcrAvailabilityResponse object, {
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
    required OcrAvailabilityResponseBuilder result,
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
  OcrAvailabilityResponse deserialize(
    Serializers serializers,
    Object serialized, {
    FullType specifiedType = FullType.unspecified,
  }) {
    final result = OcrAvailabilityResponseBuilder();
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
