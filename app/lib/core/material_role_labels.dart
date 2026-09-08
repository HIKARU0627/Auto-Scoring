import 'package:auto_scoring_app/api/sidecar_api_client.dart';

/// Japanese labels for [MaterialRole], in the words the material itself uses.
///
/// The role ids are English because they are wire values; what a reviewer sees
/// must be the term printed on the documents their cram school sent
/// (「採点基準」「添削資料」「添削サンプル」), not a translation of an internal
/// name. Issue #68's wording rule: a control says what it actually does.
String materialRoleLabel(MaterialRole role) => switch (role) {
  MaterialRole.studentAnswer => '生徒答案',
  MaterialRole.gradingCriteria => '採点基準',
  MaterialRole.annotationResource => '添削資料',
  MaterialRole.annotationSample => '添削サンプル',
  MaterialRole.reference => '参考資料',
  MaterialRole.ignore => '取り込まない',
  _ => role.name,
};
