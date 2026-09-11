//
// AUTO-GENERATED FILE, DO NOT MODIFY!
//

// ignore_for_file: unused_element
import 'package:auto_scoring_api/src/model/catalog_state.dart';
import 'package:built_collection/built_collection.dart';
import 'package:auto_scoring_api/src/model/error_catalog_entry_model.dart';
import 'package:built_value/built_value.dart';
import 'package:built_value/serializer.dart';

part 'error_catalog_response.g.dart';

/// A test's 誤答カタログ, as the review screen sees it.
///
/// Properties:
/// * [entries]
/// * [entryCount]
/// * [importError]
/// * [imported]
/// * [revision]
/// * [state]
/// * [testId]
@BuiltValue()
abstract class ErrorCatalogResponse
    implements Built<ErrorCatalogResponse, ErrorCatalogResponseBuilder> {
  @BuiltValueField(wireName: r'entries')
  BuiltList<ErrorCatalogEntryModel> get entries;

  @BuiltValueField(wireName: r'entry_count')
  int get entryCount;

  @BuiltValueField(wireName: r'import_error')
  String? get importError;

  @BuiltValueField(wireName: r'imported')
  bool get imported;

  @BuiltValueField(wireName: r'revision')
  int get revision;

  @BuiltValueField(wireName: r'state')
  CatalogState get state;
  // enum stateEnum {  not_registered,  word_only,  unreadable,  available,  };

  @BuiltValueField(wireName: r'test_id')
  String get testId;

  ErrorCatalogResponse._();

  factory ErrorCatalogResponse([void updates(ErrorCatalogResponseBuilder b)]) =
      _$ErrorCatalogResponse;

  @BuiltValueHook(initializeBuilder: true)
  static void _defaults(ErrorCatalogResponseBuilder b) => b;

  @BuiltValueSerializer(custom: true)
  static Serializer<ErrorCatalogResponse> get serializer =>
      _$ErrorCatalogResponseSerializer();
}

class _$ErrorCatalogResponseSerializer
    implements PrimitiveSerializer<ErrorCatalogResponse> {
  @override
  final Iterable<Type> types = const [
    ErrorCatalogResponse,
    _$ErrorCatalogResponse
  ];

  @override
  final String wireName = r'ErrorCatalogResponse';

  Iterable<Object?> _serializeProperties(
    Serializers serializers,
    ErrorCatalogResponse object, {
    FullType specifiedType = FullType.unspecified,
  }) sync* {
    yield r'entries';
    yield serializers.serialize(
      object.entries,
      specifiedType:
          const FullType(BuiltList, [FullType(ErrorCatalogEntryModel)]),
    );
    yield r'entry_count';
    yield serializers.serialize(
      object.entryCount,
      specifiedType: const FullType(int),
    );
    if (object.importError != null) {
      yield r'import_error';
      yield serializers.serialize(
        object.importError,
        specifiedType: const FullType.nullable(String),
      );
    }
    yield r'imported';
    yield serializers.serialize(
      object.imported,
      specifiedType: const FullType(bool),
    );
    yield r'revision';
    yield serializers.serialize(
      object.revision,
      specifiedType: const FullType(int),
    );
    yield r'state';
    yield serializers.serialize(
      object.state,
      specifiedType: const FullType(CatalogState),
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
    ErrorCatalogResponse object, {
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
    required ErrorCatalogResponseBuilder result,
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
                const FullType(BuiltList, [FullType(ErrorCatalogEntryModel)]),
          ) as BuiltList<ErrorCatalogEntryModel>;
          result.entries.replace(valueDes);
          break;
        case r'entry_count':
          final valueDes = serializers.deserialize(
            value,
            specifiedType: const FullType(int),
          ) as int;
          result.entryCount = valueDes;
          break;
        case r'import_error':
          final valueDes = serializers.deserialize(
            value,
            specifiedType: const FullType.nullable(String),
          ) as String?;
          if (valueDes == null) continue;
          result.importError = valueDes;
          break;
        case r'imported':
          final valueDes = serializers.deserialize(
            value,
            specifiedType: const FullType(bool),
          ) as bool;
          result.imported = valueDes;
          break;
        case r'revision':
          final valueDes = serializers.deserialize(
            value,
            specifiedType: const FullType(int),
          ) as int;
          result.revision = valueDes;
          break;
        case r'state':
          final valueDes = serializers.deserialize(
            value,
            specifiedType: const FullType(CatalogState),
          ) as CatalogState;
          result.state = valueDes;
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
  ErrorCatalogResponse deserialize(
    Serializers serializers,
    Object serialized, {
    FullType specifiedType = FullType.unspecified,
  }) {
    final result = ErrorCatalogResponseBuilder();
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
