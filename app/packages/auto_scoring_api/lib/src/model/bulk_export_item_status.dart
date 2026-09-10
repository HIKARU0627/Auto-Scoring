//
// AUTO-GENERATED FILE, DO NOT MODIFY!
//

// ignore_for_file: unused_element
import 'package:built_collection/built_collection.dart';
import 'package:built_value/built_value.dart';
import 'package:built_value/serializer.dart';

part 'bulk_export_item_status.g.dart';

/// What happened to one submission in a bulk export (Issue #142).  Deliberately *not* an error: the whole point of the bulk endpoint is that one submission's refusal must not cost the reviewer the other 39 (Issue #142, \"途中で止めない\"). So every outcome -- including the ones the single-submission endpoint raises a 409 for -- comes back as a row.
class BulkExportItemStatus extends EnumClass {
  @BuiltValueEnumConst(wireName: r'queued')
  static const BulkExportItemStatus queued = _$queued;
  @BuiltValueEnumConst(wireName: r'reused')
  static const BulkExportItemStatus reused = _$reused;
  @BuiltValueEnumConst(wireName: r'refused')
  static const BulkExportItemStatus refused = _$refused;

  static Serializer<BulkExportItemStatus> get serializer =>
      _$bulkExportItemStatusSerializer;

  const BulkExportItemStatus._(String name) : super(name);

  static BuiltSet<BulkExportItemStatus> get values => _$values;
  static BulkExportItemStatus valueOf(String name) => _$valueOf(name);
}

/// Optionally, enum_class can generate a mixin to go with your enum for use
/// with Angular. It exposes your enum constants as getters. So, if you mix it
/// in to your Dart component class, the values become available to the
/// corresponding Angular template.
///
/// Trigger mixin generation by writing a line like this one next to your enum.
abstract class BulkExportItemStatusMixin = Object
    with _$BulkExportItemStatusMixin;
