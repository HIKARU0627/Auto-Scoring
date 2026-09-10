//
// AUTO-GENERATED FILE, DO NOT MODIFY!
//

// ignore_for_file: unused_element
import 'package:built_collection/built_collection.dart';
import 'package:auto_scoring_api/src/model/page_geometry_response.dart';
import 'package:built_value/built_value.dart';
import 'package:built_value/serializer.dart';

part 'document_pages_response.g.dart';

/// Every page of one stored document, in order.
///
/// Properties:
/// * [pageCount] - Number of pages. Valid page_index values are 0 to page_count - 1.
/// * [pages]
@BuiltValue()
abstract class DocumentPagesResponse
    implements Built<DocumentPagesResponse, DocumentPagesResponseBuilder> {
  /// Number of pages. Valid page_index values are 0 to page_count - 1.
  @BuiltValueField(wireName: r'page_count')
  int get pageCount;

  @BuiltValueField(wireName: r'pages')
  BuiltList<PageGeometryResponse> get pages;

  DocumentPagesResponse._();

  factory DocumentPagesResponse(
      [void updates(DocumentPagesResponseBuilder b)]) = _$DocumentPagesResponse;

  @BuiltValueHook(initializeBuilder: true)
  static void _defaults(DocumentPagesResponseBuilder b) => b;

  @BuiltValueSerializer(custom: true)
  static Serializer<DocumentPagesResponse> get serializer =>
      _$DocumentPagesResponseSerializer();
}

class _$DocumentPagesResponseSerializer
    implements PrimitiveSerializer<DocumentPagesResponse> {
  @override
  final Iterable<Type> types = const [
    DocumentPagesResponse,
    _$DocumentPagesResponse
  ];

  @override
  final String wireName = r'DocumentPagesResponse';

  Iterable<Object?> _serializeProperties(
    Serializers serializers,
    DocumentPagesResponse object, {
    FullType specifiedType = FullType.unspecified,
  }) sync* {
    yield r'page_count';
    yield serializers.serialize(
      object.pageCount,
      specifiedType: const FullType(int),
    );
    yield r'pages';
    yield serializers.serialize(
      object.pages,
      specifiedType:
          const FullType(BuiltList, [FullType(PageGeometryResponse)]),
    );
  }

  @override
  Object serialize(
    Serializers serializers,
    DocumentPagesResponse object, {
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
    required DocumentPagesResponseBuilder result,
    required List<Object?> unhandled,
  }) {
    for (var i = 0; i < serializedList.length; i += 2) {
      final key = serializedList[i] as String;
      final value = serializedList[i + 1];
      switch (key) {
        case r'page_count':
          final valueDes = serializers.deserialize(
            value,
            specifiedType: const FullType(int),
          ) as int;
          result.pageCount = valueDes;
          break;
        case r'pages':
          final valueDes = serializers.deserialize(
            value,
            specifiedType:
                const FullType(BuiltList, [FullType(PageGeometryResponse)]),
          ) as BuiltList<PageGeometryResponse>;
          result.pages.replace(valueDes);
          break;
        default:
          unhandled.add(key);
          unhandled.add(value);
          break;
      }
    }
  }

  @override
  DocumentPagesResponse deserialize(
    Serializers serializers,
    Object serialized, {
    FullType specifiedType = FullType.unspecified,
  }) {
    final result = DocumentPagesResponseBuilder();
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
