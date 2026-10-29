#!/usr/bin/env python3
"""Stage and optionally build original FFBE Ultimate Power Rain Fire in FFR.

Run from repo as: .venv/Scripts/python.exe tools/rain_fire_ffbe.py --build
The script NEVER installs a game mod. It uses the project's prepared FFBE
presentation pipeline; it does not substitute a native FFR Fire animation.
"""
from __future__ import annotations

import argparse
from copy import deepcopy
import hashlib
import json
import os
import shutil
from pathlib import Path
import subprocess
import sys
import audio_source_option

ROOT = Path(__file__).resolve().parents[1]
TOOLS = ROOT / 'tools'
sys.path.insert(0, str(TOOLS))

FORM = '100045927'
UNIT_ID = 13501
SKILL_ID = 485100
SOURCE_ID = '1503020'
GROUP_ID = '604950200'
EXPECTED_HITS = [42, 62, 82, 102, 122, 142, 162, 182]
STAGE = ROOT / 'build/diagnostics/rain-original-ffbe-fire'


class Blocked(RuntimeError):
    pass


def read(path):
    return json.loads(Path(path).read_text(encoding='utf-8-sig'))


def save(path, value):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + '.tmp')
    tmp.write_text(json.dumps(value, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
    os.replace(tmp, path)


def source_identity(unit_json):
    forms = unit_json.get('forms', {})
    if isinstance(forms, dict):
        entries = list(forms.values())
    elif isinstance(forms, list):
        entries = forms
    else:
        entries = []
    matches = []
    for form in entries:
        if not isinstance(form, dict):
            continue
        # The FFBE dump includes skill records at each rarity/level.
        def walk(value):
            if isinstance(value, dict):
                if str(value.get('id')) == SOURCE_ID and value.get('attack_count') == [8]:
                    matches.append(value)
                for sub in value.values(): walk(sub)
            elif isinstance(value, list):
                for sub in value: walk(sub)
        walk(form)
    if not matches:
        raise Blocked('Original Fire source (FFBE ability 1503020) missing from unit.json')
    ability = matches[0]
    frames = ability.get('attack_frames') or []
    if not frames or list(frames[0]) != EXPECTED_HITS:
        raise Blocked(f'Unexpected source hit frames: {frames!r}')
    cost = ability.get('cost', {}).get('MP')
    if cost != 150:
        raise Blocked(f'Unexpected original MP cost: {cost!r}')
    return ability


def candidates():
    custom = os.environ.get('FFR_UNIT_SPEC')
    if custom:
        yield Path(custom)
    yield ROOT/'mods/EstherTsukiko/units.json'
    local = Path(os.environ.get('LOCALAPPDATA') or (Path.home()/'AppData/Local'))
    yield local/'FFR Vision Studio/engine/mods/EstherTsukiko/units.json'
    yield ROOT/'build/diagnostics/rain-units.json'


def find_roster(path_override=None):
    options = [Path(path_override)] if path_override else list(candidates())
    good = []
    for path in options:
        if not path.is_file(): continue
        data = read(path)
        if not isinstance(data, list) or not data: continue
        units = [u for u in data if isinstance(u, dict) and u.get('id') == UNIT_ID]
        if len(units) != 1: continue
        if str(units[0].get('ffbe', {}).get('id')) != FORM: continue
        skill = units[0].get('skills', {}).get(str(SKILL_ID))
        if not isinstance(skill, dict): continue
        # Prefer the actual converted configuration over an older native clone.
        priority = 0 if skill.get('mechanics') == 'converted' else 1
        good.append((priority, path, data))
    if not good:
        raise Blocked('No nonempty Vision roster containing Rain skill 485100. Pass --spec <units.json>.')
    good.sort(key=lambda pair: pair[0])
    return good[0][1], deepcopy(good[0][2])


def get_snapshot():
    """Build a real JP-client ability snapshot from the recovered Memorial DB.

    Avoid requiring a preexisting Studio native kit. We intentionally stage
    only the eight-hit damage component for this FIRST playable visual test.
    The resistance/imbue components stay in source provenance; they are not
    misrepresented as implemented.
    """
    import rain_memorial_bridge as bridge
    db = ROOT/'build/diagnostics/ffbe-memorial/memorial-index.sqlite'
    unit = ROOT/'units/ffbe/ultimatepowerrain/unit.json'
    source = bridge.load_source(db, unit)
    snapshot = bridge.make_snapshot(source, damage_only=True, database_path=str(db))
    kit_file = ROOT / f'data/ffbe/native_kits/{FORM}.json'
    scratch = STAGE/'jp-live-cache'
    if kit_file.is_file():
        prior = read(kit_file)
        existing = prior.get('profiles',{}).get(snapshot['root'],{}).get('snapshot')
        if existing != snapshot:
            raise Blocked('A different Rain native kit already exists. Do not overwrite it; review source identity.')
        # Still populate the scratch catalog for source-matched presentation.
        scratch.mkdir(parents=True,exist_ok=True)
        for name, rows in bridge.make_cache(source).items():
            bridge_file = scratch/(name+'.json')
            bridge_file.write_text(json.dumps({'table':name,'file':'JP Memorial SQLite',
                                               'rows':rows},ensure_ascii=False),encoding='utf-8')
    else:
        bridge.write_prepared_source(source,snapshot,scratch,kit_file)
        print('CREATED verified native kit from original Memorial data:',kit_file,flush=True)
    # These are isolated cache files. Never replace Vision Studio's live client
    # cache or cross-contaminate a different source region.
    sys.path.insert(0,str(ROOT/'tools/devui'))
    import ffbe_live
    ffbe_live.OUT=str(scratch)
    from ffbe_effects import catalog
    catalog.clear_cache()
    return snapshot['root'],snapshot


def hydrate_original_media():
    """Locate previously recovered FFBE game assets and verify each checksum.

    No original media is bundled or downloaded. Existing local recovered files
    are copied into the established particle renderer's source directory.
    """
    manifest_path = ROOT / f'build/diagnostics/ffbe-memorial/character-{FORM}-media/media-manifest.json'
    if not manifest_path.is_file():
        raise Blocked(f'Original media manifest missing: {manifest_path}')
    manifest = read(manifest_path)
    asset_root = manifest_path.parent
    sources = ROOT/'build/ffbe_cpk/effects_dec'
    if manifest.get('missingParticles') or manifest.get('missingDependencies'):
        raise Blocked('Original FFBE media manifest reports missing particles or dependencies')
    items = manifest.get('assets', {})
    if 'eff_explosion_red.bmb' not in items:
        raise Blocked('Original red explosion asset not documented by the recovered media manifest')
    files = {}
    for source in asset_root.rglob('*'):
        if source.is_file() and source.name in items and source.name not in files:
            files[source.name] = source
    missing = []
    copied = 0
    for name, record in items.items():
        expected = record.get('sha256')
        dst = sources/name
        src = dst if dst.is_file() else files.get(name)
        if src is None:
            missing.append(name)
            continue
        with src.open('rb') as handle:
            actual = hashlib.file_digest(handle, 'sha256').hexdigest()
        if actual != expected:
            raise Blocked(f'FFBE media hash mismatch for {name}: {src}')
        if not dst.is_file():
            sources.mkdir(parents=True,exist_ok=True)
            shutil.copy2(src,dst)
            copied += 1
    if missing:
        raise Blocked('FFBE effect source files are not present in the recovered staging folder:\n  '
                      + '\n  '.join(missing[:20]) + ('\n  ...' if len(missing)>20 else ''))
    print(f'Original FFBE media verified: {len(items)} files, {copied} staged from diagnostics')


def source_group_check(snapshot):
    # Use the project's source-aware effect-group decoder, rather than guessing
    # timing based on the game's generic Fire attack.
    from ffbe_effects import prepare_vision
    data = prepare_vision.timeline(snapshot, source_matched=True)
    proven = [g for p in data.get('provenance', []) for g in p.get('catalog', {}).get('groups', [])
              if str(g.get('groupId')) == GROUP_ID]
    if not proven:
        raise Blocked(f'Original FFBE explosion effect group {GROUP_ID} is not present in the retained components.')
    sounds = [s for s in data.get('sounds', []) if s.get('cueId') is not None]
    explosion_sounds = [s for g in proven for s in (g.get('group') or {}).get('sounds', [])]
    spawns = [s for s in data.get('spawns', []) if str(s.get('groupId')) == GROUP_ID]
    if len(spawns) < 8:
        raise Blocked(f'Expected eight original FFBE explosion spawns, found {len(spawns)}')
    if len(explosion_sounds) < 8:
        raise Blocked(f'Expected eight original explosion sound cues, found {len(explosion_sounds)}')
    if not sounds:
        raise Blocked('No original sound cues decoded; refusing to label a silent conversion complete.')
    return data, spawns, sounds


def stage_roster(roster, snapshot, source_key, original_ability):
    current = deepcopy(roster)
    rain = next(u for u in current if u.get('id') == UNIT_ID)
    skill = rain['skills'][str(SKILL_ID)]
    # The native-clone source is not the FFBE action. Replace the skill's
    # mechanics source, preserving the other 6 visions and all other skills.
    skill['mechanics'] = 'converted'
    # Match the same reviewed converter used during source preflight. Without
    # this the builder may select a different (nonreviewed) effect policy.
    from ability_converter.reviewed import VERSION as REVIEWED_VERSION
    skill['effectPolicy'] = REVIEWED_VERSION
    skill['conversionSource'] = deepcopy(snapshot)
    skill['motion'] = 'magic_attack'
    skill['descAuto'] = True
    skill['ffbe_presentation'] = True
    skill.setdefault('set', {})['Cost'] = original_ability['cost']['MP']
    # Remove FFR-native Fire modifiers: the source converter owns damage,
    # hit ratios, target and elemental properties.
    for field in ('magnification', 'hitCount', 'hitDamageRatioList',
                  'breakDamageValue', 'criticalHitRate', 'element', 'DamageType'):
        skill['set'].pop(field, None)
    skill.pop('visuals', None)
    skill.pop('from', None)
    source_key_from_skill = skill['conversionSource'].get('root')
    if source_key_from_skill != source_key:
        raise Blocked('Staged Fire skill lost original snapshot identity')
    # Leave original user source configuration untouched.
    path = STAGE / 'units.json'
    save(path, current)
    return path


def prepare_visuals(source_key):
    """Render original particle art; use actual FFBE SE audio only if supplied.

    The legacy pipeline assumes S:/FFBE JP Data Export/public/SE.acb. When that
    original bank is unavailable, prepare a *visual-only* test and preserve the
    source cues as diagnostics. Never substitute FFR's generic Fire bank.
    """
    from ffbe_effects import prepare_vision
    available = audio_source_option.ensure_local_bank(ROOT)
    audio_present = available is not None
    if audio_present:
        print('Original FFBE SE.acb available:', available, flush=True)
    else:
        print('ORIGINAL AUDIO UNAVAILABLE: SE.acb was not found. Preparing FFBE visuals only.', flush=True)
        print('Original FFBE cue IDs remain recorded; they will NOT play in this build.', flush=True)
        # No bogus/synthetic sound cues: the renderer can still convert .bmb
        # artwork and write an explicit omissions manifest for each source ID.
        class SilentSource:
            def selection(self, ids):
                return {'cues': {}, 'recordings': [],
                        'omitted': {str(i): 'Original FFBE SE.acb not available' for i in ids}}
        original_audio_library = prepare_vision.audio_library
        prepare_vision.audio_library = lambda name: SilentSource()
    stage_presentation = STAGE/'presentation'
    stage_presentation.mkdir(parents=True, exist_ok=True)
    try:
        prepare_vision.prepare(
            [FORM], [source_key],
            detect_scene=True, merge_existing=False, make_previews=False,
            universal=True,
            manifest_out=str(stage_presentation/(FORM+'.json')),
            host_preferences={},
        )
    finally:
        if not audio_present:
            prepare_vision.audio_library = original_audio_library
    path = stage_presentation / (FORM+'.json')
    bundle = read(path)
    entry = bundle.get('moves', {}).get(source_key)
    if not entry:
        raise Blocked('Original FFBE presentation source was not written')
    if not entry.get('visuals'):
        raise Blocked('Converted original FFBE particle tracks are missing')
    if not entry.get('sounds'):
        raise Blocked('Original FFBE sound-cue metadata missing from preparation')
    if not audio_present:
        # Modify the isolated staged presentation ONLY. The source clock and
        # FFBE cues remain in the pre-mute source evidence file.
        evidence = STAGE/'original-source-sounds.json'
        save(evidence, {'sourceKey':source_key, 'sounds':entry['sounds'],
                        'cast':entry.get('cast'), 'reason':'SE.acb absent'})
        entry['sounds'] = []
        entry.pop('cast', None)
        entry['soundOmissions'] = {str(s['cueId']): 'Original FFBE SE.acb absent'
                                   for s in read(evidence)['sounds']}
        save(path, bundle)
        print('Visual-only stage created; original cue references saved to:',evidence,flush=True)
    return entry, audio_present, stage_presentation


def check_built_artifacts(audio_present):
    patch = read(ROOT/'build/visions_mod/patch.json')
    rows = [entry.get('set', {}) for table in patch.get('tables', [])
            for entry in table.get('add', []) if isinstance(entry, dict)]
    if len(patch.get('tables', [])) < 20 or len(rows) < 90:
        raise Blocked('Incomplete seven-Vision build; do not install this package')
    matches = [r for r in rows if str(r.get('ID')) == str(SKILL_ID) and 'playSequencerId' in r]
    if len(matches) != 1:
        raise Blocked(f'Expected one Rain Fire skill 485100, found {len(matches)}')
    fire = matches[0]
    if fire.get('Cost') != 150:
        raise Blocked(f'Original MP cost not preserved: {fire.get("Cost")}')
    if fire.get('hitCount') != 8:
        raise Blocked(f'Eight-hit mechanics not preserved: {fire.get("hitCount")}')
    if fire.get('playSequencerId') != 485101:
        raise Blocked(f'Wrong custom Fire sequence: {fire.get("playSequencerId")}')
    schedule = read(ROOT/'build/visions_mod/SEQ_Battle_485101_Master-events.json')
    event_types = [item.get('set', {}).get('EventType') for item in schedule.get('bytecode', [])]
    if 'SsActorSpawnSpriteStudioActor' not in event_types:
        raise Blocked('Packaged Fire sequence is missing imported FFBE particle actors')
    if audio_present and 'SoundPlayHitSound' not in event_types:
        raise Blocked('Packaged Fire sequence is missing original FFBE sound cues')
    for ext in ('.utoc', '.ucas', '.pak'):
        filename = ROOT/'build/out'/('zzz_EstherTsukiko_P'+ext)
        if not filename.is_file() or not filename.stat().st_size:
            raise Blocked(f'Built mod package is incomplete: {filename}')
        if ext == '.ucas' and filename.stat().st_size < 1_000_000:
            raise Blocked(f'The seven-Vision cooked package is suspiciously small: {filename}')
    print('PASS: 150 MP; 8 FFBE-derived hits; original FFBE particle event(s) authored.')
    print('AUDIO:', 'Original FFBE cues authored (game test pending)' if audio_present else 'NOT INCLUDED (original SE.acb missing)')
    print('PENDING (not implemented): Fire resistance reduction, imbue removal, Fire imbue.')
    print('PASS: package complete; NOT installed. Actual game playback still needs testing.')


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--spec', type=Path, help='Exact units.json roster to stage')
    parser.add_argument('--build', action='store_true', help='Prepare original graphics/audio and build a mod without installing')
    args = parser.parse_args(argv)
    ability = source_identity(read(ROOT/'units/ffbe/ultimatepowerrain/unit.json'))
    spec_path, roster = find_roster(args.spec)
    source_key, snapshot = get_snapshot()
    print('Source roster:', spec_path)
    print('FFBE original damage component:', source_key, 'MP:', ability['cost']['MP'], 'hits:', ability['attack_frames'][0])
    print('First playable test: authentic FFBE explosion graphics and sound; three secondary mechanic groups intentionally pending')
    from ability_converter import commands
    resolved = commands.from_snapshot(snapshot, reviewed=True)
    if not resolved.get('supported'):
        raise Blocked('Eight-hit FFBE damage conversion is not supported by the available native adapter: '
                      + '; '.join(map(str, resolved.get('issues', []))))
    if args.build:
        hydrate_original_media()
    data, spawns, sounds = source_group_check(snapshot)
    print(f'Original group {GROUP_ID}: {len(spawns)} particle spawns, {len(sounds)} source sound cues')
    if not args.build:
        print('Preflight PASS. Use --build to prepare and package the original FFBE skill.')
        return 0
    entry, audio_present, presentation_dir = prepare_visuals(source_key)
    print(f'Prepared {len(entry["visuals"])} original particle tracks; original sounds:',
          'present' if audio_present else 'omitted pending source bank')
    staged = stage_roster(roster, snapshot, source_key, ability)
    env = os.environ.copy()
    env['FFR_UNIT_SPEC'] = str(staged)
    env['FFR_PRESENTATION_DIR'] = str(presentation_dir)
    env['FFR_ALLOW_NATIVE_ICON_FALLBACK'] = '1'  # explicit test-only native icons; logged per missing source
    print('Building using a staged seven-Vision roster; original spec untouched...')
    proc = subprocess.run([sys.executable, str(TOOLS/'make_vision_mod.py'), '--no-install'],
                          cwd=str(ROOT), env=env)
    if proc.returncode:
        raise Blocked('Generator failed. Check missing sprite/icon assets or source conversion errors above. '
                      'No game mod was installed.')
    check_built_artifacts(audio_present)
    return 0


if __name__ == '__main__':
    try:
        sys.exit(main())
    except (Blocked, FileNotFoundError, ValueError) as exc:
        print('\nBLOCKED: ' + str(exc), file=sys.stderr)
        sys.exit(2)
