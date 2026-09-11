//
// AUTO-GENERATED FILE, DO NOT MODIFY!
//

// ignore_for_file: unused_element
import 'package:built_collection/built_collection.dart';
import 'package:auto_scoring_api/src/model/error_catalog_entry_input.dart';
import 'package:built_value/built_value.dart';
import 'package:built_value/serializer.dart';

part 'save_error_catalog_request.g.dart';

/// The reviewed row set, pinned to the revision the reviewer read.
///
/// Properties:
/// * [entries]
/// * [revision]
@BuiltValue()
abstract class SaveErrorCatalogRequest
    implements Built<SaveErrorCatalogRequest, SaveErrorCatalogRequestBuilder> {
  @BuiltValueField(wireName: r'entries')
  BuiltList<ErrorCatalogEntryInput> get entries;

  @BuiltValueField(wireName: r'revision')
  int get revision;

  SaveErrorCatalogRequest._();

  factory SaveErrorCatalogRequest(
          [void updates(SaveErrorCatalogRequestBuilder b)]) =
      _$SaveErrorCatalogRequest;

  @BuiltValueHook(initializeBuilder: true)
  static void _defaults(SaveErrorCatalogRequestBuilder b) => b;

  @BuiltValueSerializer(custom: true)
  static Serializer<SaveErrorCatalogRequest> get serializer =>
      _$SaveErrorCatalogRequestSerializer();
}

class _$SaveErrorCatalogRequestSerializer
    implements PrimitiveSerializer<SaveErrorCatalogRequest> {
  @override
  final Iterable<Type> types = const [
    SaveErrorCatalogRequest,
    _$SaveErrorCatalogRequest
  ];

  @override
  final String wireName = r'SaveErrorCatalogRequest';

  Iterable<Object?> _serializeProperties(
    Serializers serializers,
    SaveErrorCatalogRequest object, {
    FullType specifiedType = FullType.unspecified,
  }) sync* {
    yield r'entries';
    yield serializers.serialize(
      object.entries,
      specifiedType:
          const FullType(BuiltList, [FullType(ErrorCatalogEntryInput)]),
    );
    yield r'revision';
    yield serializers.serialize(
      object.revision,
      specifiedType: const FullType(int),
    );
  }

  @override
  Object serialize(
    Serializers serializers,
    SaveErrorCatalogRequest object, {
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
    required SaveErrorCatalogRequestBuilder result,
    required List<Object?> unhandled,
  }) {
    for (var i = 0; i < serializedList.length; i += 2) {
      final key = serializedList[i] as String;
      final value = serializedList[i + 1];
      switch (key) {
        case r'entries':
          final valueDes = serializers.deserialize(
            value,
            specifiedType:
                const FullType(BuiltList, [FullType(ErrorCatalogEntryInput)]),
          ) as BuiltList<ErrorCatalogEntryInput>;
          result.entries.replace(valueDes);
          break;
        case r'revision':
          final valueDes = serializers.deserialize(
            value,
            specifiedType: const FullType(int),
          ) as int;
          result.revision = valueDes;
          break;
        default:
          unhandled.add(key);
          unhandled.add(value);
          break;
      }
    }
  }

  @override
  SaveErrorCatalogRequest deserialize(
    Serializers serializers,
    Object serialized, {
    FullType specifiedType = FullType.unspecified,
  }) {
    final result = SaveErrorCatalogRequestBuilder();
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
