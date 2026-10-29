import 'package:flutter/material.dart';
import 'package:provider/provider.dart';
import '../../design/theme.dart';
import '../../design/widgets.dart';
import '../../state/app_state.dart';
import '../../state/catalog_helpers.dart';
import 'tiers.dart';
import 'grant_details.dart';
import 'native_library_row.dart';

class AbilitiesStep extends StatefulWidget {
  const AbilitiesStep({super.key, required this.unit, required this.set});
  final Map<String, dynamic> unit;
  final ValueChanged<Map<String, dynamic>> set;
  @override
  State<AbilitiesStep> createState() => _AbilitiesStepState();
}

class _AbilitiesStepState extends State<AbilitiesStep> {
  String q = '', group = 'ffr', sourceFilter = 'all', statusFilter = 'all';
  bool allowEnemyTests = false;
  String category(Map s) {
    final supportive = s['relation'] == 'Friendlies' || s['dmgType'] == 'None';
    if (s['attr'] == 'Magic' || s['attr'] == 'MagicSword') {
      final el = s['element'];
      return el != null && el != 'None' ? '$el magic' : supportive ? 'White magic' : 'Magic';
    }
    return supportive ? 'Support abilities' : 'Attack abilities';
  }
  @override
  Widget build(BuildContext context) {
    final app = context.read<AppState>(), unit = widget.unit;
    final cat = app.catalog!;
    final skills = (cat['skills'] as List).cast<Map<String, dynamic>>();

    // A missing catalog sequence is not proof a skill fails: native Dark, Darkra,
    // Darkga and Darkga (all) were verified working in the installed full release.
    // Grant IDs are written by the existing mod builder, without new asset conversion.
    bool canAssign(Map s) {
      final id = s['id'];
      if (id is! num || !['Ability', 'Magic', 'MagicSword'].contains(s['attr'])) return false;
      final row = (s['row'] ?? '').toString();
      final special = row.contains('敵用') || id >= 500000 || (id >= 300000 && id < 400000);
      return !special || allowEnemyTests;
    }

    String sourceOf(Map s) {
      final row = (s['row'] ?? '').toString();
      if (row.contains('敵用')) return 'enemy';
      // Many 500k+ skills are enemy actions but lack the explicit Japanese marker.
      // Keep them unclassified instead of claiming they are player abilities.
      if (s['id'] is num && ((s['id'] as num) >= 500000 ||
          ((s['id'] as num) >= 300000 && (s['id'] as num) < 400000))) return 'unknown';
      final owner = (s['hasUnit'] ?? '').toString();
      if (owner.isEmpty) return 'unknown';
      return owner == 'All' ? 'general' : 'character';
    }

    String sourceLabel(Map s) {
      switch (sourceOf(s)) {
        case 'enemy':
          return 'Enemy-use';
        case 'character':
          return 'Character: ${s['hasUnit']}';
        case 'general':
          return 'General / player-side';
        default:
          return 'Unclassified';
      }
    }

    final lib = skills.toList()
      ..sort((a, b) => a['name'].toString().compareTo(b['name'].toString()));

    final studio = ((cat['studioSkills'] as List?) ?? []).cast<Map<String, dynamic>>();
    final aw = awakening(unit);
    final granted = {for (final t in aw) for (final g in t) if (g[0] == 'ActiveSkill') g[1]};
    final mine = Map<String, dynamic>.from(unit['skills'] as Map? ?? {});
    final authored = {for (final x in mine.values) if (x['studio'] != null) x['studio']};
    final query = q.trim().toLowerCase();
    bool matches(Map r) => '${r['name']} ${r['description'] ?? r['desc'] ?? ''}'.toLowerCase().contains(query);
    final natives = (group == 'native' || group == 'all') ? nativeEntries(unit).where((e) => e['kind'] != 'PASSIVE' && matches(e)).toList() : <Map<String, dynamic>>[];
    final shown = lib.where((r) =>
        (group == 'all' || group == 'ffr' || category(r) == group) &&
        (sourceFilter == 'all' || sourceOf(r) == sourceFilter) &&
        (statusFilter == 'all' ||
            (statusFilter == 'allowed' ? canAssign(r) : !canAssign(r))) &&
        matches(r)).toList();
    final studioShown = (group == 'all' || group == 'studio') ? studio.where(matches).toList() : <Map<String, dynamic>>[];

    void add(int tier, int index, DragPayload payload) {
      if (aw[tier].length >= tierCap) { grantMessage(context, 'Tier ${tier + 1} is full. Choose another tier.'); return; }
      num? id;
      var nextSkills = mine;
      if (payload.value is String) {
        final sk = studio.where((r) => r['key'] == payload.value).firstOrNull;
        if (sk == null || authored.contains(sk['key'])) return;
        final base = 445000 + ((unit['id'] as num).toInt() - 13100) * 100;
        for (var slot = 0; slot < 10; slot++) { if (!mine.containsKey('${base + slot * 10}')) { id = base + slot * 10; break; } }
        if (id == null) { grantMessage(context, 'All 10 custom command slots are occupied. Remove a custom move first.'); return; }
        final recipe = sk['recipe'] as Map;
        nextSkills = {...mine, '$id': {'from': recipe['from'], 'visuals': recipe['visuals'] ?? recipe['from'], 'jp': '${unit['jp']}_Studio_$id',
          'en': sk['name'], 'desc': sk['desc'], 'descAuto': false, 'set': Map<String, dynamic>.from(recipe['set'] as Map? ?? {}), 'studio': sk['key']}};
      } else {
        id = payload.value as num;
        final skill = skills.where((s) => s['id'] == id).firstOrNull;
        if (skill == null || !canAssign(skill) || granted.contains(id)) return;
      }
      final next = deepCopy(aw); next[tier].insert(index.clamp(0, next[tier].length), ['ActiveSkill', id]);
      widget.set({'awakening': next, 'skills': nextSkills});
    }

    final total = natives.length + shown.length + studioShown.length;
    return Row(crossAxisAlignment: CrossAxisAlignment.stretch, children: [
      Expanded(child: Column(crossAxisAlignment: CrossAxisAlignment.stretch, children: [
        Band('Abilities', color: Guide.blue, trailing: unit['ffbe'] == null ? null : NativeImportButton(unit: unit, group: 'abilities', set: widget.set)),
        Padding(padding: const EdgeInsets.all(12), child: Row(children: [
          Expanded(child: TextField(decoration: const InputDecoration(hintText: 'Search abilities', prefixIcon: Icon(Icons.search, size: 18)), onChanged: (v) => setState(() => q = v))),
          const SizedBox(width: 10), SizedBox(width: 170, child: DropdownButton<String>(value: group, isExpanded: true, style: Guide.text(), dropdownColor: Guide.paper,
            items: [for (final e in {'native': 'Native Abilities', 'all': 'All abilities', 'ffr': 'FFR abilities', if (studio.isNotEmpty) 'studio': 'Studio moves', for (final name in lib.map(category).toSet()) name: name}.entries)
              DropdownMenuItem(value: e.key, child: Text(e.value, overflow: TextOverflow.ellipsis))], onChanged: (v) => setState(() => group = v ?? 'native'))),
        ])),
        if (group != 'native' && group != 'studio')
          Padding(
            padding: const EdgeInsets.fromLTRB(12, 0, 12, 10),
            child: Row(children: [
              Expanded(child: DropdownButton<String>(
                value: sourceFilter,
                isExpanded: true,
                style: Guide.text(),
                dropdownColor: Guide.paper,
                items: const <DropdownMenuItem<String>>[
                  DropdownMenuItem(value: 'all', child: Text('All sources', overflow: TextOverflow.ellipsis)),
                  DropdownMenuItem(value: 'general', child: Text('General / player-side', overflow: TextOverflow.ellipsis)),
                  DropdownMenuItem(value: 'character', child: Text('Character-specific', overflow: TextOverflow.ellipsis)),
                  DropdownMenuItem(value: 'enemy', child: Text('Enemy-use', overflow: TextOverflow.ellipsis)),
                  DropdownMenuItem(value: 'unknown', child: Text('Unclassified', overflow: TextOverflow.ellipsis)),
                ],
                onChanged: (v) => setState(() => sourceFilter = v ?? 'all'),
              )),
              const SizedBox(width: 8),
              Expanded(child: DropdownButton<String>(
                value: statusFilter,
                isExpanded: true,
                style: Guide.text(),
                dropdownColor: Guide.paper,
                items: const <DropdownMenuItem<String>>[
                  DropdownMenuItem(value: 'all', child: Text('All skills', overflow: TextOverflow.ellipsis)),
                  DropdownMenuItem(value: 'allowed', child: Text('Eligible to test', overflow: TextOverflow.ellipsis)),
                  DropdownMenuItem(value: 'viewonly', child: Text('View only', overflow: TextOverflow.ellipsis)),
                ],
                onChanged: (v) => setState(() => statusFilter = v ?? 'all'),
              )),
            ]),
          ),
        if (group != 'native' && group != 'studio')
          Padding(padding: const EdgeInsets.fromLTRB(12, 0, 12, 8), child: Row(children: [
            Checkbox(value: allowEnemyTests, onChanged: (v) => setState(() => allowEnemyTests = v ?? false)),
            Expanded(child: Text('Enable enemy / summon / unclassified skills (unverified)', style: Guide.small())),
          ])),
        Padding(padding: const EdgeInsets.fromLTRB(12, 0, 12, 10), child: Text('Import the full native list, or use a left handle to place an ability. Native limit bursts are available on the Resonance tab.', style: Guide.small())),
        Expanded(child: total == 0 ? Center(child: Text(group == 'native' && query.isEmpty ? 'This vision has no native abilities.' : 'No matching abilities.', style: Guide.small()))
          : ListView.builder(padding: const EdgeInsets.symmetric(horizontal: 12), itemCount: total, itemBuilder: (_, i) {
            if (i < natives.length) return NativeLibraryRow(key: ValueKey(natives[i]['sourceKey']), unit: unit, entry: natives[i], set: widget.set, zebra: i.isOdd);
            final j = i - natives.length;
            if (j < studioShown.length) {
              final sk = studioShown[j];
              return LibraryRow(title: sk['name'].toString(), detail: '${sk['desc']} · Studio move', zebra: i.isOdd,
                leading: ElementSwatch(sk['recipe']?['set']?['element']), payload: DragPayload('skill', sk['key']), done: authored.contains(sk['key']),
                onAdd: (t) => add(t, aw[t].length, DragPayload('skill', sk['key'])));
            }
            final row = shown[j - studioShown.length];
            final data = grantData(unit, cat, {'kind': 'ActiveSkill', 'id': row['id']});
            final testedDark = const <int>{220390, 220520, 220400, 225270}.contains(row['id']);
            final sequenceNote = testedDark ? ' · In-game tested' :
                (row['seq'] as List?)?.isNotEmpty == true ? '' : ' · Sequence not indexed';
            return LibraryRow(title: data.name, detail: '${data.description.isEmpty ? describe(row) : data.description} · ${data.cost} MP · ${sourceLabel(row)}$sequenceNote', zebra: i.isOdd,
              icon: GrantIcon(data: data, api: app.api!, catalog: cat), payload: DragPayload('skill', row['id']), enabled: canAssign(row), done: granted.contains(row['id']),
              onInfo: () => showGrantInfo(context, unit, data), onAdd: (t) => add(t, aw[t].length, DragPayload('skill', row['id'])));
          })),
      ])),
      Container(width: 1, color: Guide.hairline),
      Expanded(child: LearnedTiers(unit: unit, set: widget.set, onLibraryDrop: add)),
    ]);
  }
}
