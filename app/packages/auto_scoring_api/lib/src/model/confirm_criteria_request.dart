//
// AUTO-GENERATED FILE, DO NOT MODIFY!
//

// ignore_for_file: unused_element
import 'package:built_value/built_value.dart';
import 'package:built_value/serializer.dart';

part 'confirm_criteria_request.g.dart';

/// The revision the reviewer is signing off on.
///
/// Properties:
/// * [revision]
@BuiltValue()
abstract class ConfirmCriteriaRequest
    implements Built<ConfirmCriteriaRequest, ConfirmCriteriaRequestBuilder> {
  @BuiltValueField(wireName: r'revision')
  int get revision;

  ConfirmCriteriaRequest._();

  factory ConfirmCriteriaRequest(
          [void updates(ConfirmCriteriaRequestBuilder b)]) =
      _$ConfirmCriteriaRequest;

  @BuiltValueHook(initializeBuilder: true)
  static void _defaults(ConfirmCriteriaRequestBuilder b) => b;

  @BuiltValueSerializer(custom: true)
  static Serializer<ConfirmCriteriaRequest> get serializer =>
      _$ConfirmCriteriaRequestSerializer();
}

class _$ConfirmCriteriaRequestSerializer
    implements PrimitiveSerializer<ConfirmCriteriaRequest> {
  @override
  final Iterable<Type> types = const [
    ConfirmCriteriaRequest,
    _$ConfirmCriteriaRequest
  ];

  @override
  final String wireName = r'ConfirmCriteriaRequest';

  Iterable<Object?> _serializeProperties(
    Serializers serializers,
    ConfirmCriteriaRequest object, {
    FullType specifiedType = FullType.unspecified,
  }) sync* {
    yield r'revision';
    yield serializers.serialize(
      object.revision,
      specifiedType: const FullType(int),
    );
  }

  @override
  Object serialize(
    Serializers serializers,
    ConfirmCriteriaRequest object, {
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
    required ConfirmCriteriaRequestBuilder result,
    required List<Object?> unhandled,
  }) {
    for (var i = 0; i < serializedList.length; i += 2) {
      final key = serializedList[i] as String;
      final value = serializedList[i + 1];
      switch (key) {
        case r'revision':
          final valueDes = serializers.deserialize(
            value,
            specifiedType: const FullType(int),
          ) as int;
          result.revision = valueDes;
          break;
        default:
          unhandled.add(key);
          unhandled.add(value);
          break;
      }
    }
  }

  @override
  ConfirmCriteriaRequest deserialize(
    Serializers serializers,
    Object serialized, {
    FullType specifiedType = FullType.unspecified,
  }) {
    final result = ConfirmCriteriaRequestBuilder();
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
