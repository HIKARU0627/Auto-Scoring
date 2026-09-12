//
// AUTO-GENERATED FILE, DO NOT MODIFY!
//

// ignore_for_file: unused_element
import 'package:auto_scoring_api/src/model/normalized_rect_response.dart';
import 'package:built_value/built_value.dart';
import 'package:built_value/serializer.dart';

part 'question_score_placement_response.g.dart';

/// Where this question's confirmed score is written on the exported sheet (Issue #406), so the review screen can draw the same score in the same place -- and can say *before* an export is attempted that this question has nowhere to put it.  ``target`` is `domain.pdf_export.ScorePlacementTarget`'s value: ``\"own\"`` (at `score_area`), ``\"margin\"`` (the page's fallback strip), or ``\"none\"`` (the export will refuse with ``no_room_for_score``). ``rect`` is the page-normalized destination for the first two and ``None`` for ``\"none\"``. It is produced by `domain.pdf_export.score_placements`, i.e. the same judgment the export gate and renderer use, never re-derived here or on the client.
///
/// Properties:
/// * [rect]
/// * [target]
@BuiltValue()
abstract class QuestionScorePlacementResponse
    implements
        Built<QuestionScorePlacementResponse,
            QuestionScorePlacementResponseBuilder> {
  @BuiltValueField(wireName: r'rect')
  NormalizedRectResponse? get rect;

  @BuiltValueField(wireName: r'target')
  String get target;

  QuestionScorePlacementResponse._();

  factory QuestionScorePlacementResponse(
          [void updates(QuestionScorePlacementResponseBuilder b)]) =
      _$QuestionScorePlacementResponse;

  @BuiltValueHook(initializeBuilder: true)
  static void _defaults(QuestionScorePlacementResponseBuilder b) => b;

  @BuiltValueSerializer(custom: true)
  static Serializer<QuestionScorePlacementResponse> get serializer =>
      _$QuestionScorePlacementResponseSerializer();
}

class _$QuestionScorePlacementResponseSerializer
    implements PrimitiveSerializer<QuestionScorePlacementResponse> {
  @override
  final Iterable<Type> types = const [
    QuestionScorePlacementResponse,
    _$QuestionScorePlacementResponse
  ];

  @override
  final String wireName = r'QuestionScorePlacementResponse';

  Iterable<Object?> _serializeProperties(
    Serializers serializers,
    QuestionScorePlacementResponse object, {
    FullType specifiedType = FullType.unspecified,
  }) sync* {
    if (object.rect != null) {
      yield r'rect';
      yield serializers.serialize(
        object.rect,
        specifiedType: const FullType.nullable(NormalizedRectResponse),
      );
    }
    yield r'target';
    yield serializers.serialize(
      object.target,
      specifiedType: const FullType(String),
    );
  }

  @override
  Object serialize(
    Serializers serializers,
    QuestionScorePlacementResponse object, {
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
    required QuestionScorePlacementResponseBuilder result,
    required List<Object?> unhandled,
  }) {
    for (var i = 0; i < serializedList.length; i += 2) {
      final key = serializedList[i] as String;
      final value = serializedList[i + 1];
      switch (key) {
        case r'rect':
          final valueDes = serializers.deserialize(
            value,
            specifiedType: const FullType.nullable(NormalizedRectResponse),
          ) as NormalizedRectResponse?;
          if (valueDes == null) continue;
          result.rect.replace(valueDes);
          break;
        case r'target':
          final valueDes = serializers.deserialize(
            value,
            specifiedType: const FullType(String),
          ) as String;
          result.target = valueDes;
          break;
        default:
          unhandled.add(key);
          unhandled.add(value);
          break;
      }
    }
  }

  @override
  QuestionScorePlacementResponse deserialize(
    Serializers serializers,
    Object serialized, {
    FullType specifiedType = FullType.unspecified,
  }) {
    final result = QuestionScorePlacementResponseBuilder();
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
