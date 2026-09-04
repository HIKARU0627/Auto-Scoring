//
// AUTO-GENERATED FILE, DO NOT MODIFY!
//

// ignore_for_file: unused_element
import 'package:built_value/built_value.dart';
import 'package:built_value/serializer.dart';

part 'score_request.g.dart';

/// ScoreRequest
///
/// Properties:
/// * [key]
/// * [maximum]
/// * [raw]
@BuiltValue()
abstract class ScoreRequest
    implements Built<ScoreRequest, ScoreRequestBuilder> {
  @BuiltValueField(wireName: r'key')
  String get key;

  @BuiltValueField(wireName: r'maximum')
  int get maximum;

  @BuiltValueField(wireName: r'raw')
  int get raw;

  ScoreRequest._();

  factory ScoreRequest([void updates(ScoreRequestBuilder b)]) = _$ScoreRequest;

  @BuiltValueHook(initializeBuilder: true)
  static void _defaults(ScoreRequestBuilder b) => b;

  @BuiltValueSerializer(custom: true)
  static Serializer<ScoreRequest> get serializer => _$ScoreRequestSerializer();
}

class _$ScoreRequestSerializer implements PrimitiveSerializer<ScoreRequest> {
  @override
  final Iterable<Type> types = const [ScoreRequest, _$ScoreRequest];

  @override
  final String wireName = r'ScoreRequest';

  Iterable<Object?> _serializeProperties(
    Serializers serializers,
    ScoreRequest object, {
    FullType specifiedType = FullType.unspecified,
  }) sync* {
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
    yield r'raw';
    yield serializers.serialize(
      object.raw,
      specifiedType: const FullType(int),
    );
  }

  @override
  Object serialize(
    Serializers serializers,
    ScoreRequest object, {
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
    required ScoreRequestBuilder result,
    required List<Object?> unhandled,
  }) {
    for (var i = 0; i < serializedList.length; i += 2) {
      final key = serializedList[i] as String;
      final value = serializedList[i + 1];
      switch (key) {
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
        case r'raw':
          final valueDes = serializers.deserialize(
            value,
            specifiedType: const FullType(int),
          ) as int;
          result.raw = valueDes;
          break;
        default:
          unhandled.add(key);
          unhandled.add(value);
          break;
      }
    }
  }

  @override
  ScoreRequest deserialize(
    Serializers serializers,
    Object serialized, {
    FullType specifiedType = FullType.unspecified,
  }) {
    final result = ScoreRequestBuilder();
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
