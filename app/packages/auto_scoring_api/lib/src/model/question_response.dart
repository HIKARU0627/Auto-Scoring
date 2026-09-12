//
// AUTO-GENERATED FILE, DO NOT MODIFY!
//

// ignore_for_file: unused_element
import 'package:auto_scoring_api/src/model/rubric_criterion_response.dart';
import 'package:built_collection/built_collection.dart';
import 'package:auto_scoring_api/src/model/normalized_rect_response.dart';
import 'package:auto_scoring_api/src/model/question_score_placement_response.dart';
import 'package:built_value/built_value.dart';
import 'package:built_value/serializer.dart';

part 'question_response.g.dart';

/// QuestionResponse
///
/// Properties:
/// * [answerArea]
/// * [commentArea]
/// * [id]
/// * [isScoringTarget]
/// * [modelAnswer]
/// * [number]
/// * [page]
/// * [points]
/// * [rubric]
/// * [scoreArea]
/// * [scorePlacement]
/// * [scoringMethod]
/// * [testId]
@BuiltValue()
abstract class QuestionResponse
    implements Built<QuestionResponse, QuestionResponseBuilder> {
  @BuiltValueField(wireName: r'answer_area')
  NormalizedRectResponse? get answerArea;

  @BuiltValueField(wireName: r'comment_area')
  NormalizedRectResponse? get commentArea;

  @BuiltValueField(wireName: r'id')
  String get id;

  @BuiltValueField(wireName: r'is_scoring_target')
  bool? get isScoringTarget;

  @BuiltValueField(wireName: r'model_answer')
  String? get modelAnswer;

  @BuiltValueField(wireName: r'number')
  String get number;

  @BuiltValueField(wireName: r'page')
  int get page;

  @BuiltValueField(wireName: r'points')
  int get points;

  @BuiltValueField(wireName: r'rubric')
  BuiltList<RubricCriterionResponse> get rubric;

  @BuiltValueField(wireName: r'score_area')
  NormalizedRectResponse? get scoreArea;

  @BuiltValueField(wireName: r'score_placement')
  QuestionScorePlacementResponse? get scorePlacement;

  @BuiltValueField(wireName: r'scoring_method')
  String get scoringMethod;

  @BuiltValueField(wireName: r'test_id')
  String get testId;

  QuestionResponse._();

  factory QuestionResponse([void updates(QuestionResponseBuilder b)]) =
      _$QuestionResponse;

  @BuiltValueHook(initializeBuilder: true)
  static void _defaults(QuestionResponseBuilder b) => b..isScoringTarget = true;

  @BuiltValueSerializer(custom: true)
  static Serializer<QuestionResponse> get serializer =>
      _$QuestionResponseSerializer();
}

class _$QuestionResponseSerializer
    implements PrimitiveSerializer<QuestionResponse> {
  @override
  final Iterable<Type> types = const [QuestionResponse, _$QuestionResponse];

  @override
  final String wireName = r'QuestionResponse';

  Iterable<Object?> _serializeProperties(
    Serializers serializers,
    QuestionResponse object, {
    FullType specifiedType = FullType.unspecified,
  }) sync* {
    if (object.answerArea != null) {
      yield r'answer_area';
      yield serializers.serialize(
        object.answerArea,
        specifiedType: const FullType.nullable(NormalizedRectResponse),
      );
    }
    if (object.commentArea != null) {
      yield r'comment_area';
      yield serializers.serialize(
        object.commentArea,
        specifiedType: const FullType.nullable(NormalizedRectResponse),
      );
    }
    yield r'id';
    yield serializers.serialize(
      object.id,
      specifiedType: const FullType(String),
    );
    if (object.isScoringTarget != null) {
      yield r'is_scoring_target';
      yield serializers.serialize(
        object.isScoringTarget,
        specifiedType: const FullType(bool),
      );
    }
    if (object.modelAnswer != null) {
      yield r'model_answer';
      yield serializers.serialize(
        object.modelAnswer,
        specifiedType: const FullType.nullable(String),
      );
    }
    yield r'number';
    yield serializers.serialize(
      object.number,
      specifiedType: const FullType(String),
    );
    yield r'page';
    yield serializers.serialize(
      object.page,
      specifiedType: const FullType(int),
    );
    yield r'points';
    yield serializers.serialize(
      object.points,
      specifiedType: const FullType(int),
    );
    yield r'rubric';
    yield serializers.serialize(
      object.rubric,
      specifiedType:
          const FullType(BuiltList, [FullType(RubricCriterionResponse)]),
    );
    if (object.scoreArea != null) {
      yield r'score_area';
      yield serializers.serialize(
        object.scoreArea,
        specifiedType: const FullType.nullable(NormalizedRectResponse),
      );
    }
    if (object.scorePlacement != null) {
      yield r'score_placement';
      yield serializers.serialize(
        object.scorePlacement,
        specifiedType: const FullType.nullable(QuestionScorePlacementResponse),
      );
    }
    yield r'scoring_method';
    yield serializers.serialize(
      object.scoringMethod,
      specifiedType: const FullType(String),
    );
    yield r'test_id';
    yield serializers.serialize(
      object.testId,
      specifiedType: const FullType(String),
    );
  }

  @override
  Object serialize(
    Serializers serializers,
    QuestionResponse object, {
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
    required QuestionResponseBuilder result,
    required List<Object?> unhandled,
  }) {
    for (var i = 0; i < serializedList.length; i += 2) {
      final key = serializedList[i] as String;
      final value = serializedList[i + 1];
      switch (key) {
        case r'answer_area':
          final valueDes = serializers.deserialize(
            value,
            specifiedType: const FullType.nullable(NormalizedRectResponse),
          ) as NormalizedRectResponse?;
          if (valueDes == null) continue;
          result.answerArea.replace(valueDes);
          break;
        case r'comment_area':
          final valueDes = serializers.deserialize(
            value,
            specifiedType: const FullType.nullable(NormalizedRectResponse),
          ) as NormalizedRectResponse?;
          if (valueDes == null) continue;
          result.commentArea.replace(valueDes);
          break;
        case r'id':
          final valueDes = serializers.deserialize(
            value,
            specifiedType: const FullType(String),
          ) as String;
          result.id = valueDes;
          break;
        case r'is_scoring_target':
          final valueDes = serializers.deserialize(
            value,
            specifiedType: const FullType.nullable(bool),
          ) as bool?;
          if (valueDes == null) continue;
          result.isScoringTarget = valueDes;
          break;
        case r'model_answer':
          final valueDes = serializers.deserialize(
            value,
            specifiedType: const FullType.nullable(String),
          ) as String?;
          if (valueDes == null) continue;
          result.modelAnswer = valueDes;
          break;
        case r'number':
          final valueDes = serializers.deserialize(
            value,
            specifiedType: const FullType(String),
          ) as String;
          result.number = valueDes;
          break;
        case r'page':
          final valueDes = serializers.deserialize(
            value,
            specifiedType: const FullType(int),
          ) as int;
          result.page = valueDes;
          break;
        case r'points':
          final valueDes = serializers.deserialize(
            value,
            specifiedType: const FullType(int),
          ) as int;
          result.points = valueDes;
          break;
        case r'rubric':
          final valueDes = serializers.deserialize(
            value,
            specifiedType:
                const FullType(BuiltList, [FullType(RubricCriterionResponse)]),
          ) as BuiltList<RubricCriterionResponse>;
          result.rubric.replace(valueDes);
          break;
        case r'score_area':
          final valueDes = serializers.deserialize(
            value,
            specifiedType: const FullType.nullable(NormalizedRectResponse),
          ) as NormalizedRectResponse?;
          if (valueDes == null) continue;
          result.scoreArea.replace(valueDes);
          break;
        case r'score_placement':
          final valueDes = serializers.deserialize(
            value,
            specifiedType:
                const FullType.nullable(QuestionScorePlacementResponse),
          ) as QuestionScorePlacementResponse?;
          if (valueDes == null) continue;
          result.scorePlacement.replace(valueDes);
          break;
        case r'scoring_method':
          final valueDes = serializers.deserialize(
            value,
            specifiedType: const FullType(String),
          ) as String;
          result.scoringMethod = valueDes;
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
  QuestionResponse deserialize(
    Serializers serializers,
    Object serialized, {
    FullType specifiedType = FullType.unspecified,
  }) {
    final result = QuestionResponseBuilder();
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
