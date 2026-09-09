//
// AUTO-GENERATED FILE, DO NOT MODIFY!
//

// ignore_for_file: unused_element
import 'package:built_collection/built_collection.dart';
import 'package:built_value/built_value.dart';
import 'package:built_value/serializer.dart';

part 'criteria_status.g.dart';

/// Whether a human has signed off on this draft.  One-way, exactly like ``domain.profile.ProfileStatus``: ``CONFIRMED`` is the attestation that a person looked at every point value, and there is no path back that would let an edit slip in behind that attestation.
class CriteriaStatus extends EnumClass {
  @BuiltValueEnumConst(wireName: r'draft')
  static const CriteriaStatus draft = _$draft;
  @BuiltValueEnumConst(wireName: r'confirmed')
  static const CriteriaStatus confirmed = _$confirmed;

  static Serializer<CriteriaStatus> get serializer =>
      _$criteriaStatusSerializer;

  const CriteriaStatus._(String name) : super(name);

  static BuiltSet<CriteriaStatus> get values => _$values;
  static CriteriaStatus valueOf(String name) => _$valueOf(name);
}

/// Optionally, enum_class can generate a mixin to go with your enum for use
/// with Angular. It exposes your enum constants as getters. So, if you mix it
/// in to your Dart component class, the values become available to the
/// corresponding Angular template.
///
/// Trigger mixin generation by writing a line like this one next to your enum.
abstract class CriteriaStatusMixin = Object with _$CriteriaStatusMixin;
