//
// AUTO-GENERATED FILE, DO NOT MODIFY!
//

// ignore_for_file: unused_element
import 'package:auto_scoring_api/src/model/material_role.dart';
import 'package:built_value/built_value.dart';
import 'package:built_value/serializer.dart';

part 'test_material_response.g.dart';

/// One registered file, and the role it was registered under.  ``original_filename`` is the name the reviewer chose the file by. It is carried purely so \"which of my files became the 採点基準?\" stays answerable after import; nothing matches on it, because names in real material are not reliable evidence (`domain.intake_template`).
///
/// Properties:
/// * [createdAt]
/// * [id]
/// * [originalFilename]
/// * [role]
/// * [sha256]
/// * [sizeBytes]
/// * [testId]
@BuiltValue()
abstract class TestMaterialResponse
    implements Built<TestMaterialResponse, TestMaterialResponseBuilder> {
  @BuiltValueField(wireName: r'created_at')
  DateTime get createdAt;

  @BuiltValueField(wireName: r'id')
  String get id;

  @BuiltValueField(wireName: r'original_filename')
  String? get originalFilename;

  @BuiltValueField(wireName: r'role')
  MaterialRole get role;
  // enum roleEnum {  student_answer,  grading_criteria,  annotation_resource,  annotation_sample,  reference,  ignore,  };

  @BuiltValueField(wireName: r'sha256')
  String get sha256;

  @BuiltValueField(wireName: r'size_bytes')
  int get sizeBytes;

  @BuiltValueField(wireName: r'test_id')
  String get testId;

  TestMaterialResponse._();

  factory TestMaterialResponse([void updates(TestMaterialResponseBuilder b)]) =
      _$TestMaterialResponse;

  @BuiltValueHook(initializeBuilder: true)
  static void _defaults(TestMaterialResponseBuilder b) => b;

  @BuiltValueSerializer(custom: true)
  static Serializer<TestMaterialResponse> get serializer =>
      _$TestMaterialResponseSerializer();
}

class _$TestMaterialResponseSerializer
    implements PrimitiveSerializer<TestMaterialResponse> {
  @override
  final Iterable<Type> types = const [
    TestMaterialResponse,
    _$TestMaterialResponse
  ];

  @override
  final String wireName = r'TestMaterialResponse';

  Iterable<Object?> _serializeProperties(
    Serializers serializers,
    TestMaterialResponse object, {
    FullType specifiedType = FullType.unspecified,
  }) sync* {
    yield r'created_at';
    yield serializers.serialize(
      object.createdAt,
      specifiedType: const FullType(DateTime),
    );
    yield r'id';
    yield serializers.serialize(
      object.id,
      specifiedType: const FullType(String),
    );
    if (object.originalFilename != null) {
      yield r'original_filename';
      yield serializers.serialize(
        object.originalFilename,
        specifiedType: const FullType.nullable(String),
      );
    }
    yield r'role';
    yield serializers.serialize(
      object.role,
      specifiedType: const FullType(MaterialRole),
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
    yield r'test_id';
    yield serializers.serialize(
      object.testId,
      specifiedType: const FullType(String),
    );
  }

  @override
  Object serialize(
    Serializers serializers,
    TestMaterialResponse object, {
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
    required TestMaterialResponseBuilder result,
    required List<Object?> unhandled,
  }) {
    for (var i = 0; i < serializedList.length; i += 2) {
      final key = serializedList[i] as String;
      final value = serializedList[i + 1];
      switch (key) {
        case r'created_at':
          final valueDes = serializers.deserialize(
            value,
            specifiedType: const FullType(DateTime),
          ) as DateTime;
          result.createdAt = valueDes;
          break;
        case r'id':
          final valueDes = serializers.deserialize(
            value,
            specifiedType: const FullType(String),
          ) as String;
          result.id = valueDes;
          break;
        case r'original_filename':
          final valueDes = serializers.deserialize(
            value,
            specifiedType: const FullType.nullable(String),
          ) as String?;
          if (valueDes == null) continue;
          result.originalFilename = valueDes;
          break;
        case r'role':
          final valueDes = serializers.deserialize(
            value,
            specifiedType: const FullType(MaterialRole),
          ) as MaterialRole;
          result.role = valueDes;
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
  TestMaterialResponse deserialize(
    Serializers serializers,
    Object serialized, {
    FullType specifiedType = FullType.unspecified,
  }) {
    final result = TestMaterialResponseBuilder();
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
