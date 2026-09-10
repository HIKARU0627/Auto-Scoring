//
// AUTO-GENERATED FILE, DO NOT MODIFY!
//

// ignore_for_file: unused_element
import 'package:built_collection/built_collection.dart';
import 'package:auto_scoring_api/src/model/bulk_export_item_response.dart';
import 'package:built_value/built_value.dart';
import 'package:built_value/serializer.dart';

part 'bulk_export_response.g.dart';

/// Every target's outcome, in the same order the test's submissions are listed in (`SubmissionRepository.list_for_test`) -- so the screen's progress list matches the queue screen's order.
///
/// Properties:
/// * [items]
/// * [testId]
@BuiltValue()
abstract class BulkExportResponse
    implements Built<BulkExportResponse, BulkExportResponseBuilder> {
  @BuiltValueField(wireName: r'items')
  BuiltList<BulkExportItemResponse> get items;

  @BuiltValueField(wireName: r'test_id')
  String get testId;

  BulkExportResponse._();

  factory BulkExportResponse([void updates(BulkExportResponseBuilder b)]) =
      _$BulkExportResponse;

  @BuiltValueHook(initializeBuilder: true)
  static void _defaults(BulkExportResponseBuilder b) => b;

  @BuiltValueSerializer(custom: true)
  static Serializer<BulkExportResponse> get serializer =>
      _$BulkExportResponseSerializer();
}

class _$BulkExportResponseSerializer
    implements PrimitiveSerializer<BulkExportResponse> {
  @override
  final Iterable<Type> types = const [BulkExportResponse, _$BulkExportResponse];

  @override
  final String wireName = r'BulkExportResponse';

  Iterable<Object?> _serializeProperties(
    Serializers serializers,
    BulkExportResponse object, {
    FullType specifiedType = FullType.unspecified,
  }) sync* {
    yield r'items';
    yield serializers.serialize(
      object.items,
      specifiedType:
          const FullType(BuiltList, [FullType(BulkExportItemResponse)]),
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
    BulkExportResponse object, {
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
    required BulkExportResponseBuilder result,
    required List<Object?> unhandled,
  }) {
    for (var i = 0; i < serializedList.length; i += 2) {
      final key = serializedList[i] as String;
      final value = serializedList[i + 1];
      switch (key) {
        case r'items':
          final valueDes = serializers.deserialize(
            value,
            specifiedType:
                const FullType(BuiltList, [FullType(BulkExportItemResponse)]),
          ) as BuiltList<BulkExportItemResponse>;
          result.items.replace(valueDes);
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
  BulkExportResponse deserialize(
    Serializers serializers,
    Object serialized, {
    FullType specifiedType = FullType.unspecified,
  }) {
    final result = BulkExportResponseBuilder();
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
