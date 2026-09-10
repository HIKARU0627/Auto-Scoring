//
// AUTO-GENERATED FILE, DO NOT MODIFY!
//

// ignore_for_file: unused_element
import 'package:built_collection/built_collection.dart';
import 'package:built_value/built_value.dart';
import 'package:built_value/serializer.dart';

part 'export_refusal_reason.g.dart';

/// Why the sidecar refuses to export one submission -- the two gates `export_refusal` evaluates, and the wire values the client reads.  The values travel verbatim: as ``detail.code`` on the single export's 409 (`api.export_router`) and as ``refusal_code`` on a bulk item (Issue #142). They live here rather than in the API layer because the *distinction* is a domain fact, not a transport one -- what the reviewer must do next differs completely between the two, and both the single and the bulk path must name it the same way.  Issue #150 is why naming it at all is not optional. Until then the two refusals shared one ``{message, question_ids}`` shape with nothing to tell them apart, and the Flutter client -- written when only `UNCONFIRMED_QUESTIONS` existed -- rendered both as \"未確認の設問がある ため出力できません\". In the live run a reviewer who had already confirmed every question was told to go and confirm them: an instruction that was not merely unhelpful but unfollowable, since the work it asked for was already done.
class ExportRefusalReason extends EnumClass {
  @BuiltValueEnumConst(wireName: r'unconfirmed_questions')
  static const ExportRefusalReason unconfirmedQuestions =
      _$unconfirmedQuestions;
  @BuiltValueEnumConst(wireName: r'no_room_for_score')
  static const ExportRefusalReason noRoomForScore = _$noRoomForScore;

  static Serializer<ExportRefusalReason> get serializer =>
      _$exportRefusalReasonSerializer;

  const ExportRefusalReason._(String name) : super(name);

  static BuiltSet<ExportRefusalReason> get values => _$values;
  static ExportRefusalReason valueOf(String name) => _$valueOf(name);
}

/// Optionally, enum_class can generate a mixin to go with your enum for use
/// with Angular. It exposes your enum constants as getters. So, if you mix it
/// in to your Dart component class, the values become available to the
/// corresponding Angular template.
///
/// Trigger mixin generation by writing a line like this one next to your enum.
abstract class ExportRefusalReasonMixin = Object
    with _$ExportRefusalReasonMixin;
