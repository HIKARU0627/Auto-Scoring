//
// AUTO-GENERATED FILE, DO NOT MODIFY!
//

// ignore_for_file: unused_element
import 'package:built_value/built_value.dart';
import 'package:built_value/serializer.dart';

part 'criteria_estimate_response.g.dart';

/// What one extraction would send, and what it would cost -- answered *before* anything is sent (code review P2-2).  Pressing 抽出 uploads every page of the criteria PDF to a paid provider, and pressing it again does it again. A reviewer is entitled to see the size of that before it happens, the same way Issue #101's intake screen shows its own call count and estimate.
///
/// Properties:
/// * [estimatedCost]
/// * [maxPages]
/// * [pageCount]
/// * [unitCost]
@BuiltValue()
abstract class CriteriaEstimateResponse
    implements
        Built<CriteriaEstimateResponse, CriteriaEstimateResponseBuilder> {
  @BuiltValueField(wireName: r'estimated_cost')
  num? get estimatedCost;

  @BuiltValueField(wireName: r'max_pages')
  int get maxPages;

  @BuiltValueField(wireName: r'page_count')
  int get pageCount;

  @BuiltValueField(wireName: r'unit_cost')
  num? get unitCost;

  CriteriaEstimateResponse._();

  factory CriteriaEstimateResponse(
          [void updates(CriteriaEstimateResponseBuilder b)]) =
      _$CriteriaEstimateResponse;

  @BuiltValueHook(initializeBuilder: true)
  static void _defaults(CriteriaEstimateResponseBuilder b) => b;

  @BuiltValueSerializer(custom: true)
  static Serializer<CriteriaEstimateResponse> get serializer =>
      _$CriteriaEstimateResponseSerializer();
}

class _$CriteriaEstimateResponseSerializer
    implements PrimitiveSerializer<CriteriaEstimateResponse> {
  @override
  final Iterable<Type> types = const [
    CriteriaEstimateResponse,
    _$CriteriaEstimateResponse
  ];

  @override
  final String wireName = r'CriteriaEstimateResponse';

  Iterable<Object?> _serializeProperties(
    Serializers serializers,
    CriteriaEstimateResponse object, {
    FullType specifiedType = FullType.unspecified,
  }) sync* {
    if (object.estimatedCost != null) {
      yield r'estimated_cost';
      yield serializers.serialize(
        object.estimatedCost,
        specifiedType: const FullType.nullable(num),
      );
    }
    yield r'max_pages';
    yield serializers.serialize(
      object.maxPages,
      specifiedType: const FullType(int),
    );
    yield r'page_count';
    yield serializers.serialize(
      object.pageCount,
      specifiedType: const FullType(int),
    );
    if (object.unitCost != null) {
      yield r'unit_cost';
      yield serializers.serialize(
        object.unitCost,
        specifiedType: const FullType.nullable(num),
      );
    }
  }

  @override
  Object serialize(
    Serializers serializers,
    CriteriaEstimateResponse object, {
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
    required CriteriaEstimateResponseBuilder result,
    required List<Object?> unhandled,
  }) {
    for (var i = 0; i < serializedList.length; i += 2) {
      final key = serializedList[i] as String;
      final value = serializedList[i + 1];
      switch (key) {
        case r'estimated_cost':
          final valueDes = serializers.deserialize(
            value,
            specifiedType: const FullType.nullable(num),
          ) as num?;
          if (valueDes == null) continue;
          result.estimatedCost = valueDes;
          break;
        case r'max_pages':
          final valueDes = serializers.deserialize(
            value,
            specifiedType: const FullType(int),
          ) as int;
          result.maxPages = valueDes;
          break;
        case r'page_count':
          final valueDes = serializers.deserialize(
            value,
            specifiedType: const FullType(int),
          ) as int;
          result.pageCount = valueDes;
          break;
        case r'unit_cost':
          final valueDes = serializers.deserialize(
            value,
            specifiedType: const FullType.nullable(num),
          ) as num?;
          if (valueDes == null) continue;
          result.unitCost = valueDes;
          break;
        default:
          unhandled.add(key);
          unhandled.add(value);
          break;
      }
    }
  }

  @override
  CriteriaEstimateResponse deserialize(
    Serializers serializers,
    Object serialized, {
    FullType specifiedType = FullType.unspecified,
  }) {
    final result = CriteriaEstimateResponseBuilder();
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
