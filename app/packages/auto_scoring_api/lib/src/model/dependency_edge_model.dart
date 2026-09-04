//
// AUTO-GENERATED FILE, DO NOT MODIFY!
//

// ignore_for_file: unused_element
import 'package:built_collection/built_collection.dart';
import 'package:built_value/built_value.dart';
import 'package:built_value/serializer.dart';

part 'dependency_edge_model.g.dart';

/// DependencyEdgeModel
///
/// Properties:
/// * [confidence]
/// * [fromQuestionId]
/// * [provides]
/// * [rationale]
/// * [toQuestionId]
@BuiltValue()
abstract class DependencyEdgeModel
    implements Built<DependencyEdgeModel, DependencyEdgeModelBuilder> {
  @BuiltValueField(wireName: r'confidence')
  num? get confidence;

  @BuiltValueField(wireName: r'from_question_id')
  String get fromQuestionId;

  @BuiltValueField(wireName: r'provides')
  BuiltList<String> get provides;

  @BuiltValueField(wireName: r'rationale')
  String get rationale;

  @BuiltValueField(wireName: r'to_question_id')
  String get toQuestionId;

  DependencyEdgeModel._();

  factory DependencyEdgeModel([void updates(DependencyEdgeModelBuilder b)]) =
      _$DependencyEdgeModel;

  @BuiltValueHook(initializeBuilder: true)
  static void _defaults(DependencyEdgeModelBuilder b) => b;

  @BuiltValueSerializer(custom: true)
  static Serializer<DependencyEdgeModel> get serializer =>
      _$DependencyEdgeModelSerializer();
}

class _$DependencyEdgeModelSerializer
    implements PrimitiveSerializer<DependencyEdgeModel> {
  @override
  final Iterable<Type> types = const [
    DependencyEdgeModel,
    _$DependencyEdgeModel
  ];

  @override
  final String wireName = r'DependencyEdgeModel';

  Iterable<Object?> _serializeProperties(
    Serializers serializers,
    DependencyEdgeModel object, {
    FullType specifiedType = FullType.unspecified,
  }) sync* {
    if (object.confidence != null) {
      yield r'confidence';
      yield serializers.serialize(
        object.confidence,
        specifiedType: const FullType.nullable(num),
      );
    }
    yield r'from_question_id';
    yield serializers.serialize(
      object.fromQuestionId,
      specifiedType: const FullType(String),
    );
    yield r'provides';
    yield serializers.serialize(
      object.provides,
      specifiedType: const FullType(BuiltList, [FullType(String)]),
    );
    yield r'rationale';
    yield serializers.serialize(
      object.rationale,
      specifiedType: const FullType(String),
    );
    yield r'to_question_id';
    yield serializers.serialize(
      object.toQuestionId,
      specifiedType: const FullType(String),
    );
  }

  @override
  Object serialize(
    Serializers serializers,
    DependencyEdgeModel object, {
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
    required DependencyEdgeModelBuilder result,
    required List<Object?> unhandled,
  }) {
    for (var i = 0; i < serializedList.length; i += 2) {
      final key = serializedList[i] as String;
      final value = serializedList[i + 1];
      switch (key) {
        case r'confidence':
          final valueDes = serializers.deserialize(
            value,
            specifiedType: const FullType.nullable(num),
          ) as num?;
          if (valueDes == null) continue;
          result.confidence = valueDes;
          break;
        case r'from_question_id':
          final valueDes = serializers.deserialize(
            value,
            specifiedType: const FullType(String),
          ) as String;
          result.fromQuestionId = valueDes;
          break;
        case r'provides':
          final valueDes = serializers.deserialize(
            value,
            specifiedType: const FullType(BuiltList, [FullType(String)]),
          ) as BuiltList<String>;
          result.provides.replace(valueDes);
          break;
        case r'rationale':
          final valueDes = serializers.deserialize(
            value,
            specifiedType: const FullType(String),
          ) as String;
          result.rationale = valueDes;
          break;
        case r'to_question_id':
          final valueDes = serializers.deserialize(
            value,
            specifiedType: const FullType(String),
          ) as String;
          result.toQuestionId = valueDes;
          break;
        default:
          unhandled.add(key);
          unhandled.add(value);
          break;
      }
    }
  }

  @override
  DependencyEdgeModel deserialize(
    Serializers serializers,
    Object serialized, {
    FullType specifiedType = FullType.unspecified,
  }) {
    final result = DependencyEdgeModelBuilder();
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
