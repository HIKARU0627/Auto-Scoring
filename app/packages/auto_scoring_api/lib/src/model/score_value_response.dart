//
// AUTO-GENERATED FILE, DO NOT MODIFY!
//

// ignore_for_file: unused_element
import 'package:built_value/built_value.dart';
import 'package:built_value/serializer.dart';

part 'score_value_response.g.dart';

/// ScoreValueResponse
///
/// Properties:
/// * [awarded]
/// * [maximum]
/// * [ratio]
@BuiltValue()
abstract class ScoreValueResponse
    implements Built<ScoreValueResponse, ScoreValueResponseBuilder> {
  @BuiltValueField(wireName: r'awarded')
  int get awarded;

  @BuiltValueField(wireName: r'maximum')
  int get maximum;

  @BuiltValueField(wireName: r'ratio')
  num get ratio;

  ScoreValueResponse._();

  factory ScoreValueResponse([void updates(ScoreValueResponseBuilder b)]) =
      _$ScoreValueResponse;

  @BuiltValueHook(initializeBuilder: true)
  static void _defaults(ScoreValueResponseBuilder b) => b;

  @BuiltValueSerializer(custom: true)
  static Serializer<ScoreValueResponse> get serializer =>
      _$ScoreValueResponseSerializer();
}

class _$ScoreValueResponseSerializer
    implements PrimitiveSerializer<ScoreValueResponse> {
  @override
  final Iterable<Type> types = const [ScoreValueResponse, _$ScoreValueResponse];

  @override
  final String wireName = r'ScoreValueResponse';

  Iterable<Object?> _serializeProperties(
    Serializers serializers,
    ScoreValueResponse object, {
    FullType specifiedType = FullType.unspecified,
  }) sync* {
    yield r'awarded';
    yield serializers.serialize(
      object.awarded,
      specifiedType: const FullType(int),
    );
    yield r'maximum';
    yield serializers.serialize(
      object.maximum,
      specifiedType: const FullType(int),
    );
    yield r'ratio';
    yield serializers.serialize(
      object.ratio,
      specifiedType: const FullType(num),
    );
  }

  @override
  Object serialize(
    Serializers serializers,
    ScoreValueResponse object, {
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
    required ScoreValueResponseBuilder result,
    required List<Object?> unhandled,
  }) {
    for (var i = 0; i < serializedList.length; i += 2) {
      final key = serializedList[i] as String;
      final value = serializedList[i + 1];
      switch (key) {
        case r'awarded':
          final valueDes = serializers.deserialize(
            value,
            specifiedType: const FullType(int),
          ) as int;
          result.awarded = valueDes;
          break;
        case r'maximum':
          final valueDes = serializers.deserialize(
            value,
            specifiedType: const FullType(int),
          ) as int;
          result.maximum = valueDes;
          break;
        case r'ratio':
          final valueDes = serializers.deserialize(
            value,
            specifiedType: const FullType(num),
          ) as num;
          result.ratio = valueDes;
          break;
        default:
          unhandled.add(key);
          unhandled.add(value);
          break;
      }
    }
  }

  @override
  ScoreValueResponse deserialize(
    Serializers serializers,
    Object serialized, {
    FullType specifiedType = FullType.unspecified,
  }) {
    final result = ScoreValueResponseBuilder();
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
