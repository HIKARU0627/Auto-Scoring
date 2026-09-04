//
// AUTO-GENERATED FILE, DO NOT MODIFY!
//

// ignore_for_file: unused_element
import 'package:built_value/built_value.dart';
import 'package:built_value/serializer.dart';

part 'score_response.g.dart';

/// ScoreResponse
///
/// Properties:
/// * [awarded]
/// * [key]
/// * [maximum]
/// * [ratio]
@BuiltValue()
abstract class ScoreResponse
    implements Built<ScoreResponse, ScoreResponseBuilder> {
  @BuiltValueField(wireName: r'awarded')
  int get awarded;

  @BuiltValueField(wireName: r'key')
  String get key;

  @BuiltValueField(wireName: r'maximum')
  int get maximum;

  @BuiltValueField(wireName: r'ratio')
  num get ratio;

  ScoreResponse._();

  factory ScoreResponse([void updates(ScoreResponseBuilder b)]) =
      _$ScoreResponse;

  @BuiltValueHook(initializeBuilder: true)
  static void _defaults(ScoreResponseBuilder b) => b;

  @BuiltValueSerializer(custom: true)
  static Serializer<ScoreResponse> get serializer =>
      _$ScoreResponseSerializer();
}

class _$ScoreResponseSerializer implements PrimitiveSerializer<ScoreResponse> {
  @override
  final Iterable<Type> types = const [ScoreResponse, _$ScoreResponse];

  @override
  final String wireName = r'ScoreResponse';

  Iterable<Object?> _serializeProperties(
    Serializers serializers,
    ScoreResponse object, {
    FullType specifiedType = FullType.unspecified,
  }) sync* {
    yield r'awarded';
    yield serializers.serialize(
      object.awarded,
      specifiedType: const FullType(int),
    );
    yield r'key';
    yield serializers.serialize(
      object.key,
      specifiedType: const FullType(String),
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
    ScoreResponse object, {
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
    required ScoreResponseBuilder result,
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
        case r'key':
          final valueDes = serializers.deserialize(
            value,
            specifiedType: const FullType(String),
          ) as String;
          result.key = valueDes;
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
  ScoreResponse deserialize(
    Serializers serializers,
    Object serialized, {
    FullType specifiedType = FullType.unspecified,
  }) {
    final result = ScoreResponseBuilder();
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
