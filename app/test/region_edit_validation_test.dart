import 'package:flutter_test/flutter_test.dart';

import 'package:auto_scoring_app/api/sidecar_api_client.dart';
import 'package:auto_scoring_app/core/region_edit_validation.dart';

RegionModel _region() => RegionModel(
  (b) => b
    ..regionId = 'r-1'
    ..kind = RegionKind.question
    ..pageIndex = 0
    ..label = '問1'
    ..confirmed = false
    ..bbox.x0 = 0.1
    ..bbox.y0 = 0.1
    ..bbox.x1 = 0.3
    ..bbox.y1 = 0.2,
);

RegionEditValidation _validate({
  RegionModel? original,
  RegionKind kind = RegionKind.question,
  String labelText = '問1',
  String pageText = '1',
  String x0Text = '0.1',
  String y0Text = '0.1',
  String x1Text = '0.3',
  String y1Text = '0.2',
  String contentText = '',
}) => validateRegionEdit(
  original: original ?? _region(),
  kind: kind,
  labelText: labelText,
  pageText: pageText,
  x0Text: x0Text,
  y0Text: y0Text,
  x1Text: x1Text,
  y1Text: y1Text,
  contentText: contentText,
);

void main() {
  group('validateRegionEdit', () {
    test('妥当な入力は座標・種類・番号を反映した領域を返す', () {
      final result = _validate(
        kind: RegionKind.answerArea,
        labelText: '問2',
        pageText: '3',
        x0Text: '0.2',
        y0Text: '0.3',
        x1Text: '0.5',
        y1Text: '0.6',
        contentText: '  模範解答  ',
      );

      expect(result.error, isNull);
      final region = result.region!;
      expect(region.kind, RegionKind.answerArea);
      expect(region.label, '問2');
      expect(region.pageIndex, 2); // 1始まりの入力を0始まりに変換
      expect(region.bbox.x0, 0.2);
      expect(region.bbox.y0, 0.3);
      expect(region.bbox.x1, 0.5);
      expect(region.bbox.y1, 0.6);
      expect(region.text, '模範解答');
    });

    test('空欄のテキストは null になる', () {
      final result = _validate(contentText: '   ');
      expect(result.region!.text, isNull);
    });

    test('ページ番号が0以下ならエラー', () {
      final result = _validate(pageText: '0');
      expect(result.region, isNull);
      expect(result.error, isNotNull);
    });

    test('ページ番号が数値でなければエラー', () {
      final result = _validate(pageText: 'abc');
      expect(result.region, isNull);
      expect(result.error, isNotNull);
    });

    test('座標が右下が左上より小さいとエラー', () {
      final result = _validate(x0Text: '0.5', x1Text: '0.3');
      expect(result.region, isNull);
      expect(result.error, isNotNull);
    });

    test('座標が0〜1の範囲外ならエラー', () {
      final result = _validate(x1Text: '1.5');
      expect(result.region, isNull);
      expect(result.error, isNotNull);
    });

    test('座標が文字列 "NaN" でもエラーとして拒否する', () {
      // `double.tryParse('NaN')` returns a non-null `double.nan`, and every
      // comparison against it (`<`, `>`, `>=`) is false -- so without the
      // explicit `isFinite` check every one of the ordering/range tests above
      // would silently pass (Issue #16 review round 5).
      final result = _validate(x0Text: 'NaN');
      expect(result.region, isNull);
      expect(result.error, isNotNull);
    });

    test('設問番号が空欄ならエラー', () {
      final result = _validate(labelText: '   ');
      expect(result.region, isNull);
      expect(result.error, isNotNull);
    });
  });
}
