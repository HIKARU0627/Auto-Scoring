//
// AUTO-GENERATED FILE, DO NOT MODIFY!
//

// ignore_for_file: unused_element
import 'package:built_value/built_value.dart';
import 'package:built_value/serializer.dart';

part 'submission_response.g.dart';

/// SubmissionResponse
///
/// Properties:
/// * [createdAt]
/// * [id]
/// * [isRetry]
/// * [originalFilename]
/// * [pageCount]
/// * [reviewReason]
/// * [state]
/// * [studentLabel]
/// * [testId]
@BuiltValue()
abstract class SubmissionResponse
    implements Built<SubmissionResponse, SubmissionResponseBuilder> {
  @BuiltValueField(wireName: r'created_at')
  DateTime get createdAt;

  @BuiltValueField(wireName: r'id')
  String get id;

  @BuiltValueField(wireName: r'is_retry')
  bool? get isRetry;

  @BuiltValueField(wireName: r'original_filename')
  String? get originalFilename;

  @BuiltValueField(wireName: r'page_count')
  int get pageCount;

  @BuiltValueField(wireName: r'review_reason')
  String? get reviewReason;

  @BuiltValueField(wireName: r'state')
  String get state;

  @BuiltValueField(wireName: r'student_label')
  String? get studentLabel;

  @BuiltValueField(wireName: r'test_id')
  String get testId;

  SubmissionResponse._();

  factory SubmissionResponse([void updates(SubmissionResponseBuilder b)]) =
      _$SubmissionResponse;

  @BuiltValueHook(initializeBuilder: true)
  static void _defaults(SubmissionResponseBuilder b) => b..isRetry = false;

  @BuiltValueSerializer(custom: true)
  static Serializer<SubmissionResponse> get serializer =>
      _$SubmissionResponseSerializer();
}

class _$SubmissionResponseSerializer
    implements PrimitiveSerializer<SubmissionResponse> {
  @override
  final Iterable<Type> types = const [SubmissionResponse, _$SubmissionResponse];

  @override
  final String wireName = r'SubmissionResponse';

  Iterable<Object?> _serializeProperties(
    Serializers serializers,
    SubmissionResponse object, {
    FullType specifiedType = FullType.unspecified,
  }) sync* {
    yield r'created_at';
    yield serializers.serialize(
      object.createdAt,
      specifiedType: const FullType(DateTime),
    );
    yield r'id';
    yield serializers.serialize(
      object.id,
      specifiedType: const FullType(String),
    );
    if (object.isRetry != null) {
      yield r'is_retry';
      yield serializers.serialize(
        object.isRetry,
        specifiedType: const FullType(bool),
      );
    }
    if (object.originalFilename != null) {
      yield r'original_filename';
      yield serializers.serialize(
        object.originalFilename,
        specifiedType: const FullType.nullable(String),
      );
    }
    yield r'page_count';
    yield serializers.serialize(
      object.pageCount,
      specifiedType: const FullType(int),
    );
    if (object.reviewReason != null) {
      yield r'review_reason';
      yield serializers.serialize(
        object.reviewReason,
        specifiedType: const FullType.nullable(String),
      );
    }
    yield r'state';
    yield serializers.serialize(
      object.state,
      specifiedType: const FullType(String),
    );
    if (object.studentLabel != null) {
      yield r'student_label';
      yield serializers.serialize(
        object.studentLabel,
        specifiedType: const FullType.nullable(String),
      );
    }
    yield r'test_id';
    yield serializers.serialize(
      object.testId,
      specifiedType: const FullType(String),
    );
  }

  @override
  Object serialize(
    Serializers serializers,
    SubmissionResponse object, {
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
    required SubmissionResponseBuilder result,
    required List<Object?> unhandled,
  }) {
    for (var i = 0; i < serializedList.length; i += 2) {
      final key = serializedList[i] as String;
      final value = serializedList[i + 1];
      switch (key) {
        case r'created_at':
          final valueDes = serializers.deserialize(
            value,
            specifiedType: const FullType(DateTime),
          ) as DateTime;
          result.createdAt = valueDes;
          break;
        case r'id':
          final valueDes = serializers.deserialize(
            value,
            specifiedType: const FullType(String),
          ) as String;
          result.id = valueDes;
          break;
        case r'is_retry':
          final valueDes = serializers.deserialize(
            value,
            specifiedType: const FullType.nullable(bool),
          ) as bool?;
          if (valueDes == null) continue;
          result.isRetry = valueDes;
          break;
        case r'original_filename':
          final valueDes = serializers.deserialize(
            value,
            specifiedType: const FullType.nullable(String),
          ) as String?;
          if (valueDes == null) continue;
          result.originalFilename = valueDes;
          break;
        case r'page_count':
          final valueDes = serializers.deserialize(
            value,
            specifiedType: const FullType(int),
          ) as int;
          result.pageCount = valueDes;
          break;
        case r'review_reason':
          final valueDes = serializers.deserialize(
            value,
            specifiedType: const FullType.nullable(String),
          ) as String?;
          if (valueDes == null) continue;
          result.reviewReason = valueDes;
          break;
        case r'state':
          final valueDes = serializers.deserialize(
            value,
            specifiedType: const FullType(String),
          ) as String;
          result.state = valueDes;
          break;
        case r'student_label':
          final valueDes = serializers.deserialize(
            value,
            specifiedType: const FullType.nullable(String),
          ) as String?;
          if (valueDes == null) continue;
          result.studentLabel = valueDes;
          break;
        case r'test_id':
          final valueDes = serializers.deserialize(
            value,
            specifiedType: const FullType(String),
          ) as String;
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
  SubmissionResponse deserialize(
    Serializers serializers,
    Object serialized, {
    FullType specifiedType = FullType.unspecified,
  }) {
    final result = SubmissionResponseBuilder();
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
