//
// AUTO-GENERATED FILE, DO NOT MODIFY!
//

// ignore_for_file: unused_element
import 'package:built_collection/built_collection.dart';
import 'package:built_value/built_value.dart';
import 'package:built_value/serializer.dart';

part 'save_transport_order_request.g.dart';

/// The submitted use order, highest priority first.
///
/// Properties:
/// * [order]
@BuiltValue()
abstract class SaveTransportOrderRequest
    implements
        Built<SaveTransportOrderRequest, SaveTransportOrderRequestBuilder> {
  @BuiltValueField(wireName: r'order')
  BuiltList<String> get order;

  SaveTransportOrderRequest._();

  factory SaveTransportOrderRequest(
          [void updates(SaveTransportOrderRequestBuilder b)]) =
      _$SaveTransportOrderRequest;

  @BuiltValueHook(initializeBuilder: true)
  static void _defaults(SaveTransportOrderRequestBuilder b) => b;

  @BuiltValueSerializer(custom: true)
  static Serializer<SaveTransportOrderRequest> get serializer =>
      _$SaveTransportOrderRequestSerializer();
}

class _$SaveTransportOrderRequestSerializer
    implements PrimitiveSerializer<SaveTransportOrderRequest> {
  @override
  final Iterable<Type> types = const [
    SaveTransportOrderRequest,
    _$SaveTransportOrderRequest
  ];

  @override
  final String wireName = r'SaveTransportOrderRequest';

  Iterable<Object?> _serializeProperties(
    Serializers serializers,
    SaveTransportOrderRequest object, {
    FullType specifiedType = FullType.unspecified,
  }) sync* {
    yield r'order';
    yield serializers.serialize(
      object.order,
      specifiedType: const FullType(BuiltList, [FullType(String)]),
    );
  }

  @override
  Object serialize(
    Serializers serializers,
    SaveTransportOrderRequest object, {
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
    required SaveTransportOrderRequestBuilder result,
    required List<Object?> unhandled,
  }) {
    for (var i = 0; i < serializedList.length; i += 2) {
      final key = serializedList[i] as String;
      final value = serializedList[i + 1];
      switch (key) {
        case r'order':
          final valueDes = serializers.deserialize(
            value,
            specifiedType: const FullType(BuiltList, [FullType(String)]),
          ) as BuiltList<String>;
          result.order.replace(valueDes);
          break;
        default:
          unhandled.add(key);
          unhandled.add(value);
          break;
      }
    }
  }

  @override
  SaveTransportOrderRequest deserialize(
    Serializers serializers,
    Object serialized, {
    FullType specifiedType = FullType.unspecified,
  }) {
    final result = SaveTransportOrderRequestBuilder();
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
