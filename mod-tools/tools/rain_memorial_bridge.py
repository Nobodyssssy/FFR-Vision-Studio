"""Make a source-traceable, minimal JP_CLIENT kit/cache for one original FFBE ability.

Uses records from the JP Memorial SQLite database, never guessed FFR donors.
The first playable visual test uses only the first FFBE damage component; the
remaining mechanics remain explicitly unimplemented, not silently advertised.
"""
from __future__ import annotations

from copy import deepcopy
import json
from pathlib import Path
import sqlite3

FORM = '100045927'
ABILITY = '1503020'
GROUPS = ('604950200','5028062','5028071','5031331','3000241')
SOURCE = 'JP_CLIENT'
ROOT_KEY = f'{SOURCE}/ability/{ABILITY}'
SCHEMA = 'ffbe-ffr-source/1'


class SourceError(ValueError):
    pass


def lookup(conn, source, record_id):
    matches = conn.execute('SELECT payload FROM records WHERE source=? AND record_id=?',
                           (source, str(record_id))).fetchall()
    if len(matches) != 1:
        raise SourceError(f'Expected exactly one JP Memorial {source} {record_id}; found {len(matches)}')
    row = json.loads(matches[0][0])
    if not isinstance(row,dict):
        raise SourceError(f'Invalid {source} {record_id} payload')
    return row


def load_source(db_path, unit_path):
    from pathlib import Path
    db_path, unit_path = Path(db_path), Path(unit_path)
    if not db_path.is_file() or not unit_path.is_file():
        raise SourceError(f'Original JP Memorial database or FFBE unit is missing: {db_path}, {unit_path}')
    unit = json.loads(unit_path.read_text(encoding='utf-8-sig'))
    forms=unit.get('forms',{})
    if not isinstance(forms,dict):
        raise SourceError('FFBE source must contain a forms dictionary')
    original = next((s for f in forms.values() for s in f.get('skills',[])
                     if str(s.get('id'))==ABILITY),None)
    if original is None:
        raise SourceError('Original FFBE skill 1503020 absent from unit.json')
    with sqlite3.connect(f'file:{db_path.as_posix()}?mode=ro',uri=True) as conn:
        ability = lookup(conn,'abilities',ABILITY)
        if str(ability.get('Ga5V42LZ'))!=ABILITY:
            raise SourceError('JP Memorial ability identity mismatch')
        if (str(ability.get('8cY9hejo'))!='150' or original.get('cost',{}).get('MP') != 150
                or original.get('attack_frames') != [[42,62,82,102,122,142,162,182]]):
            raise SourceError('FFBE Fire cost / eight hit timing disagrees with source dump')
        raw_groups = ability.get('5A8SmwyC','')
        names = [p.split(':')[1] for p in raw_groups.split('&') if ':' in p]
        if tuple(names) != GROUPS:
            raise SourceError('JP Memorial Fire effect-group IDs differ from original expected data')
        group_rows = [lookup(conn,'effect_groups',gid) for gid in GROUPS]
        # The default ability preparation has two additional cast effect groups.
        for extra in ('9000110','9000120'):
            try: group_rows.append(lookup(conn,'effect_groups',extra))
            except SourceError: pass
        effect_ids = set()
        for group in group_rows:
            for component in (group.get('5A8SmwyC') or '').replace('&',',').split(','):
                fields=component.split(':')
                if len(fields)>1 and fields[1].isdigit(): effect_ids.add(fields[1])
        effects = [lookup(conn,'effects',eid) for eid in sorted(effect_ids)]
    explosion = next(g for g in group_rows if g['qIy86WvJ']==GROUPS[0])
    particles = [p for p in explosion['5A8SmwyC'].split(',') if p]
    cues = [p for p in explosion['1fVZ3rKd'].split(',') if p]
    if len(particles)!=8 or len(cues)!=8 or not all(':5000590:' in p for p in particles):
        raise SourceError('The original group is not eight red-explosion spawns and eight sounds')
    explosion_effect=next((e for e in effects if e.get('h5t4yBm2')=='5000590'),None)
    if explosion_effect is None or explosion_effect.get('2HjxCGo6')!='eff_explosion_red.bmb':
        raise SourceError('Original explosion graphic identity differs from expected BMB file')
    return {'unit':original,'ability':ability,'groups':group_rows,'effects':effects,
            'particleCount':len(particles),'cueCount':len(cues)}


def make_snapshot(source, *, damage_only=True, database_path=''):
    """Original FFBE damage component only for the first *playable* visual test.

    Full original group provenance is preserved in _master and on disk. Do not
    label secondary resistance, dispel or imbue mechanics as implemented.
    """
    original=source['unit']; ability=source['ability']
    groups=ability['5A8SmwyC']
    frames=[int(p.split(':')[0]) for p in groups.split('&')]
    if frames != [40]*5:
        raise SourceError('Unexpected original group timing')
    effects=deepcopy(original['effects_raw'])
    if len(effects)!=4 or effects[0][2]!=15:
        raise SourceError('Unexpected original FFBE Fire component structure')
    # Damage-only in the first playable asset test; the remaining original
    # mechanical components are preserved separately in sourceEvidence.
    if damage_only:
        effects=effects[:1]
    hit=[item.split(':') for item in ability['a9DvZ70c'].split('-')]
    if len(hit)!=8 or [int(x[0]) for x in hit]!=original['attack_frames'][0]:
        raise SourceError('Source hit frames disagree with master ability')
    weights=[int(x[1]) for x in hit]
    if sum(weights)!=100:
        raise SourceError('FFBE hit weights must sum to 100')
    data={'name':original['name'], 'effects_raw':effects,
          'attack_frames':deepcopy(original['attack_frames']),
          'attack_damage':[weights], 'element_inflict':deepcopy(original['element']),
          'mp_cost':150, 'move_type':0, 'effect_frames':[frames],
          '_master':{'effect_frames':groups, 'attack_frames':ability['a9DvZ70c']}}
    record={'source':SOURCE,'kind':'ability','id':ABILITY,'data':data,
            'path':str(database_path), 'level':None, 'issues':[]}
    return {'schemaVersion':SCHEMA,'root':ROOT_KEY,'records':[record]}


def make_kit(snapshot, source):
    return {'kit':{'name':'Ultimate Power Rain',
                   'entries':[{'kind':'ABILITY','status':'ready','sourceKey':ROOT_KEY,
                               'name':source['unit']['name']}]},
            'profiles':{ROOT_KEY:{'snapshot':snapshot}},
            'provenance':{'format':'JP Memorial SQLite + FFBE unit.json',
                          'scope':'eight-hit damage and original presentation ONLY',
                          'notImplemented':['Fire resistance -130% (3 turns)',
                                            'remove existing elemental imbues',
                                            'Fire imbue (3 turns)']}}


def make_cache(source):
    """Exact JP client identifiers, with only column aliases the catalog reads.

    Place into a scratch cache, never replace the user's preexisting live data.
    """
    raw=source['ability']
    ability={'ability_id':ABILITY,'name':raw['G4L0YIB2'],
             'effect_frames':raw['5A8SmwyC'], 'attack_frames':raw['a9DvZ70c'],
             'move_type':'0','MotioinType':'2','effect_type':raw['2kq0BpnD']}
    groups=[]
    for row in source['groups']:
        copy=dict(row)
        copy['effect_frames']=copy['5A8SmwyC']
        groups.append(copy)
    return {'F_ABILITY_MST':[ability], 'F_EFFECT_GROUP_MST':groups,
            'F_EFFECT_MST':source['effects'], 'F_UNIT_MST':[]}


def write_prepared_source(source, snapshot, scratch, kit_path, *, overwrite=False):
    """Write verified source cache and kit; never replace existing kit without explicit consent."""
    scratch=Path(scratch);kit_path=Path(kit_path)
    if kit_path.exists() and not overwrite:
        raise SourceError(f'Existing native kit must be reviewed, not overwritten: {kit_path}')
    scratch.mkdir(parents=True,exist_ok=True)
    kit_path.parent.mkdir(parents=True,exist_ok=True)
    for name, rows in make_cache(source).items():
        target=scratch/(name+'.json')
        target.write_text(json.dumps({'table':name,'file':'JP Memorial SQLite (verified)',
                                      'rows':rows},ensure_ascii=False),encoding='utf-8')
    kit=make_kit(snapshot,source)
    kit_path.write_text(json.dumps(kit,ensure_ascii=False,indent=2),encoding='utf-8')
    return kit
