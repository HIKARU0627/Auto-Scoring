//
// AUTO-GENERATED FILE, DO NOT MODIFY!
//

// ignore_for_file: unused_element
import 'package:built_collection/built_collection.dart';
import 'package:built_value/built_value.dart';
import 'package:built_value/serializer.dart';

part 'bulk_export_request.g.dart';

/// ``submission_ids`` narrows the run to a subset of the test's submissions; omitted or ``null`` means every one of them.  This is the whole of \"失敗した分だけ再実行できる\" (Issue #142): the screen already holds the failed rows, so re-running them is the same call with a shorter list -- no server-side notion of \"a bulk run\" to persist, resume, or garbage-collect.  Ids that do not belong to ``test_id`` are not silently dropped: the request is refused (400), because a caller asking for a submission this test does not have is asking for something that will never happen, and quietly exporting a shorter list would look like success.
///
/// Properties:
/// * [submissionIds]
@BuiltValue()
abstract class BulkExportRequest
    implements Built<BulkExportRequest, BulkExportRequestBuilder> {
  @BuiltValueField(wireName: r'submission_ids')
  BuiltList<String>? get submissionIds;

  BulkExportRequest._();

  factory BulkExportRequest([void updates(BulkExportRequestBuilder b)]) =
      _$BulkExportRequest;

  @BuiltValueHook(initializeBuilder: true)
  static void _defaults(BulkExportRequestBuilder b) => b;

  @BuiltValueSerializer(custom: true)
  static Serializer<BulkExportRequest> get serializer =>
      _$BulkExportRequestSerializer();
}

class _$BulkExportRequestSerializer
    implements PrimitiveSerializer<BulkExportRequest> {
  @override
  final Iterable<Type> types = const [BulkExportRequest, _$BulkExportRequest];

  @override
  final String wireName = r'BulkExportRequest';

  Iterable<Object?> _serializeProperties(
    Serializers serializers,
    BulkExportRequest object, {
    FullType specifiedType = FullType.unspecified,
  }) sync* {
    if (object.submissionIds != null) {
      yield r'submission_ids';
      yield serializers.serialize(
        object.submissionIds,
        specifiedType: const FullType.nullable(BuiltList, [FullType(String)]),
      );
    }
  }

  @override
  Object serialize(
    Serializers serializers,
    BulkExportRequest object, {
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
    required BulkExportRequestBuilder result,
    required List<Object?> unhandled,
  }) {
    for (var i = 0; i < serializedList.length; i += 2) {
      final key = serializedList[i] as String;
      final value = serializedList[i + 1];
      switch (key) {
        case r'submission_ids':
          final valueDes = serializers.deserialize(
            value,
            specifiedType:
                const FullType.nullable(BuiltList, [FullType(String)]),
          ) as BuiltList<String>?;
          if (valueDes == null) continue;
          result.submissionIds.replace(valueDes);
          break;
        default:
          unhandled.add(key);
          unhandled.add(value);
          break;
      }
    }
  }

  @override
  BulkExportRequest deserialize(
    Serializers serializers,
    Object serialized, {
    FullType specifiedType = FullType.unspecified,
  }) {
    final result = BulkExportRequestBuilder();
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
