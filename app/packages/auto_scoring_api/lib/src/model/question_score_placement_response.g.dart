// GENERATED CODE - DO NOT MODIFY BY HAND

part of 'question_score_placement_response.dart';

// **************************************************************************
// BuiltValueGenerator
// **************************************************************************

class _$QuestionScorePlacementResponse extends QuestionScorePlacementResponse {
  @override
  final NormalizedRectResponse? rect;
  @override
  final String target;

  factory _$QuestionScorePlacementResponse(
          [void Function(QuestionScorePlacementResponseBuilder)? updates]) =>
      (QuestionScorePlacementResponseBuilder()..update(updates))._build();

  _$QuestionScorePlacementResponse._({this.rect, required this.target})
      : super._();
  @override
  QuestionScorePlacementResponse rebuild(
          void Function(QuestionScorePlacementResponseBuilder) updates) =>
      (toBuilder()..update(updates)).build();

  @override
  QuestionScorePlacementResponseBuilder toBuilder() =>
      QuestionScorePlacementResponseBuilder()..replace(this);

  @override
  bool operator ==(Object other) {
    if (identical(other, this)) return true;
    return other is QuestionScorePlacementResponse &&
        rect == other.rect &&
        target == other.target;
  }

  @override
  int get hashCode {
    var _$hash = 0;
    _$hash = $jc(_$hash, rect.hashCode);
    _$hash = $jc(_$hash, target.hashCode);
    _$hash = $jf(_$hash);
    return _$hash;
  }

  @override
  String toString() {
    return (newBuiltValueToStringHelper(r'QuestionScorePlacementResponse')
          ..add('rect', rect)
          ..add('target', target))
        .toString();
  }
}

class QuestionScorePlacementResponseBuilder
    implements
        Builder<QuestionScorePlacementResponse,
            QuestionScorePlacementResponseBuilder> {
  _$QuestionScorePlacementResponse? _$v;

  NormalizedRectResponseBuilder? _rect;
  NormalizedRectResponseBuilder get rect =>
      _$this._rect ??= NormalizedRectResponseBuilder();
  set rect(NormalizedRectResponseBuilder? rect) => _$this._rect = rect;

  String? _target;
  String? get target => _$this._target;
  set target(String? target) => _$this._target = target;

  QuestionScorePlacementResponseBuilder() {
    QuestionScorePlacementResponse._defaults(this);
  }

  QuestionScorePlacementResponseBuilder get _$this {
    final $v = _$v;
    if ($v != null) {
      _rect = $v.rect?.toBuilder();
      _target = $v.target;
      _$v = null;
    }
    return this;
  }

  @override
  void replace(QuestionScorePlacementResponse other) {
    _$v = other as _$QuestionScorePlacementResponse;
  }

  @override
  void update(void Function(QuestionScorePlacementResponseBuilder)? updates) {
    if (updates != null) updates(this);
  }

  @override
  QuestionScorePlacementResponse build() => _build();

  _$QuestionScorePlacementResponse _build() {
    _$QuestionScorePlacementResponse _$result;
    try {
      _$result = _$v ??
          _$QuestionScorePlacementResponse._(
            rect: _rect?.build(),
            target: BuiltValueNullFieldError.checkNotNull(
                target, r'QuestionScorePlacementResponse', 'target'),
          );
    } catch (_) {
      late String _$failedField;
      try {
        _$failedField = 'rect';
        _rect?.build();
      } catch (e) {
        throw BuiltValueNestedFieldError(
            r'QuestionScorePlacementResponse', _$failedField, e.toString());
      }
      rethrow;
    }
    replace(_$result);
    return _$result;
  }
}

// ignore_for_file: deprecated_member_use_from_same_package,type=lint
