//
// AUTO-GENERATED FILE, DO NOT MODIFY!
//

// ignore_for_file: unused_element
import 'package:built_value/built_value.dart';
import 'package:built_value/serializer.dart';

part 'classification_estimate_model.g.dart';

/// What the confirmation screen shows *before* anything is sent.  ``pending`` is the only number that costs money. ``not_needed`` is what a template's rules already covered for free -- acceptance criterion 8 is that those files are never sent at all, and this is the number that makes that visible to the reviewer rather than only true in the code.
///
/// Properties:
/// * [cached]
/// * [notNeeded]
/// * [pending]
/// * [unsupported]
@BuiltValue()
abstract class ClassificationEstimateModel
    implements
        Built<ClassificationEstimateModel, ClassificationEstimateModelBuilder> {
  @BuiltValueField(wireName: r'cached')
  int get cached;

  @BuiltValueField(wireName: r'not_needed')
  int get notNeeded;

  @BuiltValueField(wireName: r'pending')
  int get pending;

  @BuiltValueField(wireName: r'unsupported')
  int get unsupported;

  ClassificationEstimateModel._();

  factory ClassificationEstimateModel(
          [void updates(ClassificationEstimateModelBuilder b)]) =
      _$ClassificationEstimateModel;

  @BuiltValueHook(initializeBuilder: true)
  static void _defaults(ClassificationEstimateModelBuilder b) => b;

  @BuiltValueSerializer(custom: true)
  static Serializer<ClassificationEstimateModel> get serializer =>
      _$ClassificationEstimateModelSerializer();
}

class _$ClassificationEstimateModelSerializer
    implements PrimitiveSerializer<ClassificationEstimateModel> {
  @override
  final Iterable<Type> types = const [
    ClassificationEstimateModel,
    _$ClassificationEstimateModel
  ];

  @override
  final String wireName = r'ClassificationEstimateModel';

  Iterable<Object?> _serializeProperties(
    Serializers serializers,
    ClassificationEstimateModel object, {
    FullType specifiedType = FullType.unspecified,
  }) sync* {
    yield r'cached';
    yield serializers.serialize(
      object.cached,
      specifiedType: const FullType(int),
    );
    yield r'not_needed';
    yield serializers.serialize(
      object.notNeeded,
      specifiedType: const FullType(int),
    );
    yield r'pending';
    yield serializers.serialize(
      object.pending,
      specifiedType: const FullType(int),
    );
    yield r'unsupported';
    yield serializers.serialize(
      object.unsupported,
      specifiedType: const FullType(int),
    );
  }

  @override
  Object serialize(
    Serializers serializers,
    ClassificationEstimateModel object, {
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
    required ClassificationEstimateModelBuilder result,
    required List<Object?> unhandled,
  }) {
    for (var i = 0; i < serializedList.length; i += 2) {
      final key = serializedList[i] as String;
      final value = serializedList[i + 1];
      switch (key) {
        case r'cached':
          final valueDes = serializers.deserialize(
            value,
            specifiedType: const FullType(int),
          ) as int;
          result.cached = valueDes;
          break;
        case r'not_needed':
          final valueDes = serializers.deserialize(
            value,
            specifiedType: const FullType(int),
          ) as int;
          result.notNeeded = valueDes;
          break;
        case r'pending':
          final valueDes = serializers.deserialize(
            value,
            specifiedType: const FullType(int),
          ) as int;
          result.pending = valueDes;
          break;
        case r'unsupported':
          final valueDes = serializers.deserialize(
            value,
            specifiedType: const FullType(int),
          ) as int;
          result.unsupported = valueDes;
          break;
        default:
          unhandled.add(key);
          unhandled.add(value);
          break;
      }
    }
  }

  @override
  ClassificationEstimateModel deserialize(
    Serializers serializers,
    Object serialized, {
    FullType specifiedType = FullType.unspecified,
  }) {
    final result = ClassificationEstimateModelBuilder();
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
