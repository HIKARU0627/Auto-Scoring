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
/// * [absentQuestionNumbers]
/// * [pages]
/// * [questionNumbers]
/// * [readingOrderConflicts]
/// * [regions]
/// * [revision]
/// * [status]
/// * [testId]
/// * [unassignedRegionIds]
/// * [undetectedQuestionNumbers]
@BuiltValue()
abstract class ProfileResponse
    implements Built<ProfileResponse, ProfileResponseBuilder> {
  @BuiltValueField(wireName: r'absent_question_numbers')
  BuiltList<String> get absentQuestionNumbers;

  @BuiltValueField(wireName: r'pages')
  BuiltList<PageFormatModel> get pages;

  @BuiltValueField(wireName: r'question_numbers')
  BuiltList<String> get questionNumbers;

  @BuiltValueField(wireName: r'reading_order_conflicts')
  BuiltList<BuiltList<String>> get readingOrderConflicts;

  @BuiltValueField(wireName: r'regions')
  BuiltList<RegionModel> get regions;

  @BuiltValueField(wireName: r'revision')
  int get revision;

  @BuiltValueField(wireName: r'status')
  String get status;

  @BuiltValueField(wireName: r'test_id')
  String get testId;

  @BuiltValueField(wireName: r'unassigned_region_ids')
  BuiltList<String> get unassignedRegionIds;

  @BuiltValueField(wireName: r'undetected_question_numbers')
  BuiltList<String> get undetectedQuestionNumbers;

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
    yield r'absent_question_numbers';
    yield serializers.serialize(
      object.absentQuestionNumbers,
      specifiedType: const FullType(BuiltList, [FullType(String)]),
    );
    yield r'pages';
    yield serializers.serialize(
      object.pages,
      specifiedType: const FullType(BuiltList, [FullType(PageFormatModel)]),
    );
    yield r'question_numbers';
    yield serializers.serialize(
      object.questionNumbers,
      specifiedType: const FullType(BuiltList, [FullType(String)]),
    );
    yield r'reading_order_conflicts';
    yield serializers.serialize(
      object.readingOrderConflicts,
      specifiedType: const FullType(BuiltList, [
        FullType(BuiltList, [FullType(String)])
      ]),
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
    yield r'unassigned_region_ids';
    yield serializers.serialize(
      object.unassignedRegionIds,
      specifiedType: const FullType(BuiltList, [FullType(String)]),
    );
    yield r'undetected_question_numbers';
    yield serializers.serialize(
      object.undetectedQuestionNumbers,
      specifiedType: const FullType(BuiltList, [FullType(String)]),
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
        case r'absent_question_numbers':
          final valueDes = serializers.deserialize(
            value,
            specifiedType: const FullType(BuiltList, [FullType(String)]),
          ) as BuiltList<String>;
          result.absentQuestionNumbers.replace(valueDes);
          break;
        case r'pages':
          final valueDes = serializers.deserialize(
            value,
            specifiedType:
                const FullType(BuiltList, [FullType(PageFormatModel)]),
          ) as BuiltList<PageFormatModel>;
          result.pages.replace(valueDes);
          break;
        case r'question_numbers':
          final valueDes = serializers.deserialize(
            value,
            specifiedType: const FullType(BuiltList, [FullType(String)]),
          ) as BuiltList<String>;
          result.questionNumbers.replace(valueDes);
          break;
        case r'reading_order_conflicts':
          final valueDes = serializers.deserialize(
            value,
            specifiedType: const FullType(BuiltList, [
              FullType(BuiltList, [FullType(String)])
            ]),
          ) as BuiltList<BuiltList<String>>;
          result.readingOrderConflicts.replace(valueDes);
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
        case r'unassigned_region_ids':
          final valueDes = serializers.deserialize(
            value,
            specifiedType: const FullType(BuiltList, [FullType(String)]),
          ) as BuiltList<String>;
          result.unassignedRegionIds.replace(valueDes);
          break;
        case r'undetected_question_numbers':
          final valueDes = serializers.deserialize(
            value,
            specifiedType: const FullType(BuiltList, [FullType(String)]),
          ) as BuiltList<String>;
          result.undetectedQuestionNumbers.replace(valueDes);
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
