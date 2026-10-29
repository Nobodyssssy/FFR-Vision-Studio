import 'dart:convert';
import 'dart:io';

import 'package:crypto/crypto.dart';
import 'package:flutter/services.dart';
import 'package:path/path.dart' as p;

/// Small, content-verified compatibility overlay for the host-downloaded engine.
/// Only browser UI, catalog fallback, and two native table names are updated.
/// No extracted game assets, mods, or user configuration are modified.
class EngineOverlay {
  static Future<void> apply(String engineDirectory) async {
    final root = p.normalize(p.absolute(engineDirectory));
    final engine = Directory(root);
    if (!engine.existsSync()) {
      throw StateError('The downloaded Studio engine folder is missing.');
    }
    final manifest = jsonDecode(await rootBundle.loadString(
      'assets/engine_overlay/manifest.json')) as Map<String, dynamic>;
    if (manifest['schema'] != 1) {
      throw const FormatException('Unsupported bundled engine overlay.');
    }
    final entries = (manifest['entries'] as List).cast<Map<String, dynamic>>();
    for (final item in entries) {
      final name = item['file'] as String;
      final destination = item['destination'] as String;
      final expected = item['sha256'] as String;
      // Manifest is built at release time; still enforce an explicit destination boundary.
      final allowed = destination == 'data/ffr_catalog.json' ||
          destination == 'build/devui/ffr_catalog.json' ||
          destination == 'tools/devui/web/dist/index.html' ||
          (destination.startsWith('tools/devui/web/dist/assets/') &&
              RegExp(r'^[A-Za-z0-9._-]+$').hasMatch(p.basename(destination)));
      if (!allowed || !RegExp(r'^[A-Za-z0-9._-]+$').hasMatch(name)) {
        throw const FormatException('Invalid engine overlay path.');
      }
      final data = await rootBundle.load('assets/engine_overlay/$name');
      final bytes = data.buffer.asUint8List(data.offsetInBytes, data.lengthInBytes);
      if (sha256.convert(bytes).toString() != expected) {
        throw StateError('Bundled engine overlay checksum failed for $name.');
      }
      final dest = File(p.joinAll([root, ...destination.split('/')]));
      if (!p.isWithin(root, p.normalize(p.absolute(dest.path)))) {
        throw const FormatException('Engine overlay escapes its destination.');
      }
      // Preserve an existing valid full-release catalog generated from the user's
      // actual installation; use our recovered schema-9 reference as a fallback.
      if (destination.endsWith('ffr_catalog.json') && dest.existsSync()) {
        try {
          final current = jsonDecode(await dest.readAsString()) as Map<String, dynamic>;
          if (current['schema'] == 9 &&
              (current['skills'] as List).length == 1167 &&
              (current['passives'] as List).length == 378) {
            continue;
          }
        } catch (_) { /* replace invalid fallback */ }
      }
      if (dest.existsSync() && sha256.convert(await dest.readAsBytes()).toString() == expected) {
        continue;
      }
      await dest.parent.create(recursive: true);
      await dest.writeAsBytes(bytes, flush: true);
    }
    await _repairTableReferences(root);
  }

  static Future<void> _repairTableReferences(String root) async {
    const replacements = <String, (String, String)>{
      'tools/make_vision_mod.py':
          ('Asset/Skill/CDT_SkillAsset_Demo', 'Asset/Skill/CDT_SkillAsset_Prod'),
      'tools/ffbe_audio.py':
          ('Asset/Sound/CDT_SoundCueSheetAsset_Demo', 'Asset/Sound/CDT_SoundCueSheetAsset_Prod'),
    };
    for (final entry in replacements.entries) {
      final file = File(p.joinAll([root, ...entry.key.split('/')]));
      if (!await file.exists()) {
        throw StateError('Downloaded engine is missing ${entry.key}.');
      }
      final contents = await file.readAsString();
      final (oldValue, newValue) = entry.value;
      if (contents.contains(newValue) && !contents.contains(oldValue)) {
        continue;
      }
      if (!contents.contains(oldValue)) {
        throw StateError('Unknown engine table mapping in ${entry.key}; no changes made.');
      }
      final backup = File('${file.path}.before-full-release-overlay.bak');
      if (!await backup.exists()) {
        await file.copy(backup.path);
      }
      final updated = contents.replaceAll(oldValue, newValue);
      await file.writeAsString(updated, flush: true);
      if (!(await file.readAsString()).contains(newValue)) {
        throw StateError('Could not update table mapping in ${entry.key}.');
      }
    }
  }
}