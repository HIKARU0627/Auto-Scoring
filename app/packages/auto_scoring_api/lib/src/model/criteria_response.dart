//
// AUTO-GENERATED FILE, DO NOT MODIFY!
//

// ignore_for_file: unused_element
import 'package:auto_scoring_api/src/model/criteria_status.dart';
import 'package:built_collection/built_collection.dart';
import 'package:auto_scoring_api/src/model/criteria_totals_model.dart';
import 'package:auto_scoring_api/src/model/criteria_question_model.dart';
import 'package:built_value/built_value.dart';
import 'package:built_value/serializer.dart';

part 'criteria_response.g.dart';

/// A test's 配点と採点基準, as the review screen sees it.
///
/// Properties:
/// * [declaredTotalPoints]
/// * [extracted]
/// * [note]
/// * [questions]
/// * [revision]
/// * [status]
/// * [testId]
/// * [totals]
/// * [unreadablePages]
@BuiltValue()
abstract class CriteriaResponse
    implements Built<CriteriaResponse, CriteriaResponseBuilder> {
  @BuiltValueField(wireName: r'declared_total_points')
  int? get declaredTotalPoints;

  @BuiltValueField(wireName: r'extracted')
  bool get extracted;

  @BuiltValueField(wireName: r'note')
  String? get note;

  @BuiltValueField(wireName: r'questions')
  BuiltList<CriteriaQuestionModel> get questions;

  @BuiltValueField(wireName: r'revision')
  int get revision;

  @BuiltValueField(wireName: r'status')
  CriteriaStatus get status;
  // enum statusEnum {  draft,  confirmed,  };

  @BuiltValueField(wireName: r'test_id')
  String get testId;

  @BuiltValueField(wireName: r'totals')
  CriteriaTotalsModel get totals;

  @BuiltValueField(wireName: r'unreadable_pages')
  BuiltList<int> get unreadablePages;

  CriteriaResponse._();

  factory CriteriaResponse([void updates(CriteriaResponseBuilder b)]) =
      _$CriteriaResponse;

  @BuiltValueHook(initializeBuilder: true)
  static void _defaults(CriteriaResponseBuilder b) => b;

  @BuiltValueSerializer(custom: true)
  static Serializer<CriteriaResponse> get serializer =>
      _$CriteriaResponseSerializer();
}

class _$CriteriaResponseSerializer
    implements PrimitiveSerializer<CriteriaResponse> {
  @override
  final Iterable<Type> types = const [CriteriaResponse, _$CriteriaResponse];

  @override
  final String wireName = r'CriteriaResponse';

  Iterable<Object?> _serializeProperties(
    Serializers serializers,
    CriteriaResponse object, {
    FullType specifiedType = FullType.unspecified,
  }) sync* {
    if (object.declaredTotalPoints != null) {
      yield r'declared_total_points';
      yield serializers.serialize(
        object.declaredTotalPoints,
        specifiedType: const FullType.nullable(int),
      );
    }
    yield r'extracted';
    yield serializers.serialize(
      object.extracted,
      specifiedType: const FullType(bool),
    );
    if (object.note != null) {
      yield r'note';
      yield serializers.serialize(
        object.note,
        specifiedType: const FullType.nullable(String),
      );
    }
    yield r'questions';
    yield serializers.serialize(
      object.questions,
      specifiedType:
          const FullType(BuiltList, [FullType(CriteriaQuestionModel)]),
    );
    yield r'revision';
    yield serializers.serialize(
      object.revision,
      specifiedType: const FullType(int),
    );
    yield r'status';
    yield serializers.serialize(
      object.status,
      specifiedType: const FullType(CriteriaStatus),
    );
    yield r'test_id';
    yield serializers.serialize(
      object.testId,
      specifiedType: const FullType(String),
    );
    yield r'totals';
    yield serializers.serialize(
      object.totals,
      specifiedType: const FullType(CriteriaTotalsModel),
    );
    yield r'unreadable_pages';
    yield serializers.serialize(
      object.unreadablePages,
      specifiedType: const FullType(BuiltList, [FullType(int)]),
    );
  }

  @override
  Object serialize(
    Serializers serializers,
    CriteriaResponse object, {
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
    required CriteriaResponseBuilder result,
    required List<Object?> unhandled,
  }) {
    for (var i = 0; i < serializedList.length; i += 2) {
      final key = serializedList[i] as String;
      final value = serializedList[i + 1];
      switch (key) {
        case r'declared_total_points':
          final valueDes = serializers.deserialize(
            value,
            specifiedType: const FullType.nullable(int),
          ) as int?;
          if (valueDes == null) continue;
          result.declaredTotalPoints = valueDes;
          break;
        case r'extracted':
          final valueDes = serializers.deserialize(
            value,
            specifiedType: const FullType(bool),
          ) as bool;
          result.extracted = valueDes;
          break;
        case r'note':
          final valueDes = serializers.deserialize(
            value,
            specifiedType: const FullType.nullable(String),
          ) as String?;
          if (valueDes == null) continue;
          result.note = valueDes;
          break;
        case r'questions':
          final valueDes = serializers.deserialize(
            value,
            specifiedType:
                const FullType(BuiltList, [FullType(CriteriaQuestionModel)]),
          ) as BuiltList<CriteriaQuestionModel>;
          result.questions.replace(valueDes);
          break;
        case r'revision':
          final valueDes = serializers.deserialize(
            value,
            specifiedType: const FullType(int),
          ) as int;
          result.revision = valueDes;
          break;
        case r'status':
          final valueDes = serializers.deserialize(
            value,
            specifiedType: const FullType(CriteriaStatus),
          ) as CriteriaStatus;
          result.status = valueDes;
          break;
        case r'test_id':
          final valueDes = serializers.deserialize(
            value,
            specifiedType: const FullType(String),
          ) as String;
          result.testId = valueDes;
          break;
        case r'totals':
          final valueDes = serializers.deserialize(
            value,
            specifiedType: const FullType(CriteriaTotalsModel),
          ) as CriteriaTotalsModel;
          result.totals.replace(valueDes);
          break;
        case r'unreadable_pages':
          final valueDes = serializers.deserialize(
            value,
            specifiedType: const FullType(BuiltList, [FullType(int)]),
          ) as BuiltList<int>;
          result.unreadablePages.replace(valueDes);
          break;
        default:
          unhandled.add(key);
          unhandled.add(value);
          break;
      }
    }
  }

  @override
  CriteriaResponse deserialize(
    Serializers serializers,
    Object serialized, {
    FullType specifiedType = FullType.unspecified,
  }) {
    final result = CriteriaResponseBuilder();
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
