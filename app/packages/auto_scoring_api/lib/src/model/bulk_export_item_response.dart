//
// AUTO-GENERATED FILE, DO NOT MODIFY!
//

// ignore_for_file: unused_element
import 'package:auto_scoring_api/src/model/export_response.dart';
import 'package:built_collection/built_collection.dart';
import 'package:auto_scoring_api/src/model/bulk_export_item_status.dart';
import 'package:auto_scoring_api/src/model/export_refusal_reason.dart';
import 'package:built_value/built_value.dart';
import 'package:built_value/serializer.dart';

part 'bulk_export_item_response.g.dart';

/// One submission's outcome in a bulk export.
///
/// Properties:
/// * [export_]
/// * [jobId]
/// * [originalFilename]
/// * [refusalCode]
/// * [refusalQuestionIds]
/// * [status]
/// * [submissionId]
@BuiltValue()
abstract class BulkExportItemResponse
    implements Built<BulkExportItemResponse, BulkExportItemResponseBuilder> {
  @BuiltValueField(wireName: r'export')
  ExportResponse? get export_;

  @BuiltValueField(wireName: r'job_id')
  String? get jobId;

  @BuiltValueField(wireName: r'original_filename')
  String? get originalFilename;

  @BuiltValueField(wireName: r'refusal_code')
  ExportRefusalReason? get refusalCode;
  // enum refusalCodeEnum {  unconfirmed_questions,  no_room_for_score,  };

  @BuiltValueField(wireName: r'refusal_question_ids')
  BuiltList<String>? get refusalQuestionIds;

  @BuiltValueField(wireName: r'status')
  BulkExportItemStatus get status;
  // enum statusEnum {  queued,  reused,  refused,  };

  @BuiltValueField(wireName: r'submission_id')
  String get submissionId;

  BulkExportItemResponse._();

  factory BulkExportItemResponse(
          [void updates(BulkExportItemResponseBuilder b)]) =
      _$BulkExportItemResponse;

  @BuiltValueHook(initializeBuilder: true)
  static void _defaults(BulkExportItemResponseBuilder b) => b;

  @BuiltValueSerializer(custom: true)
  static Serializer<BulkExportItemResponse> get serializer =>
      _$BulkExportItemResponseSerializer();
}

class _$BulkExportItemResponseSerializer
    implements PrimitiveSerializer<BulkExportItemResponse> {
  @override
  final Iterable<Type> types = const [
    BulkExportItemResponse,
    _$BulkExportItemResponse
  ];

  @override
  final String wireName = r'BulkExportItemResponse';

  Iterable<Object?> _serializeProperties(
    Serializers serializers,
    BulkExportItemResponse object, {
    FullType specifiedType = FullType.unspecified,
  }) sync* {
    if (object.export_ != null) {
      yield r'export';
      yield serializers.serialize(
        object.export_,
        specifiedType: const FullType.nullable(ExportResponse),
      );
    }
    if (object.jobId != null) {
      yield r'job_id';
      yield serializers.serialize(
        object.jobId,
        specifiedType: const FullType.nullable(String),
      );
    }
    if (object.originalFilename != null) {
      yield r'original_filename';
      yield serializers.serialize(
        object.originalFilename,
        specifiedType: const FullType.nullable(String),
      );
    }
    if (object.refusalCode != null) {
      yield r'refusal_code';
      yield serializers.serialize(
        object.refusalCode,
        specifiedType: const FullType.nullable(ExportRefusalReason),
      );
    }
    if (object.refusalQuestionIds != null) {
      yield r'refusal_question_ids';
      yield serializers.serialize(
        object.refusalQuestionIds,
        specifiedType: const FullType(BuiltList, [FullType(String)]),
      );
    }
    yield r'status';
    yield serializers.serialize(
      object.status,
      specifiedType: const FullType(BulkExportItemStatus),
    );
    yield r'submission_id';
    yield serializers.serialize(
      object.submissionId,
      specifiedType: const FullType(String),
    );
  }

  @override
  Object serialize(
    Serializers serializers,
    BulkExportItemResponse object, {
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
    required BulkExportItemResponseBuilder result,
    required List<Object?> unhandled,
  }) {
    for (var i = 0; i < serializedList.length; i += 2) {
      final key = serializedList[i] as String;
      final value = serializedList[i + 1];
      switch (key) {
        case r'export':
          final valueDes = serializers.deserialize(
            value,
            specifiedType: const FullType.nullable(ExportResponse),
          ) as ExportResponse?;
          if (valueDes == null) continue;
          result.export_.replace(valueDes);
          break;
        case r'job_id':
          final valueDes = serializers.deserialize(
            value,
            specifiedType: const FullType.nullable(String),
          ) as String?;
          if (valueDes == null) continue;
          result.jobId = valueDes;
          break;
        case r'original_filename':
          final valueDes = serializers.deserialize(
            value,
            specifiedType: const FullType.nullable(String),
          ) as String?;
          if (valueDes == null) continue;
          result.originalFilename = valueDes;
          break;
        case r'refusal_code':
          final valueDes = serializers.deserialize(
            value,
            specifiedType: const FullType.nullable(ExportRefusalReason),
          ) as ExportRefusalReason?;
          if (valueDes == null) continue;
          result.refusalCode = valueDes;
          break;
        case r'refusal_question_ids':
          final valueDes = serializers.deserialize(
            value,
            specifiedType:
                const FullType.nullable(BuiltList, [FullType(String)]),
          ) as BuiltList<String>?;
          if (valueDes == null) continue;
          result.refusalQuestionIds.replace(valueDes);
          break;
        case r'status':
          final valueDes = serializers.deserialize(
            value,
            specifiedType: const FullType(BulkExportItemStatus),
          ) as BulkExportItemStatus;
          result.status = valueDes;
          break;
        case r'submission_id':
          final valueDes = serializers.deserialize(
            value,
            specifiedType: const FullType(String),
          ) as String;
          result.submissionId = valueDes;
          break;
        default:
          unhandled.add(key);
          unhandled.add(value);
          break;
      }
    }
  }

  @override
  BulkExportItemResponse deserialize(
    Serializers serializers,
    Object serialized, {
    FullType specifiedType = FullType.unspecified,
  }) {
    final result = BulkExportItemResponseBuilder();
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
