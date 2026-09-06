//
// AUTO-GENERATED FILE, DO NOT MODIFY!
//

// ignore_for_file: unused_element
import 'package:auto_scoring_api/src/model/bounding_box_response.dart';
import 'package:built_collection/built_collection.dart';
import 'package:built_value/built_value.dart';
import 'package:built_value/serializer.dart';

part 'recognition_response.g.dart';

/// RecognitionResponse
///
/// Properties:
/// * [boxes]
/// * [confidence]
/// * [createdAt]
/// * [id]
/// * [questionId]
/// * [source_]
/// * [stage]
/// * [submissionId]
/// * [text]
@BuiltValue()
abstract class RecognitionResponse
    implements Built<RecognitionResponse, RecognitionResponseBuilder> {
  @BuiltValueField(wireName: r'boxes')
  BuiltList<BoundingBoxResponse> get boxes;

  @BuiltValueField(wireName: r'confidence')
  num get confidence;

  @BuiltValueField(wireName: r'created_at')
  DateTime get createdAt;

  @BuiltValueField(wireName: r'id')
  String get id;

  @BuiltValueField(wireName: r'question_id')
  String get questionId;

  @BuiltValueField(wireName: r'source')
  String get source_;

  @BuiltValueField(wireName: r'stage')
  String get stage;

  @BuiltValueField(wireName: r'submission_id')
  String get submissionId;

  @BuiltValueField(wireName: r'text')
  String get text;

  RecognitionResponse._();

  factory RecognitionResponse([void updates(RecognitionResponseBuilder b)]) =
      _$RecognitionResponse;

  @BuiltValueHook(initializeBuilder: true)
  static void _defaults(RecognitionResponseBuilder b) => b;

  @BuiltValueSerializer(custom: true)
  static Serializer<RecognitionResponse> get serializer =>
      _$RecognitionResponseSerializer();
}

class _$RecognitionResponseSerializer
    implements PrimitiveSerializer<RecognitionResponse> {
  @override
  final Iterable<Type> types = const [
    RecognitionResponse,
    _$RecognitionResponse
  ];

  @override
  final String wireName = r'RecognitionResponse';

  Iterable<Object?> _serializeProperties(
    Serializers serializers,
    RecognitionResponse object, {
    FullType specifiedType = FullType.unspecified,
  }) sync* {
    yield r'boxes';
    yield serializers.serialize(
      object.boxes,
      specifiedType: const FullType(BuiltList, [FullType(BoundingBoxResponse)]),
    );
    yield r'confidence';
    yield serializers.serialize(
      object.confidence,
      specifiedType: const FullType(num),
    );
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
    yield r'question_id';
    yield serializers.serialize(
      object.questionId,
      specifiedType: const FullType(String),
    );
    yield r'source';
    yield serializers.serialize(
      object.source_,
      specifiedType: const FullType(String),
    );
    yield r'stage';
    yield serializers.serialize(
      object.stage,
      specifiedType: const FullType(String),
    );
    yield r'submission_id';
    yield serializers.serialize(
      object.submissionId,
      specifiedType: const FullType(String),
    );
    yield r'text';
    yield serializers.serialize(
      object.text,
      specifiedType: const FullType(String),
    );
  }

  @override
  Object serialize(
    Serializers serializers,
    RecognitionResponse object, {
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
    required RecognitionResponseBuilder result,
    required List<Object?> unhandled,
  }) {
    for (var i = 0; i < serializedList.length; i += 2) {
      final key = serializedList[i] as String;
      final value = serializedList[i + 1];
      switch (key) {
        case r'boxes':
          final valueDes = serializers.deserialize(
            value,
            specifiedType:
                const FullType(BuiltList, [FullType(BoundingBoxResponse)]),
          ) as BuiltList<BoundingBoxResponse>;
          result.boxes.replace(valueDes);
          break;
        case r'confidence':
          final valueDes = serializers.deserialize(
            value,
            specifiedType: const FullType(num),
          ) as num;
          result.confidence = valueDes;
          break;
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
        case r'question_id':
          final valueDes = serializers.deserialize(
            value,
            specifiedType: const FullType(String),
          ) as String;
          result.questionId = valueDes;
          break;
        case r'source':
          final valueDes = serializers.deserialize(
            value,
            specifiedType: const FullType(String),
          ) as String;
          result.source_ = valueDes;
          break;
        case r'stage':
          final valueDes = serializers.deserialize(
            value,
            specifiedType: const FullType(String),
          ) as String;
          result.stage = valueDes;
          break;
        case r'submission_id':
          final valueDes = serializers.deserialize(
            value,
            specifiedType: const FullType(String),
          ) as String;
          result.submissionId = valueDes;
          break;
        case r'text':
          final valueDes = serializers.deserialize(
            value,
            specifiedType: const FullType(String),
          ) as String;
          result.text = valueDes;
          break;
        default:
          unhandled.add(key);
          unhandled.add(value);
          break;
      }
    }
  }

  @override
  RecognitionResponse deserialize(
    Serializers serializers,
    Object serialized, {
    FullType specifiedType = FullType.unspecified,
  }) {
    final result = RecognitionResponseBuilder();
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
