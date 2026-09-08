//
// AUTO-GENERATED FILE, DO NOT MODIFY!
//

// ignore_for_file: unused_element
import 'package:built_value/built_value.dart';
import 'package:built_value/serializer.dart';

part 'scanned_file_model.g.dart';

/// ScannedFileModel
///
/// Properties:
/// * [relativePath]
/// * [sha256]
/// * [sizeBytes]
@BuiltValue()
abstract class ScannedFileModel
    implements Built<ScannedFileModel, ScannedFileModelBuilder> {
  @BuiltValueField(wireName: r'relative_path')
  String get relativePath;

  @BuiltValueField(wireName: r'sha256')
  String get sha256;

  @BuiltValueField(wireName: r'size_bytes')
  int get sizeBytes;

  ScannedFileModel._();

  factory ScannedFileModel([void updates(ScannedFileModelBuilder b)]) =
      _$ScannedFileModel;

  @BuiltValueHook(initializeBuilder: true)
  static void _defaults(ScannedFileModelBuilder b) => b;

  @BuiltValueSerializer(custom: true)
  static Serializer<ScannedFileModel> get serializer =>
      _$ScannedFileModelSerializer();
}

class _$ScannedFileModelSerializer
    implements PrimitiveSerializer<ScannedFileModel> {
  @override
  final Iterable<Type> types = const [ScannedFileModel, _$ScannedFileModel];

  @override
  final String wireName = r'ScannedFileModel';

  Iterable<Object?> _serializeProperties(
    Serializers serializers,
    ScannedFileModel object, {
    FullType specifiedType = FullType.unspecified,
  }) sync* {
    yield r'relative_path';
    yield serializers.serialize(
      object.relativePath,
      specifiedType: const FullType(String),
    );
    yield r'sha256';
    yield serializers.serialize(
      object.sha256,
      specifiedType: const FullType(String),
    );
    yield r'size_bytes';
    yield serializers.serialize(
      object.sizeBytes,
      specifiedType: const FullType(int),
    );
  }

  @override
  Object serialize(
    Serializers serializers,
    ScannedFileModel object, {
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
    required ScannedFileModelBuilder result,
    required List<Object?> unhandled,
  }) {
    for (var i = 0; i < serializedList.length; i += 2) {
      final key = serializedList[i] as String;
      final value = serializedList[i + 1];
      switch (key) {
        case r'relative_path':
          final valueDes = serializers.deserialize(
            value,
            specifiedType: const FullType(String),
          ) as String;
          result.relativePath = valueDes;
          break;
        case r'sha256':
          final valueDes = serializers.deserialize(
            value,
            specifiedType: const FullType(String),
          ) as String;
          result.sha256 = valueDes;
          break;
        case r'size_bytes':
          final valueDes = serializers.deserialize(
            value,
            specifiedType: const FullType(int),
          ) as int;
          result.sizeBytes = valueDes;
          break;
        default:
          unhandled.add(key);
          unhandled.add(value);
          break;
      }
    }
  }

  @override
  ScannedFileModel deserialize(
    Serializers serializers,
    Object serialized, {
    FullType specifiedType = FullType.unspecified,
  }) {
    final result = ScannedFileModelBuilder();
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
