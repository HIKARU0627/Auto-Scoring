//
// AUTO-GENERATED FILE, DO NOT MODIFY!
//

// ignore_for_file: unused_element
import 'package:built_collection/built_collection.dart';
import 'package:auto_scoring_api/src/model/question_text_override.dart';
import 'package:built_value/built_value.dart';
import 'package:built_value/serializer.dart';

part 'analyze_request.g.dart';

/// AnalyzeRequest
///
/// Properties:
/// * [overrides]
@BuiltValue()
abstract class AnalyzeRequest
    implements Built<AnalyzeRequest, AnalyzeRequestBuilder> {
  @BuiltValueField(wireName: r'overrides')
  BuiltList<QuestionTextOverride>? get overrides;

  AnalyzeRequest._();

  factory AnalyzeRequest([void updates(AnalyzeRequestBuilder b)]) =
      _$AnalyzeRequest;

  @BuiltValueHook(initializeBuilder: true)
  static void _defaults(AnalyzeRequestBuilder b) => b;

  @BuiltValueSerializer(custom: true)
  static Serializer<AnalyzeRequest> get serializer =>
      _$AnalyzeRequestSerializer();
}

class _$AnalyzeRequestSerializer
    implements PrimitiveSerializer<AnalyzeRequest> {
  @override
  final Iterable<Type> types = const [AnalyzeRequest, _$AnalyzeRequest];

  @override
  final String wireName = r'AnalyzeRequest';

  Iterable<Object?> _serializeProperties(
    Serializers serializers,
    AnalyzeRequest object, {
    FullType specifiedType = FullType.unspecified,
  }) sync* {
    if (object.overrides != null) {
      yield r'overrides';
      yield serializers.serialize(
        object.overrides,
        specifiedType:
            const FullType(BuiltList, [FullType(QuestionTextOverride)]),
      );
    }
  }

  @override
  Object serialize(
    Serializers serializers,
    AnalyzeRequest object, {
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
    required AnalyzeRequestBuilder result,
    required List<Object?> unhandled,
  }) {
    for (var i = 0; i < serializedList.length; i += 2) {
      final key = serializedList[i] as String;
      final value = serializedList[i + 1];
      switch (key) {
        case r'overrides':
          final valueDes = serializers.deserialize(
            value,
            specifiedType: const FullType.nullable(
                BuiltList, [FullType(QuestionTextOverride)]),
          ) as BuiltList<QuestionTextOverride>?;
          if (valueDes == null) continue;
          result.overrides.replace(valueDes);
          break;
        default:
          unhandled.add(key);
          unhandled.add(value);
          break;
      }
    }
  }

  @override
  AnalyzeRequest deserialize(
    Serializers serializers,
    Object serialized, {
    FullType specifiedType = FullType.unspecified,
  }) {
    final result = AnalyzeRequestBuilder();
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
