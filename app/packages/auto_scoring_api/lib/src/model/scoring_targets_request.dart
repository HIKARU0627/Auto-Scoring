//
// AUTO-GENERATED FILE, DO NOT MODIFY!
//

// ignore_for_file: unused_element
import 'package:built_collection/built_collection.dart';
import 'package:built_value/built_value.dart';
import 'package:built_value/serializer.dart';

part 'scoring_targets_request.g.dart';

/// ScoringTargetsRequest
///
/// Properties:
/// * [questionIds]
@BuiltValue()
abstract class ScoringTargetsRequest
    implements Built<ScoringTargetsRequest, ScoringTargetsRequestBuilder> {
  @BuiltValueField(wireName: r'question_ids')
  BuiltList<String> get questionIds;

  ScoringTargetsRequest._();

  factory ScoringTargetsRequest(
      [void updates(ScoringTargetsRequestBuilder b)]) = _$ScoringTargetsRequest;

  @BuiltValueHook(initializeBuilder: true)
  static void _defaults(ScoringTargetsRequestBuilder b) => b;

  @BuiltValueSerializer(custom: true)
  static Serializer<ScoringTargetsRequest> get serializer =>
      _$ScoringTargetsRequestSerializer();
}

class _$ScoringTargetsRequestSerializer
    implements PrimitiveSerializer<ScoringTargetsRequest> {
  @override
  final Iterable<Type> types = const [
    ScoringTargetsRequest,
    _$ScoringTargetsRequest
  ];

  @override
  final String wireName = r'ScoringTargetsRequest';

  Iterable<Object?> _serializeProperties(
    Serializers serializers,
    ScoringTargetsRequest object, {
    FullType specifiedType = FullType.unspecified,
  }) sync* {
    yield r'question_ids';
    yield serializers.serialize(
      object.questionIds,
      specifiedType: const FullType(BuiltList, [FullType(String)]),
    );
  }

  @override
  Object serialize(
    Serializers serializers,
    ScoringTargetsRequest object, {
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
    required ScoringTargetsRequestBuilder result,
    required List<Object?> unhandled,
  }) {
    for (var i = 0; i < serializedList.length; i += 2) {
      final key = serializedList[i] as String;
      final value = serializedList[i + 1];
      switch (key) {
        case r'question_ids':
          final valueDes = serializers.deserialize(
            value,
            specifiedType: const FullType(BuiltList, [FullType(String)]),
          ) as BuiltList<String>;
          result.questionIds.replace(valueDes);
          break;
        default:
          unhandled.add(key);
          unhandled.add(value);
          break;
      }
    }
  }

  @override
  ScoringTargetsRequest deserialize(
    Serializers serializers,
    Object serialized, {
    FullType specifiedType = FullType.unspecified,
  }) {
    final result = ScoringTargetsRequestBuilder();
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
