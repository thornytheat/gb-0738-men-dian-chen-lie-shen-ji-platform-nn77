from hashlib import sha256

PENDING_REASONS = {'VISIT_MISSING', 'MISSING_PHOTO', 'SCAN_INCOMPLETE'}


def slot_key(store, slot):
    return f'{store}:{slot}'


def rank_score(seed, store, slot):
    digest = sha256(seed.encode() + b'\x00' + store.encode() + b'\x00' + slot.encode())
    return digest.hexdigest()


def apportion(groups, sample_size):
    """最大余数法按权重分配目标；余数并列按店组编号顺序，总数不丢柜。"""
    total_weight = sum(group['weight'] for group in groups)
    ordered = sorted(groups, key=lambda group: group['code'])
    quotas = {group['code']: sample_size * group['weight'] // total_weight for group in ordered}
    remainder = sample_size - sum(quotas.values())
    # 余数大者先得柜；余数并列按店组编号升序，保证确定性。
    ranked = sorted(ordered, key=lambda group: (-(_fraction(sample_size, group, total_weight, quotas)), group['code']))
    for group in ranked[:remainder]:
        quotas[group['code']] += 1
    return {group['code']: quotas[group['code']] for group in ordered}


def _fraction(sample_size, group, total_weight, quotas):
    return sample_size * group['weight'] / total_weight - quotas[group['code']]


def choose_slots(intake, sample_size):
    """组内按 SHA-256(种子 NUL 门店 NUL 柜位) 排序抽取，结果与输入顺序无关。"""
    campaign = intake['campaign']
    seed = campaign['seed']
    quotas = apportion(campaign['groups'], sample_size)
    stores = {row['store']: row for row in intake['stores']}
    pools = {group['code']: [] for group in campaign['groups']}
    for row in intake['slots']:
        group = stores[row['store']]['group']
        key = slot_key(row['store'], row['slot'])
        pools[group].append({'key': key, 'store': row['store'], 'slot': row['slot'],
                             'category': row['category'], 'source': row['source'],
                             'score': rank_score(seed, row['store'], row['slot'])})
    rows, quota_rows = [], []
    for group in campaign['groups']:
        code = group['code']
        candidates = sorted(pools[code], key=lambda item: (item['score'], item['key']))
        target = quotas[code]
        for order, candidate in enumerate(candidates):
            candidate['group'] = code
            candidate['rank'] = order + 1
            candidate['selected'] = order < target
        rows.extend(candidates[:target])
        quota_rows.append({'code': code, 'target': target, 'pool': len(candidates),
                           'selected': min(target, len(candidates)),
                           'unfilled': max(0, target - len(candidates)),
                           'ranked_candidates': candidates})
    rows.sort(key=lambda item: (item['group'], item['rank']))
    return rows, quota_rows
