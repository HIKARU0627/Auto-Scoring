//
// AUTO-GENERATED FILE, DO NOT MODIFY!
//

// ignore_for_file: unused_element
import 'package:built_collection/built_collection.dart';
import 'package:auto_scoring_api/src/model/criteria_item_model.dart';
import 'package:built_value/built_value.dart';
import 'package:built_value/serializer.dart';

part 'criteria_question_model.g.dart';

/// One question's allocation and criteria, over the wire.  ``points`` being ``null`` is the 不明 the whole feature is built around: it means \"this could not be read\", never 0. The app renders it as 不明 and refuses to confirm while any remain.
///
/// Properties:
/// * [criteria]
/// * [modelAnswer]
/// * [note]
/// * [number]
/// * [points]
/// * [sourcePages]
@BuiltValue()
abstract class CriteriaQuestionModel
    implements Built<CriteriaQuestionModel, CriteriaQuestionModelBuilder> {
  @BuiltValueField(wireName: r'criteria')
  BuiltList<CriteriaItemModel> get criteria;

  @BuiltValueField(wireName: r'model_answer')
  String? get modelAnswer;

  @BuiltValueField(wireName: r'note')
  String? get note;

  @BuiltValueField(wireName: r'number')
  String get number;

  @BuiltValueField(wireName: r'points')
  int? get points;

  @BuiltValueField(wireName: r'source_pages')
  BuiltList<int> get sourcePages;

  CriteriaQuestionModel._();

  factory CriteriaQuestionModel(
      [void updates(CriteriaQuestionModelBuilder b)]) = _$CriteriaQuestionModel;

  @BuiltValueHook(initializeBuilder: true)
  static void _defaults(CriteriaQuestionModelBuilder b) => b;

  @BuiltValueSerializer(custom: true)
  static Serializer<CriteriaQuestionModel> get serializer =>
      _$CriteriaQuestionModelSerializer();
}

class _$CriteriaQuestionModelSerializer
    implements PrimitiveSerializer<CriteriaQuestionModel> {
  @override
  final Iterable<Type> types = const [
    CriteriaQuestionModel,
    _$CriteriaQuestionModel
  ];

  @override
  final String wireName = r'CriteriaQuestionModel';

  Iterable<Object?> _serializeProperties(
    Serializers serializers,
    CriteriaQuestionModel object, {
    FullType specifiedType = FullType.unspecified,
  }) sync* {
    yield r'criteria';
    yield serializers.serialize(
      object.criteria,
      specifiedType: const FullType(BuiltList, [FullType(CriteriaItemModel)]),
    );
    if (object.modelAnswer != null) {
      yield r'model_answer';
      yield serializers.serialize(
        object.modelAnswer,
        specifiedType: const FullType.nullable(String),
      );
    }
    if (object.note != null) {
      yield r'note';
      yield serializers.serialize(
        object.note,
        specifiedType: const FullType.nullable(String),
      );
    }
    yield r'number';
    yield serializers.serialize(
      object.number,
      specifiedType: const FullType(String),
    );
    if (object.points != null) {
      yield r'points';
      yield serializers.serialize(
        object.points,
        specifiedType: const FullType.nullable(int),
      );
    }
    yield r'source_pages';
    yield serializers.serialize(
      object.sourcePages,
      specifiedType: const FullType(BuiltList, [FullType(int)]),
    );
  }

  @override
  Object serialize(
    Serializers serializers,
    CriteriaQuestionModel object, {
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
    required CriteriaQuestionModelBuilder result,
    required List<Object?> unhandled,
  }) {
    for (var i = 0; i < serializedList.length; i += 2) {
      final key = serializedList[i] as String;
      final value = serializedList[i + 1];
      switch (key) {
        case r'criteria':
          final valueDes = serializers.deserialize(
            value,
            specifiedType:
                const FullType(BuiltList, [FullType(CriteriaItemModel)]),
          ) as BuiltList<CriteriaItemModel>;
          result.criteria.replace(valueDes);
          break;
        case r'model_answer':
          final valueDes = serializers.deserialize(
            value,
            specifiedType: const FullType.nullable(String),
          ) as String?;
          if (valueDes == null) continue;
          result.modelAnswer = valueDes;
          break;
        case r'note':
          final valueDes = serializers.deserialize(
            value,
            specifiedType: const FullType.nullable(String),
          ) as String?;
          if (valueDes == null) continue;
          result.note = valueDes;
          break;
        case r'number':
          final valueDes = serializers.deserialize(
            value,
            specifiedType: const FullType(String),
          ) as String;
          result.number = valueDes;
          break;
        case r'points':
          final valueDes = serializers.deserialize(
            value,
            specifiedType: const FullType.nullable(int),
          ) as int?;
          if (valueDes == null) continue;
          result.points = valueDes;
          break;
        case r'source_pages':
          final valueDes = serializers.deserialize(
            value,
            specifiedType: const FullType(BuiltList, [FullType(int)]),
          ) as BuiltList<int>;
          result.sourcePages.replace(valueDes);
          break;
        default:
          unhandled.add(key);
          unhandled.add(value);
          break;
      }
    }
  }

  @override
  CriteriaQuestionModel deserialize(
    Serializers serializers,
    Object serialized, {
    FullType specifiedType = FullType.unspecified,
  }) {
    final result = CriteriaQuestionModelBuilder();
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
