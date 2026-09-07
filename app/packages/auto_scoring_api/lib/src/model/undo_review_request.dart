//
// AUTO-GENERATED FILE, DO NOT MODIFY!
//

// ignore_for_file: unused_element
import 'package:built_value/built_value.dart';
import 'package:built_value/serializer.dart';

part 'undo_review_request.g.dart';

/// UndoReviewRequest
///
/// Properties:
/// * [expectedVersion]
@BuiltValue()
abstract class UndoReviewRequest
    implements Built<UndoReviewRequest, UndoReviewRequestBuilder> {
  @BuiltValueField(wireName: r'expected_version')
  int get expectedVersion;

  UndoReviewRequest._();

  factory UndoReviewRequest([void updates(UndoReviewRequestBuilder b)]) =
      _$UndoReviewRequest;

  @BuiltValueHook(initializeBuilder: true)
  static void _defaults(UndoReviewRequestBuilder b) => b;

  @BuiltValueSerializer(custom: true)
  static Serializer<UndoReviewRequest> get serializer =>
      _$UndoReviewRequestSerializer();
}

class _$UndoReviewRequestSerializer
    implements PrimitiveSerializer<UndoReviewRequest> {
  @override
  final Iterable<Type> types = const [UndoReviewRequest, _$UndoReviewRequest];

  @override
  final String wireName = r'UndoReviewRequest';

  Iterable<Object?> _serializeProperties(
    Serializers serializers,
    UndoReviewRequest object, {
    FullType specifiedType = FullType.unspecified,
  }) sync* {
    yield r'expected_version';
    yield serializers.serialize(
      object.expectedVersion,
      specifiedType: const FullType(int),
    );
  }

  @override
  Object serialize(
    Serializers serializers,
    UndoReviewRequest object, {
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
    required UndoReviewRequestBuilder result,
    required List<Object?> unhandled,
  }) {
    for (var i = 0; i < serializedList.length; i += 2) {
      final key = serializedList[i] as String;
      final value = serializedList[i + 1];
      switch (key) {
        case r'expected_version':
          final valueDes = serializers.deserialize(
            value,
            specifiedType: const FullType(int),
          ) as int;
          result.expectedVersion = valueDes;
          break;
        default:
          unhandled.add(key);
          unhandled.add(value);
          break;
      }
    }
  }

  @override
  UndoReviewRequest deserialize(
    Serializers serializers,
    Object serialized, {
    FullType specifiedType = FullType.unspecified,
  }) {
    final result = UndoReviewRequestBuilder();
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
