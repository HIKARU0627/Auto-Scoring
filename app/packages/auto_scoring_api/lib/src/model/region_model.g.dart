// GENERATED CODE - DO NOT MODIFY BY HAND

part of 'region_model.dart';

// **************************************************************************
// BuiltValueGenerator
// **************************************************************************

class _$RegionModel extends RegionModel {
  @override
  final NormalizedBBoxModel bbox;
  @override
  final bool? confirmed;
  @override
  final RegionKind kind;
  @override
  final String label;
  @override
  final int pageIndex;
  @override
  final String regionId;
  @override
  final String? text;

  factory _$RegionModel([void Function(RegionModelBuilder)? updates]) =>
      (RegionModelBuilder()..update(updates))._build();

  _$RegionModel._(
      {required this.bbox,
      this.confirmed,
      required this.kind,
      required this.label,
      required this.pageIndex,
      required this.regionId,
      this.text})
      : super._();
  @override
  RegionModel rebuild(void Function(RegionModelBuilder) updates) =>
      (toBuilder()..update(updates)).build();

  @override
  RegionModelBuilder toBuilder() => RegionModelBuilder()..replace(this);

  @override
  bool operator ==(Object other) {
    if (identical(other, this)) return true;
    return other is RegionModel &&
        bbox == other.bbox &&
        confirmed == other.confirmed &&
        kind == other.kind &&
        label == other.label &&
        pageIndex == other.pageIndex &&
        regionId == other.regionId &&
        text == other.text;
  }

  @override
  int get hashCode {
    var _$hash = 0;
    _$hash = $jc(_$hash, bbox.hashCode);
    _$hash = $jc(_$hash, confirmed.hashCode);
    _$hash = $jc(_$hash, kind.hashCode);
    _$hash = $jc(_$hash, label.hashCode);
    _$hash = $jc(_$hash, pageIndex.hashCode);
    _$hash = $jc(_$hash, regionId.hashCode);
    _$hash = $jc(_$hash, text.hashCode);
    _$hash = $jf(_$hash);
    return _$hash;
  }

  @override
  String toString() {
    return (newBuiltValueToStringHelper(r'RegionModel')
          ..add('bbox', bbox)
          ..add('confirmed', confirmed)
          ..add('kind', kind)
          ..add('label', label)
          ..add('pageIndex', pageIndex)
          ..add('regionId', regionId)
          ..add('text', text))
        .toString();
  }
}

class RegionModelBuilder implements Builder<RegionModel, RegionModelBuilder> {
  _$RegionModel? _$v;

  NormalizedBBoxModelBuilder? _bbox;
  NormalizedBBoxModelBuilder get bbox =>
      _$this._bbox ??= NormalizedBBoxModelBuilder();
  set bbox(NormalizedBBoxModelBuilder? bbox) => _$this._bbox = bbox;

  bool? _confirmed;
  bool? get confirmed => _$this._confirmed;
  set confirmed(bool? confirmed) => _$this._confirmed = confirmed;

  RegionKind? _kind;
  RegionKind? get kind => _$this._kind;
  set kind(RegionKind? kind) => _$this._kind = kind;

  String? _label;
  String? get label => _$this._label;
  set label(String? label) => _$this._label = label;

  int? _pageIndex;
  int? get pageIndex => _$this._pageIndex;
  set pageIndex(int? pageIndex) => _$this._pageIndex = pageIndex;

  String? _regionId;
  String? get regionId => _$this._regionId;
  set regionId(String? regionId) => _$this._regionId = regionId;

  String? _text;
  String? get text => _$this._text;
  set text(String? text) => _$this._text = text;

  RegionModelBuilder() {
    RegionModel._defaults(this);
  }

  RegionModelBuilder get _$this {
    final $v = _$v;
    if ($v != null) {
      _bbox = $v.bbox.toBuilder();
      _confirmed = $v.confirmed;
      _kind = $v.kind;
      _label = $v.label;
      _pageIndex = $v.pageIndex;
      _regionId = $v.regionId;
      _text = $v.text;
      _$v = null;
    }
    return this;
  }

  @override
  void replace(RegionModel other) {
    _$v = other as _$RegionModel;
  }

  @override
  void update(void Function(RegionModelBuilder)? updates) {
    if (updates != null) updates(this);
  }

  @override
  RegionModel build() => _build();

  _$RegionModel _build() {
    _$RegionModel _$result;
    try {
      _$result = _$v ??
          _$RegionModel._(
            bbox: bbox.build(),
            confirmed: confirmed,
            kind: BuiltValueNullFieldError.checkNotNull(
                kind, r'RegionModel', 'kind'),
            label: BuiltValueNullFieldError.checkNotNull(
                label, r'RegionModel', 'label'),
            pageIndex: BuiltValueNullFieldError.checkNotNull(
                pageIndex, r'RegionModel', 'pageIndex'),
            regionId: BuiltValueNullFieldError.checkNotNull(
                regionId, r'RegionModel', 'regionId'),
            text: text,
          );
    } catch (_) {
      late String _$failedField;
      try {
        _$failedField = 'bbox';
        bbox.build();
      } catch (e) {
        throw BuiltValueNestedFieldError(
            r'RegionModel', _$failedField, e.toString());
      }
      rethrow;
    }
    replace(_$result);
    return _$result;
  }
}

// ignore_for_file: deprecated_member_use_from_same_package,type=lint
