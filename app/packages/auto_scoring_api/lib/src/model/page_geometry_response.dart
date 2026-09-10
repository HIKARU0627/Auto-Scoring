//
// AUTO-GENERATED FILE, DO NOT MODIFY!
//

// ignore_for_file: unused_element
import 'package:built_value/built_value.dart';
import 'package:built_value/serializer.dart';

part 'page_geometry_response.g.dart';

/// One page's layout, as pdfium displays it.  ``displayed_width`` / ``displayed_height`` are `domain.pdf_geometry.PageGeometry`'s own properties: ``CropBox`` intersected with ``MediaBox``, with ``/Rotate`` applied -- the same values the annotation export transforms coordinates against.  **Not a basis for coordinates**; see `_COORDINATE_RULE`.
///
/// Properties:
/// * [displayedHeight] - Height in PDF points of the page as pdfium displays it (CropBox∩MediaBox, after /Rotate). For sizing a placeholder, not for dividing a click position.
/// * [displayedWidth] - Width in PDF points of the page as pdfium displays it (CropBox∩MediaBox, after /Rotate). For sizing a placeholder, not for dividing a click position.
/// * [pageIndex] - 0-based index of this page.
/// * [rotation] - The page's /Rotate, reduced to 0, 90, 180 or 270.
@BuiltValue()
abstract class PageGeometryResponse
    implements Built<PageGeometryResponse, PageGeometryResponseBuilder> {
  /// Height in PDF points of the page as pdfium displays it (CropBox∩MediaBox, after /Rotate). For sizing a placeholder, not for dividing a click position.
  @BuiltValueField(wireName: r'displayed_height')
  num get displayedHeight;

  /// Width in PDF points of the page as pdfium displays it (CropBox∩MediaBox, after /Rotate). For sizing a placeholder, not for dividing a click position.
  @BuiltValueField(wireName: r'displayed_width')
  num get displayedWidth;

  /// 0-based index of this page.
  @BuiltValueField(wireName: r'page_index')
  int get pageIndex;

  /// The page's /Rotate, reduced to 0, 90, 180 or 270.
  @BuiltValueField(wireName: r'rotation')
  int get rotation;

  PageGeometryResponse._();

  factory PageGeometryResponse([void updates(PageGeometryResponseBuilder b)]) =
      _$PageGeometryResponse;

  @BuiltValueHook(initializeBuilder: true)
  static void _defaults(PageGeometryResponseBuilder b) => b;

  @BuiltValueSerializer(custom: true)
  static Serializer<PageGeometryResponse> get serializer =>
      _$PageGeometryResponseSerializer();
}

class _$PageGeometryResponseSerializer
    implements PrimitiveSerializer<PageGeometryResponse> {
  @override
  final Iterable<Type> types = const [
    PageGeometryResponse,
    _$PageGeometryResponse
  ];

  @override
  final String wireName = r'PageGeometryResponse';

  Iterable<Object?> _serializeProperties(
    Serializers serializers,
    PageGeometryResponse object, {
    FullType specifiedType = FullType.unspecified,
  }) sync* {
    yield r'displayed_height';
    yield serializers.serialize(
      object.displayedHeight,
      specifiedType: const FullType(num),
    );
    yield r'displayed_width';
    yield serializers.serialize(
      object.displayedWidth,
      specifiedType: const FullType(num),
    );
    yield r'page_index';
    yield serializers.serialize(
      object.pageIndex,
      specifiedType: const FullType(int),
    );
    yield r'rotation';
    yield serializers.serialize(
      object.rotation,
      specifiedType: const FullType(int),
    );
  }

  @override
  Object serialize(
    Serializers serializers,
    PageGeometryResponse object, {
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
    required PageGeometryResponseBuilder result,
    required List<Object?> unhandled,
  }) {
    for (var i = 0; i < serializedList.length; i += 2) {
      final key = serializedList[i] as String;
      final value = serializedList[i + 1];
      switch (key) {
        case r'displayed_height':
          final valueDes = serializers.deserialize(
            value,
            specifiedType: const FullType(num),
          ) as num;
          result.displayedHeight = valueDes;
          break;
        case r'displayed_width':
          final valueDes = serializers.deserialize(
            value,
            specifiedType: const FullType(num),
          ) as num;
          result.displayedWidth = valueDes;
          break;
        case r'page_index':
          final valueDes = serializers.deserialize(
            value,
            specifiedType: const FullType(int),
          ) as int;
          result.pageIndex = valueDes;
          break;
        case r'rotation':
          final valueDes = serializers.deserialize(
            value,
            specifiedType: const FullType(int),
          ) as int;
          result.rotation = valueDes;
          break;
        default:
          unhandled.add(key);
          unhandled.add(value);
          break;
      }
    }
  }

  @override
  PageGeometryResponse deserialize(
    Serializers serializers,
    Object serialized, {
    FullType specifiedType = FullType.unspecified,
  }) {
    final result = PageGeometryResponseBuilder();
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
