//
// AUTO-GENERATED FILE, DO NOT MODIFY!
//

// ignore_for_file: unused_element
import 'package:built_value/built_value.dart';
import 'package:built_value/serializer.dart';

part 'error_catalog_entry_model.g.dart';

/// One catalogue row over the wire.
///
/// Properties:
/// * [deduction]
/// * [edited]
/// * [mistake]
/// * [questionLabel]
/// * [redInk]
/// * [roundLabel]
@BuiltValue()
abstract class ErrorCatalogEntryModel
    implements Built<ErrorCatalogEntryModel, ErrorCatalogEntryModelBuilder> {
  @BuiltValueField(wireName: r'deduction')
  String? get deduction;

  @BuiltValueField(wireName: r'edited')
  bool? get edited;

  @BuiltValueField(wireName: r'mistake')
  String get mistake;

  @BuiltValueField(wireName: r'question_label')
  String? get questionLabel;

  @BuiltValueField(wireName: r'red_ink')
  String get redInk;

  @BuiltValueField(wireName: r'round_label')
  String? get roundLabel;

  ErrorCatalogEntryModel._();

  factory ErrorCatalogEntryModel(
          [void updates(ErrorCatalogEntryModelBuilder b)]) =
      _$ErrorCatalogEntryModel;

  @BuiltValueHook(initializeBuilder: true)
  static void _defaults(ErrorCatalogEntryModelBuilder b) => b..edited = false;

  @BuiltValueSerializer(custom: true)
  static Serializer<ErrorCatalogEntryModel> get serializer =>
      _$ErrorCatalogEntryModelSerializer();
}

class _$ErrorCatalogEntryModelSerializer
    implements PrimitiveSerializer<ErrorCatalogEntryModel> {
  @override
  final Iterable<Type> types = const [
    ErrorCatalogEntryModel,
    _$ErrorCatalogEntryModel
  ];

  @override
  final String wireName = r'ErrorCatalogEntryModel';

  Iterable<Object?> _serializeProperties(
    Serializers serializers,
    ErrorCatalogEntryModel object, {
    FullType specifiedType = FullType.unspecified,
  }) sync* {
    if (object.deduction != null) {
      yield r'deduction';
      yield serializers.serialize(
        object.deduction,
        specifiedType: const FullType.nullable(String),
      );
    }
    if (object.edited != null) {
      yield r'edited';
      yield serializers.serialize(
        object.edited,
        specifiedType: const FullType(bool),
      );
    }
    yield r'mistake';
    yield serializers.serialize(
      object.mistake,
      specifiedType: const FullType(String),
    );
    if (object.questionLabel != null) {
      yield r'question_label';
      yield serializers.serialize(
        object.questionLabel,
        specifiedType: const FullType.nullable(String),
      );
    }
    yield r'red_ink';
    yield serializers.serialize(
      object.redInk,
      specifiedType: const FullType(String),
    );
    if (object.roundLabel != null) {
      yield r'round_label';
      yield serializers.serialize(
        object.roundLabel,
        specifiedType: const FullType.nullable(String),
      );
    }
  }

  @override
  Object serialize(
    Serializers serializers,
    ErrorCatalogEntryModel object, {
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
    required ErrorCatalogEntryModelBuilder result,
    required List<Object?> unhandled,
  }) {
    for (var i = 0; i < serializedList.length; i += 2) {
      final key = serializedList[i] as String;
      final value = serializedList[i + 1];
      switch (key) {
        case r'deduction':
          final valueDes = serializers.deserialize(
            value,
            specifiedType: const FullType.nullable(String),
          ) as String?;
          if (valueDes == null) continue;
          result.deduction = valueDes;
          break;
        case r'edited':
          final valueDes = serializers.deserialize(
            value,
            specifiedType: const FullType.nullable(bool),
          ) as bool?;
          if (valueDes == null) continue;
          result.edited = valueDes;
          break;
        case r'mistake':
          final valueDes = serializers.deserialize(
            value,
            specifiedType: const FullType(String),
          ) as String;
          result.mistake = valueDes;
          break;
        case r'question_label':
          final valueDes = serializers.deserialize(
            value,
            specifiedType: const FullType.nullable(String),
          ) as String?;
          if (valueDes == null) continue;
          result.questionLabel = valueDes;
          break;
        case r'red_ink':
          final valueDes = serializers.deserialize(
            value,
            specifiedType: const FullType(String),
          ) as String;
          result.redInk = valueDes;
          break;
        case r'round_label':
          final valueDes = serializers.deserialize(
            value,
            specifiedType: const FullType.nullable(String),
          ) as String?;
          if (valueDes == null) continue;
          result.roundLabel = valueDes;
          break;
        default:
          unhandled.add(key);
          unhandled.add(value);
          break;
      }
    }
  }

  @override
  ErrorCatalogEntryModel deserialize(
    Serializers serializers,
    Object serialized, {
    FullType specifiedType = FullType.unspecified,
  }) {
    final result = ErrorCatalogEntryModelBuilder();
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
