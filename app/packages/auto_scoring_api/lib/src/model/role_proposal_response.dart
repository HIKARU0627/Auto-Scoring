//
// AUTO-GENERATED FILE, DO NOT MODIFY!
//

// ignore_for_file: unused_element
import 'package:auto_scoring_api/src/model/material_role.dart';
import 'package:built_value/built_value.dart';
import 'package:built_value/serializer.dart';

part 'role_proposal_response.g.dart';

/// ``role`` is ``null`` when the classifier could not tell.  That is a real answer, not a failure: the reviewer picks, exactly as they would for a file no rule matched.
///
/// Properties:
/// * [cached]
/// * [confidence]
/// * [role]
@BuiltValue()
abstract class RoleProposalResponse
    implements Built<RoleProposalResponse, RoleProposalResponseBuilder> {
  @BuiltValueField(wireName: r'cached')
  bool get cached;

  @BuiltValueField(wireName: r'confidence')
  num get confidence;

  @BuiltValueField(wireName: r'role')
  MaterialRole? get role;
  // enum roleEnum {  student_answer,  grading_criteria,  annotation_resource,  annotation_sample,  reference,  ignore,  };

  RoleProposalResponse._();

  factory RoleProposalResponse([void updates(RoleProposalResponseBuilder b)]) =
      _$RoleProposalResponse;

  @BuiltValueHook(initializeBuilder: true)
  static void _defaults(RoleProposalResponseBuilder b) => b;

  @BuiltValueSerializer(custom: true)
  static Serializer<RoleProposalResponse> get serializer =>
      _$RoleProposalResponseSerializer();
}

class _$RoleProposalResponseSerializer
    implements PrimitiveSerializer<RoleProposalResponse> {
  @override
  final Iterable<Type> types = const [
    RoleProposalResponse,
    _$RoleProposalResponse
  ];

  @override
  final String wireName = r'RoleProposalResponse';

  Iterable<Object?> _serializeProperties(
    Serializers serializers,
    RoleProposalResponse object, {
    FullType specifiedType = FullType.unspecified,
  }) sync* {
    yield r'cached';
    yield serializers.serialize(
      object.cached,
      specifiedType: const FullType(bool),
    );
    yield r'confidence';
    yield serializers.serialize(
      object.confidence,
      specifiedType: const FullType(num),
    );
    yield r'role';
    yield object.role == null
        ? null
        : serializers.serialize(
            object.role,
            specifiedType: const FullType.nullable(MaterialRole),
          );
  }

  @override
  Object serialize(
    Serializers serializers,
    RoleProposalResponse object, {
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
    required RoleProposalResponseBuilder result,
    required List<Object?> unhandled,
  }) {
    for (var i = 0; i < serializedList.length; i += 2) {
      final key = serializedList[i] as String;
      final value = serializedList[i + 1];
      switch (key) {
        case r'cached':
          final valueDes = serializers.deserialize(
            value,
            specifiedType: const FullType(bool),
          ) as bool;
          result.cached = valueDes;
          break;
        case r'confidence':
          final valueDes = serializers.deserialize(
            value,
            specifiedType: const FullType(num),
          ) as num;
          result.confidence = valueDes;
          break;
        case r'role':
          final valueDes = serializers.deserialize(
            value,
            specifiedType: const FullType.nullable(MaterialRole),
          ) as MaterialRole?;
          if (valueDes == null) continue;
          result.role = valueDes;
          break;
        default:
          unhandled.add(key);
          unhandled.add(value);
          break;
      }
    }
  }

  @override
  RoleProposalResponse deserialize(
    Serializers serializers,
    Object serialized, {
    FullType specifiedType = FullType.unspecified,
  }) {
    final result = RoleProposalResponseBuilder();
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
