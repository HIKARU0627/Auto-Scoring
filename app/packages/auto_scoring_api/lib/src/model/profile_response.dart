//
// AUTO-GENERATED FILE, DO NOT MODIFY!
//

// ignore_for_file: unused_element
import 'package:auto_scoring_api/src/model/page_format_model.dart';
import 'package:auto_scoring_api/src/model/region_model.dart';
import 'package:built_collection/built_collection.dart';
import 'package:built_value/built_value.dart';
import 'package:built_value/serializer.dart';

part 'profile_response.g.dart';

/// ProfileResponse
///
/// Properties:
/// * [pages]
/// * [regions]
/// * [revision]
/// * [status]
/// * [testId]
@BuiltValue()
abstract class ProfileResponse
    implements Built<ProfileResponse, ProfileResponseBuilder> {
  @BuiltValueField(wireName: r'pages')
  BuiltList<PageFormatModel> get pages;

  @BuiltValueField(wireName: r'regions')
  BuiltList<RegionModel> get regions;

  @BuiltValueField(wireName: r'revision')
  int get revision;

  @BuiltValueField(wireName: r'status')
  String get status;

  @BuiltValueField(wireName: r'test_id')
  String get testId;

  ProfileResponse._();

  factory ProfileResponse([void updates(ProfileResponseBuilder b)]) =
      _$ProfileResponse;

  @BuiltValueHook(initializeBuilder: true)
  static void _defaults(ProfileResponseBuilder b) => b;

  @BuiltValueSerializer(custom: true)
  static Serializer<ProfileResponse> get serializer =>
      _$ProfileResponseSerializer();
}

class _$ProfileResponseSerializer
    implements PrimitiveSerializer<ProfileResponse> {
  @override
  final Iterable<Type> types = const [ProfileResponse, _$ProfileResponse];

  @override
  final String wireName = r'ProfileResponse';

  Iterable<Object?> _serializeProperties(
    Serializers serializers,
    ProfileResponse object, {
    FullType specifiedType = FullType.unspecified,
  }) sync* {
    yield r'pages';
    yield serializers.serialize(
      object.pages,
      specifiedType: const FullType(BuiltList, [FullType(PageFormatModel)]),
    );
    yield r'regions';
    yield serializers.serialize(
      object.regions,
      specifiedType: const FullType(BuiltList, [FullType(RegionModel)]),
    );
    yield r'revision';
    yield serializers.serialize(
      object.revision,
      specifiedType: const FullType(int),
    );
    yield r'status';
    yield serializers.serialize(
      object.status,
      specifiedType: const FullType(String),
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
    ProfileResponse object, {
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
    required ProfileResponseBuilder result,
    required List<Object?> unhandled,
  }) {
    for (var i = 0; i < serializedList.length; i += 2) {
      final key = serializedList[i] as String;
      final value = serializedList[i + 1];
      switch (key) {
        case r'pages':
          final valueDes = serializers.deserialize(
            value,
            specifiedType:
                const FullType(BuiltList, [FullType(PageFormatModel)]),
          ) as BuiltList<PageFormatModel>;
          result.pages.replace(valueDes);
          break;
        case r'regions':
          final valueDes = serializers.deserialize(
            value,
            specifiedType: const FullType(BuiltList, [FullType(RegionModel)]),
          ) as BuiltList<RegionModel>;
          result.regions.replace(valueDes);
          break;
        case r'revision':
          final valueDes = serializers.deserialize(
            value,
            specifiedType: const FullType(int),
          ) as int;
          result.revision = valueDes;
          break;
        case r'status':
          final valueDes = serializers.deserialize(
            value,
            specifiedType: const FullType(String),
          ) as String;
          result.status = valueDes;
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
  ProfileResponse deserialize(
    Serializers serializers,
    Object serialized, {
    FullType specifiedType = FullType.unspecified,
  }) {
    final result = ProfileResponseBuilder();
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
