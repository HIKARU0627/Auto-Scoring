//
// AUTO-GENERATED FILE, DO NOT MODIFY!
//

// ignore_for_file: unused_element
import 'package:built_value/built_value.dart';
import 'package:built_value/serializer.dart';

part 'page_format_model.g.dart';

/// PageFormatModel
///
/// Properties:
/// * [heightPt]
/// * [widthPt]
@BuiltValue()
abstract class PageFormatModel
    implements Built<PageFormatModel, PageFormatModelBuilder> {
  @BuiltValueField(wireName: r'height_pt')
  num get heightPt;

  @BuiltValueField(wireName: r'width_pt')
  num get widthPt;

  PageFormatModel._();

  factory PageFormatModel([void updates(PageFormatModelBuilder b)]) =
      _$PageFormatModel;

  @BuiltValueHook(initializeBuilder: true)
  static void _defaults(PageFormatModelBuilder b) => b;

  @BuiltValueSerializer(custom: true)
  static Serializer<PageFormatModel> get serializer =>
      _$PageFormatModelSerializer();
}

class _$PageFormatModelSerializer
    implements PrimitiveSerializer<PageFormatModel> {
  @override
  final Iterable<Type> types = const [PageFormatModel, _$PageFormatModel];

  @override
  final String wireName = r'PageFormatModel';

  Iterable<Object?> _serializeProperties(
    Serializers serializers,
    PageFormatModel object, {
    FullType specifiedType = FullType.unspecified,
  }) sync* {
    yield r'height_pt';
    yield serializers.serialize(
      object.heightPt,
      specifiedType: const FullType(num),
    );
    yield r'width_pt';
    yield serializers.serialize(
      object.widthPt,
      specifiedType: const FullType(num),
    );
  }

  @override
  Object serialize(
    Serializers serializers,
    PageFormatModel object, {
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
    required PageFormatModelBuilder result,
    required List<Object?> unhandled,
  }) {
    for (var i = 0; i < serializedList.length; i += 2) {
      final key = serializedList[i] as String;
      final value = serializedList[i + 1];
      switch (key) {
        case r'height_pt':
          final valueDes = serializers.deserialize(
            value,
            specifiedType: const FullType(num),
          ) as num;
          result.heightPt = valueDes;
          break;
        case r'width_pt':
          final valueDes = serializers.deserialize(
            value,
            specifiedType: const FullType(num),
          ) as num;
          result.widthPt = valueDes;
          break;
        default:
          unhandled.add(key);
          unhandled.add(value);
          break;
      }
    }
  }

  @override
  PageFormatModel deserialize(
    Serializers serializers,
    Object serialized, {
    FullType specifiedType = FullType.unspecified,
  }) {
    final result = PageFormatModelBuilder();
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
