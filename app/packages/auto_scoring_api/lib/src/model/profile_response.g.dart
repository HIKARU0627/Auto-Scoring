// GENERATED CODE - DO NOT MODIFY BY HAND

part of 'profile_response.dart';

// **************************************************************************
// BuiltValueGenerator
// **************************************************************************

class _$ProfileResponse extends ProfileResponse {
  @override
  final BuiltList<PageFormatModel> pages;
  @override
  final BuiltList<String> questionNumbers;
  @override
  final BuiltList<RegionModel> regions;
  @override
  final int revision;
  @override
  final String status;
  @override
  final String testId;
  @override
  final BuiltList<String> unassignedRegionIds;
  @override
  final BuiltList<String> undetectedQuestionNumbers;

  factory _$ProfileResponse([void Function(ProfileResponseBuilder)? updates]) =>
      (ProfileResponseBuilder()..update(updates))._build();

  _$ProfileResponse._(
      {required this.pages,
      required this.questionNumbers,
      required this.regions,
      required this.revision,
      required this.status,
      required this.testId,
      required this.unassignedRegionIds,
      required this.undetectedQuestionNumbers})
      : super._();
  @override
  ProfileResponse rebuild(void Function(ProfileResponseBuilder) updates) =>
      (toBuilder()..update(updates)).build();

  @override
  ProfileResponseBuilder toBuilder() => ProfileResponseBuilder()..replace(this);

  @override
  bool operator ==(Object other) {
    if (identical(other, this)) return true;
    return other is ProfileResponse &&
        pages == other.pages &&
        questionNumbers == other.questionNumbers &&
        regions == other.regions &&
        revision == other.revision &&
        status == other.status &&
        testId == other.testId &&
        unassignedRegionIds == other.unassignedRegionIds &&
        undetectedQuestionNumbers == other.undetectedQuestionNumbers;
  }

  @override
  int get hashCode {
    var _$hash = 0;
    _$hash = $jc(_$hash, pages.hashCode);
    _$hash = $jc(_$hash, questionNumbers.hashCode);
    _$hash = $jc(_$hash, regions.hashCode);
    _$hash = $jc(_$hash, revision.hashCode);
    _$hash = $jc(_$hash, status.hashCode);
    _$hash = $jc(_$hash, testId.hashCode);
    _$hash = $jc(_$hash, unassignedRegionIds.hashCode);
    _$hash = $jc(_$hash, undetectedQuestionNumbers.hashCode);
    _$hash = $jf(_$hash);
    return _$hash;
  }

  @override
  String toString() {
    return (newBuiltValueToStringHelper(r'ProfileResponse')
          ..add('pages', pages)
          ..add('questionNumbers', questionNumbers)
          ..add('regions', regions)
          ..add('revision', revision)
          ..add('status', status)
          ..add('testId', testId)
          ..add('unassignedRegionIds', unassignedRegionIds)
          ..add('undetectedQuestionNumbers', undetectedQuestionNumbers))
        .toString();
  }
}

class ProfileResponseBuilder
    implements Builder<ProfileResponse, ProfileResponseBuilder> {
  _$ProfileResponse? _$v;

  ListBuilder<PageFormatModel>? _pages;
  ListBuilder<PageFormatModel> get pages =>
      _$this._pages ??= ListBuilder<PageFormatModel>();
  set pages(ListBuilder<PageFormatModel>? pages) => _$this._pages = pages;

  ListBuilder<String>? _questionNumbers;
  ListBuilder<String> get questionNumbers =>
      _$this._questionNumbers ??= ListBuilder<String>();
  set questionNumbers(ListBuilder<String>? questionNumbers) =>
      _$this._questionNumbers = questionNumbers;

  ListBuilder<RegionModel>? _regions;
  ListBuilder<RegionModel> get regions =>
      _$this._regions ??= ListBuilder<RegionModel>();
  set regions(ListBuilder<RegionModel>? regions) => _$this._regions = regions;

  int? _revision;
  int? get revision => _$this._revision;
  set revision(int? revision) => _$this._revision = revision;

  String? _status;
  String? get status => _$this._status;
  set status(String? status) => _$this._status = status;

  String? _testId;
  String? get testId => _$this._testId;
  set testId(String? testId) => _$this._testId = testId;

  ListBuilder<String>? _unassignedRegionIds;
  ListBuilder<String> get unassignedRegionIds =>
      _$this._unassignedRegionIds ??= ListBuilder<String>();
  set unassignedRegionIds(ListBuilder<String>? unassignedRegionIds) =>
      _$this._unassignedRegionIds = unassignedRegionIds;

  ListBuilder<String>? _undetectedQuestionNumbers;
  ListBuilder<String> get undetectedQuestionNumbers =>
      _$this._undetectedQuestionNumbers ??= ListBuilder<String>();
  set undetectedQuestionNumbers(
          ListBuilder<String>? undetectedQuestionNumbers) =>
      _$this._undetectedQuestionNumbers = undetectedQuestionNumbers;

  ProfileResponseBuilder() {
    ProfileResponse._defaults(this);
  }

  ProfileResponseBuilder get _$this {
    final $v = _$v;
    if ($v != null) {
      _pages = $v.pages.toBuilder();
      _questionNumbers = $v.questionNumbers.toBuilder();
      _regions = $v.regions.toBuilder();
      _revision = $v.revision;
      _status = $v.status;
      _testId = $v.testId;
      _unassignedRegionIds = $v.unassignedRegionIds.toBuilder();
      _undetectedQuestionNumbers = $v.undetectedQuestionNumbers.toBuilder();
      _$v = null;
    }
    return this;
  }

  @override
  void replace(ProfileResponse other) {
    _$v = other as _$ProfileResponse;
  }

  @override
  void update(void Function(ProfileResponseBuilder)? updates) {
    if (updates != null) updates(this);
  }

  @override
  ProfileResponse build() => _build();

  _$ProfileResponse _build() {
    _$ProfileResponse _$result;
    try {
      _$result = _$v ??
          _$ProfileResponse._(
            pages: pages.build(),
            questionNumbers: questionNumbers.build(),
            regions: regions.build(),
            revision: BuiltValueNullFieldError.checkNotNull(
                revision, r'ProfileResponse', 'revision'),
            status: BuiltValueNullFieldError.checkNotNull(
                status, r'ProfileResponse', 'status'),
            testId: BuiltValueNullFieldError.checkNotNull(
                testId, r'ProfileResponse', 'testId'),
            unassignedRegionIds: unassignedRegionIds.build(),
            undetectedQuestionNumbers: undetectedQuestionNumbers.build(),
          );
    } catch (_) {
      late String _$failedField;
      try {
        _$failedField = 'pages';
        pages.build();
        _$failedField = 'questionNumbers';
        questionNumbers.build();
        _$failedField = 'regions';
        regions.build();

        _$failedField = 'unassignedRegionIds';
        unassignedRegionIds.build();
        _$failedField = 'undetectedQuestionNumbers';
        undetectedQuestionNumbers.build();
      } catch (e) {
        throw BuiltValueNestedFieldError(
            r'ProfileResponse', _$failedField, e.toString());
      }
      rethrow;
    }
    replace(_$result);
    return _$result;
  }
}

// ignore_for_file: deprecated_member_use_from_same_package,type=lint
