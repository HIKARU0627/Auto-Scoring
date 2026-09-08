import 'package:test/test.dart';
import 'package:auto_scoring_api/auto_scoring_api.dart';

/// tests for IntakeApi
void main() {
  final instance = AutoScoringApi().getIntakeApi();

  group(IntakeApi, () {
    // Attribute Answer
    //
    // Ask which of the offered tests one answer belongs to.  The candidate set is the caller's: the tests this batch would create plus the already-registered ones the reviewer has narrowed to. **A caller with a single candidate must not call this at all** -- the reviewer has already decided, and asking a provider to choose from a list of one spends money to confirm a foregone conclusion. That is the ordinary case from week two onward, which is why the reviewer's narrowing step is the real cost control here and the classifier is the fallback.
    //
    //Future<AttributionProposalResponse> attributeAnswerIntakeAttributePost(BuiltList<String> candidateIds, BuiltList<String> candidateLabels, MultipartFile file) async
    test('test attributeAnswerIntakeAttributePost', () async {
      // TODO
    });

    // Classification Availability
    //
    //Future<ClassificationAvailabilityResponse> classificationAvailabilityIntakeClassificationAvailabilityGet() async
    test('test classificationAvailabilityIntakeClassificationAvailabilityGet',
        () async {
      // TODO
    });

    // Classify Material
    //
    // Propose what one file is, from its first page.  Callers send only files a template's rules did not match: a matched file must never reach this endpoint (acceptance criterion 8). Nothing here enforces that -- there is no way for this endpoint to know which template the caller used -- so the guarantee lives where the decision is made, in `domain.intake_plan.build_plan` and its tests.
    //
    //Future<RoleProposalResponse> classifyMaterialIntakeClassifyPost(MultipartFile file) async
    test('test classifyMaterialIntakeClassifyPost', () async {
      // TODO
    });

    // List Templates
    //
    //Future<BuiltList<IntakeTemplateModel>> listTemplatesIntakeTemplatesGet() async
    test('test listTemplatesIntakeTemplatesGet', () async {
      // TODO
    });

    // Plan Intake
    //
    //Future<IntakePlanResponse> planIntakeIntakePlanPost(PlanRequest planRequest) async
    test('test planIntakeIntakePlanPost', () async {
      // TODO
    });

    // Save Templates
    //
    //Future<BuiltList<IntakeTemplateModel>> saveTemplatesIntakeTemplatesPut(SaveTemplatesRequest saveTemplatesRequest) async
    test('test saveTemplatesIntakeTemplatesPut', () async {
      // TODO
    });
  });
}
