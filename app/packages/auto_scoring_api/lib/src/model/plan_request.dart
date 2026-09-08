//
// AUTO-GENERATED FILE, DO NOT MODIFY!
//

// ignore_for_file: unused_element
import 'package:auto_scoring_api/src/model/scanned_file_model.dart';
import 'package:built_collection/built_collection.dart';
import 'package:built_value/built_value.dart';
import 'package:built_value/serializer.dart';

part 'plan_request.g.dart';

/// PlanRequest
///
/// Properties:
/// * [files]
/// * [rootName]
/// * [templateId]
@BuiltValue()
abstract class PlanRequest implements Built<PlanRequest, PlanRequestBuilder> {
  @BuiltValueField(wireName: r'files')
  BuiltList<ScannedFileModel> get files;

  @BuiltValueField(wireName: r'root_name')
  String get rootName;

  @BuiltValueField(wireName: r'template_id')
  String get templateId;

  PlanRequest._();

  factory PlanRequest([void updates(PlanRequestBuilder b)]) = _$PlanRequest;

  @BuiltValueHook(initializeBuilder: true)
  static void _defaults(PlanRequestBuilder b) => b;

  @BuiltValueSerializer(custom: true)
  static Serializer<PlanRequest> get serializer => _$PlanRequestSerializer();
}

class _$PlanRequestSerializer implements PrimitiveSerializer<PlanRequest> {
  @override
  final Iterable<Type> types = const [PlanRequest, _$PlanRequest];

  @override
  final String wireName = r'PlanRequest';

  Iterable<Object?> _serializeProperties(
    Serializers serializers,
    PlanRequest object, {
    FullType specifiedType = FullType.unspecified,
  }) sync* {
    yield r'files';
    yield serializers.serialize(
      object.files,
      specifiedType: const FullType(BuiltList, [FullType(ScannedFileModel)]),
    );
    yield r'root_name';
    yield serializers.serialize(
      object.rootName,
      specifiedType: const FullType(String),
    );
    yield r'template_id';
    yield serializers.serialize(
      object.templateId,
      specifiedType: const FullType(String),
    );
  }

  @override
  Object serialize(
    Serializers serializers,
    PlanRequest object, {
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
    required PlanRequestBuilder result,
    required List<Object?> unhandled,
  }) {
    for (var i = 0; i < serializedList.length; i += 2) {
      final key = serializedList[i] as String;
      final value = serializedList[i + 1];
      switch (key) {
        case r'files':
          final valueDes = serializers.deserialize(
            value,
            specifiedType:
                const FullType(BuiltList, [FullType(ScannedFileModel)]),
          ) as BuiltList<ScannedFileModel>;
          result.files.replace(valueDes);
          break;
        case r'root_name':
          final valueDes = serializers.deserialize(
            value,
            specifiedType: const FullType(String),
          ) as String;
          result.rootName = valueDes;
          break;
        case r'template_id':
          final valueDes = serializers.deserialize(
            value,
            specifiedType: const FullType(String),
          ) as String;
          result.templateId = valueDes;
          break;
        default:
          unhandled.add(key);
          unhandled.add(value);
          break;
      }
    }
  }

  @override
  PlanRequest deserialize(
    Serializers serializers,
    Object serialized, {
    FullType specifiedType = FullType.unspecified,
  }) {
    final result = PlanRequestBuilder();
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
