//
// AUTO-GENERATED FILE, DO NOT MODIFY!
//

// ignore_for_file: unused_element
import 'package:built_collection/built_collection.dart';
import 'package:auto_scoring_api/src/model/unresolved_question_model.dart';
import 'package:auto_scoring_api/src/model/dependency_edge_model.dart';
import 'package:built_value/built_value.dart';
import 'package:built_value/serializer.dart';

part 'dependency_graph_response.g.dart';

/// DependencyGraphResponse
///
/// Properties:
/// * [confirmedAt]
/// * [createdAt]
/// * [edges]
/// * [id]
/// * [layers]
/// * [questionIds]
/// * [status]
/// * [testId]
/// * [unresolved]
/// * [version]
@BuiltValue()
abstract class DependencyGraphResponse
    implements Built<DependencyGraphResponse, DependencyGraphResponseBuilder> {
  @BuiltValueField(wireName: r'confirmed_at')
  DateTime? get confirmedAt;

  @BuiltValueField(wireName: r'created_at')
  DateTime get createdAt;

  @BuiltValueField(wireName: r'edges')
  BuiltList<DependencyEdgeModel> get edges;

  @BuiltValueField(wireName: r'id')
  String get id;

  @BuiltValueField(wireName: r'layers')
  BuiltList<BuiltList<String>> get layers;

  @BuiltValueField(wireName: r'question_ids')
  BuiltList<String> get questionIds;

  @BuiltValueField(wireName: r'status')
  String get status;

  @BuiltValueField(wireName: r'test_id')
  String get testId;

  @BuiltValueField(wireName: r'unresolved')
  BuiltList<UnresolvedQuestionModel> get unresolved;

  @BuiltValueField(wireName: r'version')
  int get version;

  DependencyGraphResponse._();

  factory DependencyGraphResponse(
          [void updates(DependencyGraphResponseBuilder b)]) =
      _$DependencyGraphResponse;

  @BuiltValueHook(initializeBuilder: true)
  static void _defaults(DependencyGraphResponseBuilder b) => b;

  @BuiltValueSerializer(custom: true)
  static Serializer<DependencyGraphResponse> get serializer =>
      _$DependencyGraphResponseSerializer();
}

class _$DependencyGraphResponseSerializer
    implements PrimitiveSerializer<DependencyGraphResponse> {
  @override
  final Iterable<Type> types = const [
    DependencyGraphResponse,
    _$DependencyGraphResponse
  ];

  @override
  final String wireName = r'DependencyGraphResponse';

  Iterable<Object?> _serializeProperties(
    Serializers serializers,
    DependencyGraphResponse object, {
    FullType specifiedType = FullType.unspecified,
  }) sync* {
    if (object.confirmedAt != null) {
      yield r'confirmed_at';
      yield serializers.serialize(
        object.confirmedAt,
        specifiedType: const FullType.nullable(DateTime),
      );
    }
    yield r'created_at';
    yield serializers.serialize(
      object.createdAt,
      specifiedType: const FullType(DateTime),
    );
    yield r'edges';
    yield serializers.serialize(
      object.edges,
      specifiedType: const FullType(BuiltList, [FullType(DependencyEdgeModel)]),
    );
    yield r'id';
    yield serializers.serialize(
      object.id,
      specifiedType: const FullType(String),
    );
    yield r'layers';
    yield serializers.serialize(
      object.layers,
      specifiedType: const FullType(BuiltList, [
        FullType(BuiltList, [FullType(String)])
      ]),
    );
    yield r'question_ids';
    yield serializers.serialize(
      object.questionIds,
      specifiedType: const FullType(BuiltList, [FullType(String)]),
    );
    yield r'status';
    yield serializers.serialize(
      object.status,
      specifiedType: const FullType(String),
    );
    yield r'test_id';
    yield serializers.serialize(
      object.testId,
      specifiedType: const FullType(String),
    );
    yield r'unresolved';
    yield serializers.serialize(
      object.unresolved,
      specifiedType:
          const FullType(BuiltList, [FullType(UnresolvedQuestionModel)]),
    );
    yield r'version';
    yield serializers.serialize(
      object.version,
      specifiedType: const FullType(int),
    );
  }

  @override
  Object serialize(
    Serializers serializers,
    DependencyGraphResponse object, {
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
    required DependencyGraphResponseBuilder result,
    required List<Object?> unhandled,
  }) {
    for (var i = 0; i < serializedList.length; i += 2) {
      final key = serializedList[i] as String;
      final value = serializedList[i + 1];
      switch (key) {
        case r'confirmed_at':
          final valueDes = serializers.deserialize(
            value,
            specifiedType: const FullType.nullable(DateTime),
          ) as DateTime?;
          if (valueDes == null) continue;
          result.confirmedAt = valueDes;
          break;
        case r'created_at':
          final valueDes = serializers.deserialize(
            value,
            specifiedType: const FullType(DateTime),
          ) as DateTime;
          result.createdAt = valueDes;
          break;
        case r'edges':
          final valueDes = serializers.deserialize(
            value,
            specifiedType:
                const FullType(BuiltList, [FullType(DependencyEdgeModel)]),
          ) as BuiltList<DependencyEdgeModel>;
          result.edges.replace(valueDes);
          break;
        case r'id':
          final valueDes = serializers.deserialize(
            value,
            specifiedType: const FullType(String),
          ) as String;
          result.id = valueDes;
          break;
        case r'layers':
          final valueDes = serializers.deserialize(
            value,
            specifiedType: const FullType(BuiltList, [
              FullType(BuiltList, [FullType(String)])
            ]),
          ) as BuiltList<BuiltList<String>>;
          result.layers.replace(valueDes);
          break;
        case r'question_ids':
          final valueDes = serializers.deserialize(
            value,
            specifiedType: const FullType(BuiltList, [FullType(String)]),
          ) as BuiltList<String>;
          result.questionIds.replace(valueDes);
          break;
        case r'status':
          final valueDes = serializers.deserialize(
            value,
            specifiedType: const FullType(String),
          ) as String;
          result.status = valueDes;
          break;
        case r'test_id':
          final valueDes = serializers.deserialize(
            value,
            specifiedType: const FullType(String),
          ) as String;
          result.testId = valueDes;
          break;
        case r'unresolved':
          final valueDes = serializers.deserialize(
            value,
            specifiedType:
                const FullType(BuiltList, [FullType(UnresolvedQuestionModel)]),
          ) as BuiltList<UnresolvedQuestionModel>;
          result.unresolved.replace(valueDes);
          break;
        case r'version':
          final valueDes = serializers.deserialize(
            value,
            specifiedType: const FullType(int),
          ) as int;
          result.version = valueDes;
          break;
        default:
          unhandled.add(key);
          unhandled.add(value);
          break;
      }
    }
  }

  @override
  DependencyGraphResponse deserialize(
    Serializers serializers,
    Object serialized, {
    FullType specifiedType = FullType.unspecified,
  }) {
    final result = DependencyGraphResponseBuilder();
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
