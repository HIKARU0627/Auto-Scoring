//
// AUTO-GENERATED FILE, DO NOT MODIFY!
//

// ignore_for_file: unused_element
import 'package:built_value/built_value.dart';
import 'package:built_value/serializer.dart';

part 'job_response.g.dart';

/// JobResponse
///
/// Properties:
/// * [attempts]
/// * [blockedOnQuestionId]
/// * [createdAt]
/// * [dependencyGraphVersion]
/// * [errorCode]
/// * [id]
/// * [kind]
/// * [lastError]
/// * [maxAttempts]
/// * [questionId]
/// * [state]
/// * [submissionId]
/// * [updatedAt]
/// * [usable]
@BuiltValue()
abstract class JobResponse implements Built<JobResponse, JobResponseBuilder> {
  @BuiltValueField(wireName: r'attempts')
  int get attempts;

  @BuiltValueField(wireName: r'blocked_on_question_id')
  String? get blockedOnQuestionId;

  @BuiltValueField(wireName: r'created_at')
  DateTime get createdAt;

  @BuiltValueField(wireName: r'dependency_graph_version')
  int? get dependencyGraphVersion;

  @BuiltValueField(wireName: r'error_code')
  String? get errorCode;

  @BuiltValueField(wireName: r'id')
  String get id;

  @BuiltValueField(wireName: r'kind')
  String get kind;

  @BuiltValueField(wireName: r'last_error')
  String? get lastError;

  @BuiltValueField(wireName: r'max_attempts')
  int get maxAttempts;

  @BuiltValueField(wireName: r'question_id')
  String? get questionId;

  @BuiltValueField(wireName: r'state')
  String get state;

  @BuiltValueField(wireName: r'submission_id')
  String get submissionId;

  @BuiltValueField(wireName: r'updated_at')
  DateTime get updatedAt;

  @BuiltValueField(wireName: r'usable')
  bool? get usable;

  JobResponse._();

  factory JobResponse([void updates(JobResponseBuilder b)]) = _$JobResponse;

  @BuiltValueHook(initializeBuilder: true)
  static void _defaults(JobResponseBuilder b) => b;

  @BuiltValueSerializer(custom: true)
  static Serializer<JobResponse> get serializer => _$JobResponseSerializer();
}

class _$JobResponseSerializer implements PrimitiveSerializer<JobResponse> {
  @override
  final Iterable<Type> types = const [JobResponse, _$JobResponse];

  @override
  final String wireName = r'JobResponse';

  Iterable<Object?> _serializeProperties(
    Serializers serializers,
    JobResponse object, {
    FullType specifiedType = FullType.unspecified,
  }) sync* {
    yield r'attempts';
    yield serializers.serialize(
      object.attempts,
      specifiedType: const FullType(int),
    );
    if (object.blockedOnQuestionId != null) {
      yield r'blocked_on_question_id';
      yield serializers.serialize(
        object.blockedOnQuestionId,
        specifiedType: const FullType.nullable(String),
      );
    }
    yield r'created_at';
    yield serializers.serialize(
      object.createdAt,
      specifiedType: const FullType(DateTime),
    );
    if (object.dependencyGraphVersion != null) {
      yield r'dependency_graph_version';
      yield serializers.serialize(
        object.dependencyGraphVersion,
        specifiedType: const FullType.nullable(int),
      );
    }
    if (object.errorCode != null) {
      yield r'error_code';
      yield serializers.serialize(
        object.errorCode,
        specifiedType: const FullType.nullable(String),
      );
    }
    yield r'id';
    yield serializers.serialize(
      object.id,
      specifiedType: const FullType(String),
    );
    yield r'kind';
    yield serializers.serialize(
      object.kind,
      specifiedType: const FullType(String),
    );
    if (object.lastError != null) {
      yield r'last_error';
      yield serializers.serialize(
        object.lastError,
        specifiedType: const FullType.nullable(String),
      );
    }
    yield r'max_attempts';
    yield serializers.serialize(
      object.maxAttempts,
      specifiedType: const FullType(int),
    );
    if (object.questionId != null) {
      yield r'question_id';
      yield serializers.serialize(
        object.questionId,
        specifiedType: const FullType.nullable(String),
      );
    }
    yield r'state';
    yield serializers.serialize(
      object.state,
      specifiedType: const FullType(String),
    );
    yield r'submission_id';
    yield serializers.serialize(
      object.submissionId,
      specifiedType: const FullType(String),
    );
    yield r'updated_at';
    yield serializers.serialize(
      object.updatedAt,
      specifiedType: const FullType(DateTime),
    );
    if (object.usable != null) {
      yield r'usable';
      yield serializers.serialize(
        object.usable,
        specifiedType: const FullType.nullable(bool),
      );
    }
  }

  @override
  Object serialize(
    Serializers serializers,
    JobResponse object, {
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
    required JobResponseBuilder result,
    required List<Object?> unhandled,
  }) {
    for (var i = 0; i < serializedList.length; i += 2) {
      final key = serializedList[i] as String;
      final value = serializedList[i + 1];
      switch (key) {
        case r'attempts':
          final valueDes = serializers.deserialize(
            value,
            specifiedType: const FullType(int),
          ) as int;
          result.attempts = valueDes;
          break;
        case r'blocked_on_question_id':
          final valueDes = serializers.deserialize(
            value,
            specifiedType: const FullType.nullable(String),
          ) as String?;
          if (valueDes == null) continue;
          result.blockedOnQuestionId = valueDes;
          break;
        case r'created_at':
          final valueDes = serializers.deserialize(
            value,
            specifiedType: const FullType(DateTime),
          ) as DateTime;
          result.createdAt = valueDes;
          break;
        case r'dependency_graph_version':
          final valueDes = serializers.deserialize(
            value,
            specifiedType: const FullType.nullable(int),
          ) as int?;
          if (valueDes == null) continue;
          result.dependencyGraphVersion = valueDes;
          break;
        case r'error_code':
          final valueDes = serializers.deserialize(
            value,
            specifiedType: const FullType.nullable(String),
          ) as String?;
          if (valueDes == null) continue;
          result.errorCode = valueDes;
          break;
        case r'id':
          final valueDes = serializers.deserialize(
            value,
            specifiedType: const FullType(String),
          ) as String;
          result.id = valueDes;
          break;
        case r'kind':
          final valueDes = serializers.deserialize(
            value,
            specifiedType: const FullType(String),
          ) as String;
          result.kind = valueDes;
          break;
        case r'last_error':
          final valueDes = serializers.deserialize(
            value,
            specifiedType: const FullType.nullable(String),
          ) as String?;
          if (valueDes == null) continue;
          result.lastError = valueDes;
          break;
        case r'max_attempts':
          final valueDes = serializers.deserialize(
            value,
            specifiedType: const FullType(int),
          ) as int;
          result.maxAttempts = valueDes;
          break;
        case r'question_id':
          final valueDes = serializers.deserialize(
            value,
            specifiedType: const FullType.nullable(String),
          ) as String?;
          if (valueDes == null) continue;
          result.questionId = valueDes;
          break;
        case r'state':
          final valueDes = serializers.deserialize(
            value,
            specifiedType: const FullType(String),
          ) as String;
          result.state = valueDes;
          break;
        case r'submission_id':
          final valueDes = serializers.deserialize(
            value,
            specifiedType: const FullType(String),
          ) as String;
          result.submissionId = valueDes;
          break;
        case r'updated_at':
          final valueDes = serializers.deserialize(
            value,
            specifiedType: const FullType(DateTime),
          ) as DateTime;
          result.updatedAt = valueDes;
          break;
        case r'usable':
          final valueDes = serializers.deserialize(
            value,
            specifiedType: const FullType.nullable(bool),
          ) as bool?;
          if (valueDes == null) continue;
          result.usable = valueDes;
          break;
        default:
          unhandled.add(key);
          unhandled.add(value);
          break;
      }
    }
  }

  @override
  JobResponse deserialize(
    Serializers serializers,
    Object serialized, {
    FullType specifiedType = FullType.unspecified,
  }) {
    final result = JobResponseBuilder();
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
