from copy import deepcopy

from app.modules.coverage.sampling import apportion, choose_slots
from conftest import locate_or_fail


def test_weighted_quotas_allocate_remainder_without_losing_a_slot(field):  # TRAP-24
    groups = field.intake['campaign']['groups']
    assert apportion(groups, 18) == {'CORE': 9, 'COMM': 5, 'RURAL': 4}
    assert sum(apportion(groups, 7).values()) == 7


def test_tied_remainder_uses_group_code_deterministically():  # TRAP-19
    groups = [{'code': 'B', 'weight': 1}, {'code': 'A', 'weight': 1}]
    assert apportion(groups, 1) == apportion(list(reversed(groups)), 1) == {'A': 1, 'B': 0}


def test_rank_scores_deterministic_under_input_permutation(field):
    intake = deepcopy(field.intake)
    intake['slots'].reverse()
    intake['stores'].reverse()
    assert choose_slots(intake, 18) == choose_slots(field.intake, 18)
    row = locate_or_fail(field.coverage['strata'], code='CORE')
    assert row['ranked_candidates'][0]['key'] == '002:A03'


def test_stratum_shortfall_cannot_be_filled_with_a_different_store_group(field):
    result = field.coverage
    rural = locate_or_fail(result['strata'], code='RURAL')
    assert (result['target'], result['selected'], result['unfilled']) == (18, 17, 1)
    assert (rural['pool'], rural['target'], rural['selected'], rural['unfilled'], rural['gap']) == (3, 4, 3, 1, 2)


def test_missing_evidence_does_not_remove_slot_from_denominator(field):
    item = locate_or_fail(field.coverage['slots'], key='001:A04')
    assert (item['evidence_status'], item['reason']) == ('PENDING', 'MISSING_PHOTO')
    assert field.coverage['verified'] == 11
    assert field.coverage['selected'] - field.coverage['verified'] == 6


def test_uncalled_store_slots_are_drawn_but_stay_pending(reference):
    reference.bundle['visits.csv'] = b'visit,store,clock\n'
    result = reference.coverage
    assert (result['target'], result['selected'], result['verified']) == (18, 18, 0)
    assert {row['reason'] for row in result['slots']} == {'VISIT_MISSING'}


def test_full_reference_has_zero_gap_and_requested_size_is_applied(reference):
    assert [row['gap'] for row in reference.coverage['strata']] == [0, 0, 0]
    rows, quotas = choose_slots(reference.intake, 10)
    assert len(rows) == 10
    assert [row['selected'] for row in quotas] == [5, 3, 2]


def test_waitlist_keeps_deterministic_rank_order_within_each_stratum(field):
    strata = {row['code']: row for row in field.coverage['strata']}
    core = strata['CORE']
    ranked = [item['key'] for item in core['ranked_candidates']]
    assert ranked[0] == '002:A03'
    assert core['waitlist'] == ranked[core['selected']:]
    assert [item['rank'] for item in core['ranked_candidates']] == list(range(1, core['pool'] + 1))
    # 近郊名册只有 3 柜，候补序列为空，缺额留在本组而非借柜。
    rural = strata['RURAL']
    assert rural['waitlist'] == [] and rural['unfilled'] == 1
    assert all(item['group'] == 'RURAL' for item in rural['ranked_candidates'])


def test_target_selected_and_unfilled_reconcile_at_top_and_stratum_level(field):
    result = field.coverage
    assert result['target'] == result['selected'] + result['unfilled']
    for group in result['strata']:
        assert group['target'] == group['selected'] + group['unfilled']
        assert group['selected'] == group['verified'] + group['pending'] + group['isolated']
        assert group['gap'] == group['pending'] + group['isolated'] + group['unfilled']
    assert result['selected'] == result['verified'] + result['pending'] + result['isolated']
    assert len(result['slots']) == result['selected'] == len({row['key'] for row in result['slots']})

