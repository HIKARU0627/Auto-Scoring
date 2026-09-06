// GENERATED CODE - DO NOT MODIFY BY HAND

part of 'profile_response.dart';

// **************************************************************************
// BuiltValueGenerator
// **************************************************************************

class _$ProfileResponse extends ProfileResponse {
  @override
  final BuiltList<PageFormatModel> pages;
  @override
  final BuiltList<RegionModel> regions;
  @override
  final int revision;
  @override
  final String status;
  @override
  final String testId;

  factory _$ProfileResponse([void Function(ProfileResponseBuilder)? updates]) =>
      (ProfileResponseBuilder()..update(updates))._build();

  _$ProfileResponse._(
      {required this.pages,
      required this.regions,
      required this.revision,
      required this.status,
      required this.testId})
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
        regions == other.regions &&
        revision == other.revision &&
        status == other.status &&
        testId == other.testId;
  }

  @override
  int get hashCode {
    var _$hash = 0;
    _$hash = $jc(_$hash, pages.hashCode);
    _$hash = $jc(_$hash, regions.hashCode);
    _$hash = $jc(_$hash, revision.hashCode);
    _$hash = $jc(_$hash, status.hashCode);
    _$hash = $jc(_$hash, testId.hashCode);
    _$hash = $jf(_$hash);
    return _$hash;
  }

  @override
  String toString() {
    return (newBuiltValueToStringHelper(r'ProfileResponse')
          ..add('pages', pages)
          ..add('regions', regions)
          ..add('revision', revision)
          ..add('status', status)
          ..add('testId', testId))
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

  ProfileResponseBuilder() {
    ProfileResponse._defaults(this);
  }

  ProfileResponseBuilder get _$this {
    final $v = _$v;
    if ($v != null) {
      _pages = $v.pages.toBuilder();
      _regions = $v.regions.toBuilder();
      _revision = $v.revision;
      _status = $v.status;
      _testId = $v.testId;
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
            regions: regions.build(),
            revision: BuiltValueNullFieldError.checkNotNull(
                revision, r'ProfileResponse', 'revision'),
            status: BuiltValueNullFieldError.checkNotNull(
                status, r'ProfileResponse', 'status'),
            testId: BuiltValueNullFieldError.checkNotNull(
                testId, r'ProfileResponse', 'testId'),
          );
    } catch (_) {
      late String _$failedField;
      try {
        _$failedField = 'pages';
        pages.build();
        _$failedField = 'regions';
        regions.build();
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
