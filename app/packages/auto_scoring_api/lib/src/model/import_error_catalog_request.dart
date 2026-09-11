//
// AUTO-GENERATED FILE, DO NOT MODIFY!
//

// ignore_for_file: unused_element
import 'package:auto_scoring_api/src/model/import_conflict_policy.dart';
import 'package:built_value/built_value.dart';
import 'package:built_value/serializer.dart';

part 'import_error_catalog_request.g.dart';

/// The explicit instruction to read the source file again.
///
/// Properties:
/// * [onConflict]
@BuiltValue()
abstract class ImportErrorCatalogRequest
    implements
        Built<ImportErrorCatalogRequest, ImportErrorCatalogRequestBuilder> {
  @BuiltValueField(wireName: r'on_conflict')
  ImportConflictPolicy get onConflict;
  // enum onConflictEnum {  keep_edited,  overwrite,  };

  ImportErrorCatalogRequest._();

  factory ImportErrorCatalogRequest(
          [void updates(ImportErrorCatalogRequestBuilder b)]) =
      _$ImportErrorCatalogRequest;

  @BuiltValueHook(initializeBuilder: true)
  static void _defaults(ImportErrorCatalogRequestBuilder b) => b;

  @BuiltValueSerializer(custom: true)
  static Serializer<ImportErrorCatalogRequest> get serializer =>
      _$ImportErrorCatalogRequestSerializer();
}

class _$ImportErrorCatalogRequestSerializer
    implements PrimitiveSerializer<ImportErrorCatalogRequest> {
  @override
  final Iterable<Type> types = const [
    ImportErrorCatalogRequest,
    _$ImportErrorCatalogRequest
  ];

  @override
  final String wireName = r'ImportErrorCatalogRequest';

  Iterable<Object?> _serializeProperties(
    Serializers serializers,
    ImportErrorCatalogRequest object, {
    FullType specifiedType = FullType.unspecified,
  }) sync* {
    yield r'on_conflict';
    yield serializers.serialize(
      object.onConflict,
      specifiedType: const FullType(ImportConflictPolicy),
    );
  }

  @override
  Object serialize(
    Serializers serializers,
    ImportErrorCatalogRequest object, {
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
    required ImportErrorCatalogRequestBuilder result,
    required List<Object?> unhandled,
  }) {
    for (var i = 0; i < serializedList.length; i += 2) {
      final key = serializedList[i] as String;
      final value = serializedList[i + 1];
      switch (key) {
        case r'on_conflict':
          final valueDes = serializers.deserialize(
            value,
            specifiedType: const FullType(ImportConflictPolicy),
          ) as ImportConflictPolicy;
          result.onConflict = valueDes;
          break;
        default:
          unhandled.add(key);
          unhandled.add(value);
          break;
      }
    }
  }

  @override
  ImportErrorCatalogRequest deserialize(
    Serializers serializers,
    Object serialized, {
    FullType specifiedType = FullType.unspecified,
  }) {
    final result = ImportErrorCatalogRequestBuilder();
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
