import 'package:test/test.dart';
import 'package:auto_scoring_api/auto_scoring_api.dart';

/// tests for TestRegistrationApi
void main() {
  final instance = AutoScoringApi().getTestRegistrationApi();

  group(TestRegistrationApi, () {
    // Analyze Profile
    //
    //Future<ProfileResponse> analyzeProfileTestsTestIdProfileAnalyzePost(String testId) async
    test('test analyzeProfileTestsTestIdProfileAnalyzePost', () async {
      // TODO
    });

    // Complete Registration
    //
    //Future<CompleteRegistrationResponse> completeRegistrationTestsTestIdCompleteRegistrationPost(String testId) async
    test('test completeRegistrationTestsTestIdCompleteRegistrationPost',
        () async {
      // TODO
    });

    // Confirm Profile
    //
    //Future<ProfileResponse> confirmProfileTestsTestIdProfileConfirmPost(String testId) async
    test('test confirmProfileTestsTestIdProfileConfirmPost', () async {
      // TODO
    });

    // Create Test
    //
    //Future<TestResponse> createTestTestsPost(MultipartFile manual, MultipartFile modelAnswer, String name, { String subject }) async
    test('test createTestTestsPost', () async {
      // TODO
    });

    // Get Profile
    //
    //Future<ProfileResponse> getProfileTestsTestIdProfileGet(String testId) async
    test('test getProfileTestsTestIdProfileGet', () async {
      // TODO
    });

    // Get Test
    //
    //Future<TestResponse> getTestTestsTestIdGet(String testId) async
    test('test getTestTestsTestIdGet', () async {
      // TODO
    });

    // Update Profile
    //
    //Future<ProfileResponse> updateProfileTestsTestIdProfilePut(String testId, UpdateProfileRequest updateProfileRequest) async
    test('test updateProfileTestsTestIdProfilePut', () async {
      // TODO
    });
  });
}
