//
// AUTO-GENERATED FILE, DO NOT MODIFY!
//

// ignore_for_file: unused_element
import 'package:built_value/built_value.dart';
import 'package:built_value/serializer.dart';

part 'answer_layout_response.g.dart';

/// The reference answer sheet this test's answer areas are laid out against (Issue #105), and whether detection can run here at all.
///
/// Properties:
/// * [detectionAvailable]
/// * [detectionUnavailableReason]
/// * [pageCount]
/// * [testId]
@BuiltValue()
abstract class AnswerLayoutResponse
    implements Built<AnswerLayoutResponse, AnswerLayoutResponseBuilder> {
  @BuiltValueField(wireName: r'detection_available')
  bool get detectionAvailable;

  @BuiltValueField(wireName: r'detection_unavailable_reason')
  String? get detectionUnavailableReason;

  @BuiltValueField(wireName: r'page_count')
  int? get pageCount;

  @BuiltValueField(wireName: r'test_id')
  String get testId;

  AnswerLayoutResponse._();

  factory AnswerLayoutResponse([void updates(AnswerLayoutResponseBuilder b)]) =
      _$AnswerLayoutResponse;

  @BuiltValueHook(initializeBuilder: true)
  static void _defaults(AnswerLayoutResponseBuilder b) => b;

  @BuiltValueSerializer(custom: true)
  static Serializer<AnswerLayoutResponse> get serializer =>
      _$AnswerLayoutResponseSerializer();
}

class _$AnswerLayoutResponseSerializer
    implements PrimitiveSerializer<AnswerLayoutResponse> {
  @override
  final Iterable<Type> types = const [
    AnswerLayoutResponse,
    _$AnswerLayoutResponse
  ];

  @override
  final String wireName = r'AnswerLayoutResponse';

  Iterable<Object?> _serializeProperties(
    Serializers serializers,
    AnswerLayoutResponse object, {
    FullType specifiedType = FullType.unspecified,
  }) sync* {
    yield r'detection_available';
    yield serializers.serialize(
      object.detectionAvailable,
      specifiedType: const FullType(bool),
    );
    if (object.detectionUnavailableReason != null) {
      yield r'detection_unavailable_reason';
      yield serializers.serialize(
        object.detectionUnavailableReason,
        specifiedType: const FullType.nullable(String),
      );
    }
    yield r'page_count';
    yield object.pageCount == null
        ? null
        : serializers.serialize(
            object.pageCount,
            specifiedType: const FullType.nullable(int),
          );
    yield r'test_id';
    yield serializers.serialize(
      object.testId,
      specifiedType: const FullType(String),
    );
  }

  @override
  Object serialize(
    Serializers serializers,
    AnswerLayoutResponse object, {
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
    required AnswerLayoutResponseBuilder result,
    required List<Object?> unhandled,
  }) {
    for (var i = 0; i < serializedList.length; i += 2) {
      final key = serializedList[i] as String;
      final value = serializedList[i + 1];
      switch (key) {
        case r'detection_available':
          final valueDes = serializers.deserialize(
            value,
            specifiedType: const FullType(bool),
          ) as bool;
          result.detectionAvailable = valueDes;
          break;
        case r'detection_unavailable_reason':
          final valueDes = serializers.deserialize(
            value,
            specifiedType: const FullType.nullable(String),
          ) as String?;
          if (valueDes == null) continue;
          result.detectionUnavailableReason = valueDes;
          break;
        case r'page_count':
          final valueDes = serializers.deserialize(
            value,
            specifiedType: const FullType.nullable(int),
          ) as int?;
          if (valueDes == null) continue;
          result.pageCount = valueDes;
          break;
        case r'test_id':
          final valueDes = serializers.deserialize(
            value,
            specifiedType: const FullType(String),
          ) as String;
          result.testId = valueDes;
          break;
        default:
          unhandled.add(key);
          unhandled.add(value);
          break;
      }
    }
  }

  @override
  AnswerLayoutResponse deserialize(
    Serializers serializers,
    Object serialized, {
    FullType specifiedType = FullType.unspecified,
  }) {
    final result = AnswerLayoutResponseBuilder();
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
