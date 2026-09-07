//
// AUTO-GENERATED FILE, DO NOT MODIFY!
//

// ignore_for_file: unused_element
import 'package:auto_scoring_api/src/model/export_response.dart';
import 'package:built_value/built_value.dart';
import 'package:built_value/serializer.dart';

part 'export_request_response.g.dart';

/// Result of ``POST .../export``: `decision` is one of `domain.pdf_export.ReexportDecision`'s values.  ``job_id`` is set (and the HTTP status is 202) for ``accept_new``/``accept_new_superseding`` -- a fresh `Job` was queued; poll it via `api.jobs_router`. ``export`` is set (status 200) for ``reuse_existing`` -- nothing was queued, the existing export already reflects the current review state.
///
/// Properties:
/// * [decision]
/// * [export_]
/// * [jobId]
@BuiltValue()
abstract class ExportRequestResponse
    implements Built<ExportRequestResponse, ExportRequestResponseBuilder> {
  @BuiltValueField(wireName: r'decision')
  String get decision;

  @BuiltValueField(wireName: r'export')
  ExportResponse? get export_;

  @BuiltValueField(wireName: r'job_id')
  String? get jobId;

  ExportRequestResponse._();

  factory ExportRequestResponse(
      [void updates(ExportRequestResponseBuilder b)]) = _$ExportRequestResponse;

  @BuiltValueHook(initializeBuilder: true)
  static void _defaults(ExportRequestResponseBuilder b) => b;

  @BuiltValueSerializer(custom: true)
  static Serializer<ExportRequestResponse> get serializer =>
      _$ExportRequestResponseSerializer();
}

class _$ExportRequestResponseSerializer
    implements PrimitiveSerializer<ExportRequestResponse> {
  @override
  final Iterable<Type> types = const [
    ExportRequestResponse,
    _$ExportRequestResponse
  ];

  @override
  final String wireName = r'ExportRequestResponse';

  Iterable<Object?> _serializeProperties(
    Serializers serializers,
    ExportRequestResponse object, {
    FullType specifiedType = FullType.unspecified,
  }) sync* {
    yield r'decision';
    yield serializers.serialize(
      object.decision,
      specifiedType: const FullType(String),
    );
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
  }

  @override
  Object serialize(
    Serializers serializers,
    ExportRequestResponse object, {
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
    required ExportRequestResponseBuilder result,
    required List<Object?> unhandled,
  }) {
    for (var i = 0; i < serializedList.length; i += 2) {
      final key = serializedList[i] as String;
      final value = serializedList[i + 1];
      switch (key) {
        case r'decision':
          final valueDes = serializers.deserialize(
            value,
            specifiedType: const FullType(String),
          ) as String;
          result.decision = valueDes;
          break;
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
        default:
          unhandled.add(key);
          unhandled.add(value);
          break;
      }
    }
  }

  @override
  ExportRequestResponse deserialize(
    Serializers serializers,
    Object serialized, {
    FullType specifiedType = FullType.unspecified,
  }) {
    final result = ExportRequestResponseBuilder();
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
