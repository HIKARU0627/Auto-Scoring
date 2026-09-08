//
// AUTO-GENERATED FILE, DO NOT MODIFY!
//

// ignore_for_file: unused_element
import 'package:built_value/built_value.dart';
import 'package:built_value/serializer.dart';

part 'attribution_proposal_response.g.dart';

/// ``test_id`` is ``null`` for \"could not tell\".  Expect that often. The observed answer sheets carry a course-name field that is printed on some, blank on others and handwritten on the rest, and every sheet inspected had blank student name/id fields -- so a first page frequently identifies nothing at all.
///
/// Properties:
/// * [confidence]
/// * [testId]
@BuiltValue()
abstract class AttributionProposalResponse
    implements
        Built<AttributionProposalResponse, AttributionProposalResponseBuilder> {
  @BuiltValueField(wireName: r'confidence')
  num get confidence;

  @BuiltValueField(wireName: r'test_id')
  String? get testId;

  AttributionProposalResponse._();

  factory AttributionProposalResponse(
          [void updates(AttributionProposalResponseBuilder b)]) =
      _$AttributionProposalResponse;

  @BuiltValueHook(initializeBuilder: true)
  static void _defaults(AttributionProposalResponseBuilder b) => b;

  @BuiltValueSerializer(custom: true)
  static Serializer<AttributionProposalResponse> get serializer =>
      _$AttributionProposalResponseSerializer();
}

class _$AttributionProposalResponseSerializer
    implements PrimitiveSerializer<AttributionProposalResponse> {
  @override
  final Iterable<Type> types = const [
    AttributionProposalResponse,
    _$AttributionProposalResponse
  ];

  @override
  final String wireName = r'AttributionProposalResponse';

  Iterable<Object?> _serializeProperties(
    Serializers serializers,
    AttributionProposalResponse object, {
    FullType specifiedType = FullType.unspecified,
  }) sync* {
    yield r'confidence';
    yield serializers.serialize(
      object.confidence,
      specifiedType: const FullType(num),
    );
    yield r'test_id';
    yield object.testId == null
        ? null
        : serializers.serialize(
            object.testId,
            specifiedType: const FullType.nullable(String),
          );
  }

  @override
  Object serialize(
    Serializers serializers,
    AttributionProposalResponse object, {
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
    required AttributionProposalResponseBuilder result,
    required List<Object?> unhandled,
  }) {
    for (var i = 0; i < serializedList.length; i += 2) {
      final key = serializedList[i] as String;
      final value = serializedList[i + 1];
      switch (key) {
        case r'confidence':
          final valueDes = serializers.deserialize(
            value,
            specifiedType: const FullType(num),
          ) as num;
          result.confidence = valueDes;
          break;
        case r'test_id':
          final valueDes = serializers.deserialize(
            value,
            specifiedType: const FullType.nullable(String),
          ) as String?;
          if (valueDes == null) continue;
          result.testId = valueDes;
          break;
        default:
          unhandled.add(key);
          unhandled.add(value);
          break;
      }
    }
  }

  @override
  AttributionProposalResponse deserialize(
    Serializers serializers,
    Object serialized, {
    FullType specifiedType = FullType.unspecified,
  }) {
    final result = AttributionProposalResponseBuilder();
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
