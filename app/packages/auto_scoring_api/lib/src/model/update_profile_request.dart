//
// AUTO-GENERATED FILE, DO NOT MODIFY!
//

// ignore_for_file: unused_element
import 'package:auto_scoring_api/src/model/region_model.dart';
import 'package:built_collection/built_collection.dart';
import 'package:built_value/built_value.dart';
import 'package:built_value/serializer.dart';

part 'update_profile_request.g.dart';

/// UpdateProfileRequest
///
/// Properties:
/// * [regions]
@BuiltValue()
abstract class UpdateProfileRequest
    implements Built<UpdateProfileRequest, UpdateProfileRequestBuilder> {
  @BuiltValueField(wireName: r'regions')
  BuiltList<RegionModel>? get regions;

  UpdateProfileRequest._();

  factory UpdateProfileRequest([void updates(UpdateProfileRequestBuilder b)]) =
      _$UpdateProfileRequest;

  @BuiltValueHook(initializeBuilder: true)
  static void _defaults(UpdateProfileRequestBuilder b) => b;

  @BuiltValueSerializer(custom: true)
  static Serializer<UpdateProfileRequest> get serializer =>
      _$UpdateProfileRequestSerializer();
}

class _$UpdateProfileRequestSerializer
    implements PrimitiveSerializer<UpdateProfileRequest> {
  @override
  final Iterable<Type> types = const [
    UpdateProfileRequest,
    _$UpdateProfileRequest
  ];

  @override
  final String wireName = r'UpdateProfileRequest';

  Iterable<Object?> _serializeProperties(
    Serializers serializers,
    UpdateProfileRequest object, {
    FullType specifiedType = FullType.unspecified,
  }) sync* {
    if (object.regions != null) {
      yield r'regions';
      yield serializers.serialize(
        object.regions,
        specifiedType: const FullType(BuiltList, [FullType(RegionModel)]),
      );
    }
  }

  @override
  Object serialize(
    Serializers serializers,
    UpdateProfileRequest object, {
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
    required UpdateProfileRequestBuilder result,
    required List<Object?> unhandled,
  }) {
    for (var i = 0; i < serializedList.length; i += 2) {
      final key = serializedList[i] as String;
      final value = serializedList[i + 1];
      switch (key) {
        case r'regions':
          final valueDes = serializers.deserialize(
            value,
            specifiedType:
                const FullType.nullable(BuiltList, [FullType(RegionModel)]),
          ) as BuiltList<RegionModel>?;
          if (valueDes == null) continue;
          result.regions.replace(valueDes);
          break;
        default:
          unhandled.add(key);
          unhandled.add(value);
          break;
      }
    }
  }

  @override
  UpdateProfileRequest deserialize(
    Serializers serializers,
    Object serialized, {
    FullType specifiedType = FullType.unspecified,
  }) {
    final result = UpdateProfileRequestBuilder();
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
