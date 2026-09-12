//
// AUTO-GENERATED FILE, DO NOT MODIFY!
//

// ignore_for_file: unused_element
import 'package:built_collection/built_collection.dart';
import 'package:built_value/built_value.dart';
import 'package:built_value/serializer.dart';

part 'scoring_targets_response.g.dart';

/// ScoringTargetsResponse
///
/// Properties:
/// * [questionIds]
@BuiltValue()
abstract class ScoringTargetsResponse
    implements Built<ScoringTargetsResponse, ScoringTargetsResponseBuilder> {
  @BuiltValueField(wireName: r'question_ids')
  BuiltList<String> get questionIds;

  ScoringTargetsResponse._();

  factory ScoringTargetsResponse(
          [void updates(ScoringTargetsResponseBuilder b)]) =
      _$ScoringTargetsResponse;

  @BuiltValueHook(initializeBuilder: true)
  static void _defaults(ScoringTargetsResponseBuilder b) => b;

  @BuiltValueSerializer(custom: true)
  static Serializer<ScoringTargetsResponse> get serializer =>
      _$ScoringTargetsResponseSerializer();
}

class _$ScoringTargetsResponseSerializer
    implements PrimitiveSerializer<ScoringTargetsResponse> {
  @override
  final Iterable<Type> types = const [
    ScoringTargetsResponse,
    _$ScoringTargetsResponse
  ];

  @override
  final String wireName = r'ScoringTargetsResponse';

  Iterable<Object?> _serializeProperties(
    Serializers serializers,
    ScoringTargetsResponse object, {
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
    ScoringTargetsResponse object, {
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
    required ScoringTargetsResponseBuilder result,
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
  ScoringTargetsResponse deserialize(
    Serializers serializers,
    Object serialized, {
    FullType specifiedType = FullType.unspecified,
  }) {
    final result = ScoringTargetsResponseBuilder();
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
