//
// AUTO-GENERATED FILE, DO NOT MODIFY!
//

// ignore_for_file: unused_element
import 'package:built_value/built_value.dart';
import 'package:built_value/serializer.dart';

part 'approve_review_request.g.dart';

/// ApproveReviewRequest
///
/// Properties:
/// * [expectedAiGradeId]
/// * [expectedVersion]
/// * [note]
@BuiltValue()
abstract class ApproveReviewRequest
    implements Built<ApproveReviewRequest, ApproveReviewRequestBuilder> {
  @BuiltValueField(wireName: r'expected_ai_grade_id')
  String? get expectedAiGradeId;

  @BuiltValueField(wireName: r'expected_version')
  int get expectedVersion;

  @BuiltValueField(wireName: r'note')
  String? get note;

  ApproveReviewRequest._();

  factory ApproveReviewRequest([void updates(ApproveReviewRequestBuilder b)]) =
      _$ApproveReviewRequest;

  @BuiltValueHook(initializeBuilder: true)
  static void _defaults(ApproveReviewRequestBuilder b) => b;

  @BuiltValueSerializer(custom: true)
  static Serializer<ApproveReviewRequest> get serializer =>
      _$ApproveReviewRequestSerializer();
}

class _$ApproveReviewRequestSerializer
    implements PrimitiveSerializer<ApproveReviewRequest> {
  @override
  final Iterable<Type> types = const [
    ApproveReviewRequest,
    _$ApproveReviewRequest
  ];

  @override
  final String wireName = r'ApproveReviewRequest';

  Iterable<Object?> _serializeProperties(
    Serializers serializers,
    ApproveReviewRequest object, {
    FullType specifiedType = FullType.unspecified,
  }) sync* {
    if (object.expectedAiGradeId != null) {
      yield r'expected_ai_grade_id';
      yield serializers.serialize(
        object.expectedAiGradeId,
        specifiedType: const FullType.nullable(String),
      );
    }
    yield r'expected_version';
    yield serializers.serialize(
      object.expectedVersion,
      specifiedType: const FullType(int),
    );
    if (object.note != null) {
      yield r'note';
      yield serializers.serialize(
        object.note,
        specifiedType: const FullType.nullable(String),
      );
    }
  }

  @override
  Object serialize(
    Serializers serializers,
    ApproveReviewRequest object, {
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
    required ApproveReviewRequestBuilder result,
    required List<Object?> unhandled,
  }) {
    for (var i = 0; i < serializedList.length; i += 2) {
      final key = serializedList[i] as String;
      final value = serializedList[i + 1];
      switch (key) {
        case r'expected_ai_grade_id':
          final valueDes = serializers.deserialize(
            value,
            specifiedType: const FullType.nullable(String),
          ) as String?;
          if (valueDes == null) continue;
          result.expectedAiGradeId = valueDes;
          break;
        case r'expected_version':
          final valueDes = serializers.deserialize(
            value,
            specifiedType: const FullType(int),
          ) as int;
          result.expectedVersion = valueDes;
          break;
        case r'note':
          final valueDes = serializers.deserialize(
            value,
            specifiedType: const FullType.nullable(String),
          ) as String?;
          if (valueDes == null) continue;
          result.note = valueDes;
          break;
        default:
          unhandled.add(key);
          unhandled.add(value);
          break;
      }
    }
  }

  @override
  ApproveReviewRequest deserialize(
    Serializers serializers,
    Object serialized, {
    FullType specifiedType = FullType.unspecified,
  }) {
    final result = ApproveReviewRequestBuilder();
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
