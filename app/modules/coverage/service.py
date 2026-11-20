from collections import Counter

from app.modules.coverage.sampling import PENDING_REASONS, choose_slots, slot_key


def evidence_state(plan_decision, binding):
    """合并陈列图与图证结论：可核 / 待证 / 隔离，未到访保留抽中身份。"""
    plan_reason = plan_decision['reason']
    if plan_reason == 'VISIT_MISSING':
        return 'PENDING', 'VISIT_MISSING'
    if plan_reason == 'PLAN_MISSING':
        return 'ISOLATED', 'PLAN_MISSING'
    if plan_reason == 'PLAN_OVERLAP':
        return 'ISOLATED', 'PLAN_OVERLAP'
    if binding is None:
        return 'PENDING', 'MISSING_PHOTO'
    reason = binding['reason']
    if reason is None:
        return 'VERIFIED', None
    if reason in PENDING_REASONS:
        return 'PENDING', reason
    return 'ISOLATED', reason


def coverage(intake, plans, photos, sample_size):
    selected, quota_rows = choose_slots(intake, sample_size)
    plan_index = {slot_key(row['store'], row['slot']): row for row in plans['decisions']}
    # 图证按巡检绑定，先经有效巡检转回门店维度。
    visit_store = {visit['visit']: visit['store'] for visit in intake['visits']}
    evidence_index = {}
    for binding in photos['bindings']:
        store = visit_store.get(binding['visit'])
        if store is not None:
            evidence_index[slot_key(store, binding['slot'])] = binding

    slots, totals = [], Counter()
    strata_by_code = {row['code']: row for row in quota_rows}
    for candidate in selected:
        key = candidate['key']
        plan_decision = plan_index[key]
        binding = evidence_index.get(key)
        status, reason = evidence_state(plan_decision, binding)
        entry = {**candidate, 'key': key, 'group': candidate['group'], 'category': candidate['category'],
                 'visit': plan_decision['visit'], 'plan': plan_decision['plan'],
                 'plan_candidates': plan_decision['candidates'], 'evidence': binding,
                 'evidence_status': status, 'reason': reason, 'source': candidate['source']}
        slots.append(entry)
        totals[status] += 1
        strata_by_code[candidate['group']].setdefault('_states', Counter())[status] += 1

    strata = []
    group_titles = {group['code']: group['title'] for group in intake['campaign']['groups']}
    group_weights = {group['code']: group['weight'] for group in intake['campaign']['groups']}
    for row in quota_rows:
        states = row.pop('_states', Counter())
        verified, pending, isolated = (states['VERIFIED'], states['PENDING'], states['ISOLATED'])
        strata.append({'code': row['code'], 'title': group_titles[row['code']], 'weight': group_weights[row['code']],
                       'pool': row['pool'], 'target': row['target'], 'selected': row['selected'],
                       'unfilled': row['unfilled'], 'verified': verified, 'pending': pending,
                       'isolated': isolated, 'gap': pending + isolated + row['unfilled'],
                       'waitlist': [item['key'] for item in row['ranked_candidates'] if not item['selected']],
                       'ranked_candidates': row['ranked_candidates']})

    target = sum(group['target'] for group in strata)
    selected_total = sum(group['selected'] for group in strata)
    unfilled = sum(group['unfilled'] for group in strata)
    if selected_total + unfilled != target:
        raise AssertionError('抽样目标与名册供给对账失败')
    return {'target': target, 'selected': selected_total, 'unfilled': unfilled,
            'verified': totals['VERIFIED'], 'pending': totals['PENDING'], 'isolated': totals['ISOLATED'],
            'strata': strata, 'slots': slots}
