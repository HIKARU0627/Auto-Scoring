//
// AUTO-GENERATED FILE, DO NOT MODIFY!
//

// ignore_for_file: unused_element
import 'package:built_collection/built_collection.dart';
import 'package:auto_scoring_api/src/model/dependency_edge_model.dart';
import 'package:built_value/built_value.dart';
import 'package:built_value/serializer.dart';

part 'confirm_request.g.dart';

/// ConfirmRequest
///
/// Properties:
/// * [edges]
/// * [version]
@BuiltValue()
abstract class ConfirmRequest
    implements Built<ConfirmRequest, ConfirmRequestBuilder> {
  @BuiltValueField(wireName: r'edges')
  BuiltList<DependencyEdgeModel> get edges;

  @BuiltValueField(wireName: r'version')
  int get version;

  ConfirmRequest._();

  factory ConfirmRequest([void updates(ConfirmRequestBuilder b)]) =
      _$ConfirmRequest;

  @BuiltValueHook(initializeBuilder: true)
  static void _defaults(ConfirmRequestBuilder b) => b;

  @BuiltValueSerializer(custom: true)
  static Serializer<ConfirmRequest> get serializer =>
      _$ConfirmRequestSerializer();
}

class _$ConfirmRequestSerializer
    implements PrimitiveSerializer<ConfirmRequest> {
  @override
  final Iterable<Type> types = const [ConfirmRequest, _$ConfirmRequest];

  @override
  final String wireName = r'ConfirmRequest';

  Iterable<Object?> _serializeProperties(
    Serializers serializers,
    ConfirmRequest object, {
    FullType specifiedType = FullType.unspecified,
  }) sync* {
    yield r'edges';
    yield serializers.serialize(
      object.edges,
      specifiedType: const FullType(BuiltList, [FullType(DependencyEdgeModel)]),
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
    ConfirmRequest object, {
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
    required ConfirmRequestBuilder result,
    required List<Object?> unhandled,
  }) {
    for (var i = 0; i < serializedList.length; i += 2) {
      final key = serializedList[i] as String;
      final value = serializedList[i + 1];
      switch (key) {
        case r'edges':
          final valueDes = serializers.deserialize(
            value,
            specifiedType:
                const FullType(BuiltList, [FullType(DependencyEdgeModel)]),
          ) as BuiltList<DependencyEdgeModel>;
          result.edges.replace(valueDes);
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
  ConfirmRequest deserialize(
    Serializers serializers,
    Object serialized, {
    FullType specifiedType = FullType.unspecified,
  }) {
    final result = ConfirmRequestBuilder();
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
