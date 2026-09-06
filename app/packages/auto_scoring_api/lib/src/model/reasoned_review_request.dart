//
// AUTO-GENERATED FILE, DO NOT MODIFY!
//

// ignore_for_file: unused_element
import 'package:built_value/built_value.dart';
import 'package:built_value/serializer.dart';

part 'reasoned_review_request.g.dart';

/// ReasonedReviewRequest
///
/// Properties:
/// * [expectedVersion]
/// * [reason]
@BuiltValue()
abstract class ReasonedReviewRequest
    implements Built<ReasonedReviewRequest, ReasonedReviewRequestBuilder> {
  @BuiltValueField(wireName: r'expected_version')
  int get expectedVersion;

  @BuiltValueField(wireName: r'reason')
  String? get reason;

  ReasonedReviewRequest._();

  factory ReasonedReviewRequest(
      [void updates(ReasonedReviewRequestBuilder b)]) = _$ReasonedReviewRequest;

  @BuiltValueHook(initializeBuilder: true)
  static void _defaults(ReasonedReviewRequestBuilder b) => b;

  @BuiltValueSerializer(custom: true)
  static Serializer<ReasonedReviewRequest> get serializer =>
      _$ReasonedReviewRequestSerializer();
}

class _$ReasonedReviewRequestSerializer
    implements PrimitiveSerializer<ReasonedReviewRequest> {
  @override
  final Iterable<Type> types = const [
    ReasonedReviewRequest,
    _$ReasonedReviewRequest
  ];

  @override
  final String wireName = r'ReasonedReviewRequest';

  Iterable<Object?> _serializeProperties(
    Serializers serializers,
    ReasonedReviewRequest object, {
    FullType specifiedType = FullType.unspecified,
  }) sync* {
    yield r'expected_version';
    yield serializers.serialize(
      object.expectedVersion,
      specifiedType: const FullType(int),
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
    ReasonedReviewRequest object, {
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
    required ReasonedReviewRequestBuilder result,
    required List<Object?> unhandled,
  }) {
    for (var i = 0; i < serializedList.length; i += 2) {
      final key = serializedList[i] as String;
      final value = serializedList[i + 1];
      switch (key) {
        case r'expected_version':
          final valueDes = serializers.deserialize(
            value,
            specifiedType: const FullType(int),
          ) as int;
          result.expectedVersion = valueDes;
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
  ReasonedReviewRequest deserialize(
    Serializers serializers,
    Object serialized, {
    FullType specifiedType = FullType.unspecified,
  }) {
    final result = ReasonedReviewRequestBuilder();
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
