import 'dart:convert';
import 'dart:io';

import 'package:flutter_test/flutter_test.dart';
import 'package:ffr_vision_studio/services/engine_overlay.dart';

void main() {
  TestWidgetsFlutterBinding.ensureInitialized();
  test('clean install stages full catalog/browser and fixes both demo table names', () async {
    final dir = await Directory.systemTemp.createTemp('ffr-clean-overlay-');
    addTearDown(() async { if (dir.existsSync()) await dir.delete(recursive: true); });
    for (final rel in ['tools/make_vision_mod.py', 'tools/ffbe_audio.py']) {
      final file = File('${dir.path}/$rel');
      await file.parent.create(recursive: true);
      final table = rel.contains('audio')
          ? 'Asset/Sound/CDT_SoundCueSheetAsset_Demo'
          : 'Asset/Skill/CDT_SkillAsset_Demo';
      await file.writeAsString('TABLE = "$table"\n');
    }
    await EngineOverlay.apply(dir.path);
    await EngineOverlay.apply(dir.path); // repeat is safe and does not erase data
    final cat = jsonDecode(await File('${dir.path}/build/devui/ffr_catalog.json').readAsString()) as Map;
    expect(cat['schema'], 9);
    expect((cat['skills'] as List).length, 1167);
    expect((cat['passives'] as List).length, 378);
    expect((await File('${dir.path}/tools/make_vision_mod.py').readAsString()).contains('CDT_SkillAsset_Prod'), true);
    expect((await File('${dir.path}/tools/ffbe_audio.py').readAsString()).contains('CDT_SoundCueSheetAsset_Prod'), true);
    final html = await File('${dir.path}/tools/devui/web/dist/index.html').readAsString();
    expect(html.contains('/assets/'), true);
  });
}