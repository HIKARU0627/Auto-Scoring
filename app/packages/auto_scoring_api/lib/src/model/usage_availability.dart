//
// AUTO-GENERATED FILE, DO NOT MODIFY!
//

// ignore_for_file: unused_element
import 'package:built_collection/built_collection.dart';
import 'package:built_value/built_value.dart';
import 'package:built_value/serializer.dart';

part 'usage_availability.g.dart';

/// Whether token totals are complete for the rows being summarized.
class UsageAvailability extends EnumClass {
  @BuiltValueEnumConst(wireName: r'known')
  static const UsageAvailability known = _$known;
  @BuiltValueEnumConst(wireName: r'partial')
  static const UsageAvailability partial = _$partial;
  @BuiltValueEnumConst(wireName: r'unknown')
  static const UsageAvailability unknown = _$unknown;

  static Serializer<UsageAvailability> get serializer =>
      _$usageAvailabilitySerializer;

  const UsageAvailability._(String name) : super(name);

  static BuiltSet<UsageAvailability> get values => _$values;
  static UsageAvailability valueOf(String name) => _$valueOf(name);
}

/// Optionally, enum_class can generate a mixin to go with your enum for use
/// with Angular. It exposes your enum constants as getters. So, if you mix it
/// in to your Dart component class, the values become available to the
/// corresponding Angular template.
///
/// Trigger mixin generation by writing a line like this one next to your enum.
abstract class UsageAvailabilityMixin = Object with _$UsageAvailabilityMixin;
