"""Release regression search and bounded, consent-gated repair experiments."""
import subprocess
import tempfile
import uuid
from datetime import datetime, timezone
from pathlib import Path
from causaltrace import build_doctor
from causaltrace.diagnostic_context import evidence, bounded_text
from causaltrace.test_runner import is_failure, same_tests, run_pytest
from causaltrace.verifier import test_commit, run_command
from causaltrace.language_runner import is_test_path, RUNNER
from causaltrace.analysis_policy import settings
from causaltrace.controlled_process import run as controlled_run


def git(repo, *args):
    return run_command(['git', *args], repo).stdout.strip()


def resolve_releases(repo, good_ref, bad_ref):
    if not good_ref or not bad_ref or len(good_ref) > 200 or len(bad_ref) > 200:
        raise ValueError('Select the last working release and the broken release (tags or commit IDs).')
    def resolve(ref):
        try:
            return git(repo, 'rev-parse', '--verify', '--end-of-options', ref + '^{commit}')
        except subprocess.SubprocessError as error:
            raise ValueError('A selected release does not resolve to a commit.') from error
    good, bad = resolve(good_ref), resolve(bad_ref)
    if good == bad:
        raise ValueError('Good and bad releases must be different commits.')
    history = git(repo, 'rev-list', '--first-parent', bad).splitlines()
    if good not in history:
        raise ValueError('The working release must be on the broken release first-parent history.')
    return good, bad, list(reversed(history[:history.index(good)+1]))


def outcome(result, test_id):
    if result.get('execution_error'):
        return 'unknown'
    if test_id.startswith('collection::'):
        path = test_id[len('collection::'):]
        if path in result.get('collection_errors', []):
            return 'fail'
        if result.get('collection_errors'):
            return 'unknown'
        return 'pass' if any(identity.startswith(path+'::') for identity in result.get('passed_ids', [])) else 'unknown'
    if result.get('collection_errors'):
        return 'unknown'
    if test_id in result.get('failed_ids', []):
        return 'fail'
    if test_id in result.get('passed_ids', []):
        return 'pass'
    return 'unknown'


def regression_search(repo, directory, revisions, cache, budget=None):
    budget = budget or settings()["history_runs"]
    """Bisect each failed test using cached whole-suite executions; never guess unknowns."""
    good, bad = revisions[0], revisions[-1]
    def run(commit):
        if commit not in cache:
            if len(cache) >= budget:
                return None
            cache[commit] = test_commit(repo, commit, directory)
        return cache[commit]
    groups = []
    failures = list(dict.fromkeys(cache[bad].get('failed_ids', []) + ['collection::'+p for p in cache[bad].get('collection_errors', [])]))
    changed_tests = [p for p in git(repo, 'diff', '--name-only', good, bad, '--', directory).splitlines() if is_test_path(p)]
    for test_id in failures[:settings()["failure_groups"]]:
        group = {'test_id': test_id, 'confirmed': False, 'reason': '', 'searched': []}
        groups.append(group)
        if outcome(cache[good], test_id) != 'pass':
            group['reason'] = 'This failing test did not pass at the selected working release.'
            continue
        lo, hi = 0, len(revisions)-1
        unavailable = set()
        while hi-lo > 1:
            eligible = [i for i in range(lo+1,hi) if i not in unavailable]
            if not eligible:
                group['reason'] = 'The remaining interval contains unavailable test evidence; no adjacent boundary can be verified.'
                break
            mid = min(eligible, key=lambda i: abs(i-(lo+hi)/2))
            result = run(revisions[mid])
            state = outcome(result, test_id) if result else 'unknown'
            group['searched'].append({'commit': revisions[mid], 'outcome': state})
            if state == 'unknown':
                if result is None:
                    group['reason'] = 'Historical execution budget exhausted. All attempted results remain visible.'
                    break
                unavailable.add(mid)
                continue
            if state == 'pass':
                lo = mid
            else:
                hi = mid
        else:
            group.update(parent_revision=revisions[lo], suspected_commit=revisions[hi])
            group['confirmed'] = not bool(changed_tests)
            group['reason'] = ('Adjacent passing/failing boundary confirmed for this test. Search assumes a single pass-to-fail transition in the selected range.' if not changed_tests else
                'Tests changed between releases; the observed boundary does not establish implementation causality.')
            group['commit_date'] = git(repo, 'show', '-s', '--format=%aI', revisions[hi])
            group['commit_message'] = git(repo, 'show', '-s', '--format=%s', revisions[hi])
    return groups, changed_tests, max(0, len(failures)-settings()["failure_groups"])


def reversal_checks(repo, directory, groups):
    """Reverse up to three distinct candidates; assess each failed test separately."""
    candidates = list(dict.fromkeys(g['suspected_commit'] for g in groups if g['confirmed']))[:settings()["reversals"]]
    for candidate in candidates:
        related = [g for g in groups if g.get('suspected_commit') == candidate and g['confirmed']]
        result = {'outcome': 'inconclusive', 'reason': 'Reversal could not be evaluated.'}
        with tempfile.TemporaryDirectory(prefix='causaltrace-release-reverse-') as folder:
            worktree = Path(folder)/'repo'
            run_command(['git','worktree','add','--detach',str(worktree),'HEAD'], repo)
            try:
                before = run_pytest(worktree/directory)
                reversed_change = controlled_run(['git','revert','--no-commit',candidate], cwd=worktree,
                    capture_output=True, text=True, timeout=30)
                if reversed_change.returncode == 0:
                    after = run_pytest(worktree/directory)
                    for group in related:
                        pre, post = outcome(before, group['test_id']), outcome(after, group['test_id'])
                        preserved = set(before.get('passed_ids', [])) <= set(after.get('passed_ids', []))
                        supported = pre == 'fail' and post == 'pass' and preserved and not after.get('skipped_ids') and same_tests(before, after)
                        group['reversal'] = {'outcome':'verified' if supported else 'not_supported' if pre == post == 'fail' else 'inconclusive',
                            'reason':'The target failure disappears after reversal; existing passing tests remain passing.' if supported else 'Reversal did not establish the target cause without losing passing tests.',
                            'before':before, 'after':after}
                else:
                    result['reason'] = 'Candidate could not be reversed cleanly (conflict or merge commit).'
            finally:
                run_command(['git','worktree','remove','--force',str(worktree)], repo)
        for group in related:
            group.setdefault('reversal', dict(result))
    for group in groups:
        group.setdefault('reversal', {'outcome':'not_run', 'reason':'No implementation boundary was confirmed or the three-candidate reversal limit was reached.'})


def improves(before, after):
    if not same_tests(before, after) or after.get('execution_error') or after.get('collection_errors') or after.get('skipped_ids'):
        return False
    if after.get('passed'):
        return True
    # Retain a partial repair only if it fixes tests and introduces no new failures.
    old, new = set(before.get('failed_ids', [])), set(after.get('failed_ids', []))
    return bool(old) and new < old and set(before.get('passed_ids', [])) <= set(after.get('passed_ids', []))


def repair_loop(repo, directory, baseline, diff, attempts, consent):
    result = {'status': 'not_run', 'attempts': [], 'final_tests': baseline, 'patch': '', 'reason': ''}
    if not consent:
        result['reason'] = 'Enable sharing selected evidence with Nebius for this run to request repairs.'
        return result
    if not is_failure(baseline):
        result['reason'] = 'No reproducible failing test baseline; repair verification cannot start.'
        return result
    limits = settings()
    current, feedback = baseline, ''
    base_revision = git(repo, 'rev-parse', 'HEAD')
    for number in range(1, attempts+1):
        files, scope = evidence(repo, directory, current['output'], diff)
        context = ('Release repair experiment. Fix observed failures without changing tests or configuration. '
                   'No commit causality is implied by this request. Previous attempt feedback:\n' + feedback + '\nBASELINE:\n' + current['output'])
        request = build_doctor.BuildRequest(log=bounded_text(context, limits["log_chars"]), files=files, diff=bounded_text(diff, settings()["diff_chars"]))
        entry = {'number': number, 'source_context': scope, 'accepted': False}
        result['attempts'].append(entry)
        try:
            proposal = build_doctor.investigate(request)
            entry['proposal'] = proposal
            if not proposal['patch'] or proposal['patch_error']:
                entry['reason'] = 'No applicable implementation patch was proposed.'
                break
            verification = build_doctor.verify(proposal['id'], repository=repo, directory=directory)
            entry['verification'] = verification
            before, after = verification.get('before'), verification.get('after')
            stable_baseline = (before and before.get('status') == current.get('status')
                and set(before.get('failed_ids', [])) == set(current.get('failed_ids', []))
                and set(before.get('collection_errors', [])) == set(current.get('collection_errors', [])))
            if not before or not after or not stable_baseline or not improves(current, after) or not same_tests(current, before):
                entry['reason'] = 'Candidate did not reduce failures while preserving existing tests and passing outcomes.'
                feedback = proposal['patch'] + '\n' + (after or before or {}).get('output', entry['reason'])
                continue
            edits = [build_doctor.Replacement.model_validate(e) for e in proposal['diagnosis']['replacements']]
            build_doctor.validate_edits(edits)
            patched, _ = build_doctor.apply_replacements(files, edits)
            changed = [f.path for f in files if patched[f.path] != f.content]
            for path in changed:
                full = Path(repo)/directory/path
                full.write_text(patched[path], encoding='utf-8')
            git(repo, 'add', '--', *[(Path(directory)/p).as_posix() for p in changed])
            git(repo, '-c', 'user.name=CausalTrace Repair Experiment', '-c', 'user.email=repair@causaltrace.local', '-c', 'commit.gpgsign=false', 'commit', '-qm', f'Isolated repair attempt {number}')
            entry['accepted'] = True
            entry['reason'] = 'Candidate reduced failures without new failures or skipped tests.'
            current = after
            result['final_tests'] = current
            feedback = 'Previous accepted patch fixed some failures. Fix the remaining failures using the current committed source.'
            if current.get('passed'):
                result['status'] = 'verified'
                result['reason'] = 'The complete unchanged test suite passes after the cumulative repair. This covers the executed tests, not all possible bugs.'
                break
        except Exception:
            entry['reason'] = 'AI proposal or verification could not complete; check provider access and runner setup.'
            break
    if result['status'] != 'verified':
        result['status'] = 'partial' if any(e['accepted'] for e in result['attempts']) else 'not_verified'
        result['reason'] = 'Repair attempt budget finished or a proposal was unavailable. Remaining failures are unresolved.'
    exported = controlled_run(['git', 'diff', '--binary', '--full-index', base_revision, 'HEAD', '--', directory],
        cwd=repo, capture_output=True, check=True, timeout=30)
    result['patch'] = exported.stdout.decode('utf-8')
    return result


def run_release(repo, directory, repository_id, reports_root, good_ref, bad_ref, good, bad, revisions, attempts=3, consent=False):
    from causaltrace.pipeline import persist
    report = {'id': uuid.uuid4().hex, 'generated_at': datetime.now(timezone.utc).isoformat(),
        'project': 'CausalTrace', 'repository_id': repository_id, 'investigation_type': 'release',
        'status': 'inconclusive', 'reason': '', 'baseline_revision': bad, 'test_runner': RUNNER.get(),
        'model_sharing_consent': consent, 'ai_analysis': {'status':'not_run'}, 'repair': None, 'experiments': {},
        'release_range': {'good_ref':good_ref, 'bad_ref':bad_ref, 'good_commit':good, 'bad_commit':bad,
                          'commits_in_range':len(revisions)-1, 'search_budget':settings()['history_runs'],
                          'assumption':'Each failure has a single pass-to-fail transition; bisection does not rule out untested transient failures.'}}
    from causaltrace.public_demos import PUBLIC_IDS
    if repository_id in PUBLIC_IDS:
        from causaltrace.upstream_projects import provenance
        report['provenance'] = {**provenance(repository_id), 'upstream_revision':bad, 'note':'Original upstream history and tests at the selected broken release. Repair experiments use independent copies.'}
    cache = {good:test_commit(repo, good, directory), bad:test_commit(repo, bad, directory)}
    from causaltrace.pipeline import locate_boundary, HISTORY_LIMIT
    history = locate_boundary(repo, directory, limit=HISTORY_LIMIT.get(), baseline=cache[bad], cache=cache)
    report['regression'] = history
    history_revisions = [row['commit'] for row in history['history']]
    if good not in history_revisions:
        history_revisions.append(good)  # Keep the separately requested endpoint check.
    report['release_range']['search_budget'] = HISTORY_LIMIT.get()
    report['release_range']['assumption'] = 'Search starts at the broken release and stops at the newest passing/failing transition or configured limit. The selected working endpoint is checked separately.'
    def save():
        boundary = report.setdefault('regression', {'confirmed':False})
        rows=[]
        for commit in history_revisions:
            if commit not in cache:
                continue
            parts=git(repo,'show','-s','--format=%h%x1f%s%x1f%aI',commit).split('\x1f',2)
            rows.append({'commit':commit,'short_hash':parts[0],'message':parts[1],'date':parts[2],
                         'status':cache[commit]['status'],'result':cache[commit]})
        boundary['history']=rows
        return persist(report,reports_root)
    report['working_baseline'], report['baseline'] = cache[good], cache[bad]
    if not cache[good].get('passed'):
        report['reason'] = 'The selected working release did not pass its full test suite. Choose a verified working release or fix runner setup.'
        return save()
    if not is_failure(cache[bad]):
        report['status'] = 'no_failure' if cache[bad].get('passed') else 'execution_error'
        report['reason'] = 'The selected broken release did not reproduce a valid test failure. Provide a failing regression test or fix runner setup.'
        return save()
    if history['confirmed']:
        scoped_revisions = list(reversed([row['commit'] for row in history['history']]))
        groups, changed_tests, omitted = regression_search(repo, directory, scoped_revisions, cache)
    else:
        groups, changed_tests = [], []
        omitted = len(cache[bad].get('failed_ids', [])) + len(cache[bad].get('collection_errors', []))
    reversal_checks(repo, directory, groups)
    report['failure_groups'] = groups
    report['unsearched_failures'] = omitted
    report['test_changes_detected'] = changed_tests
    report['regression']['confirmed'] = bool(groups) and all(g['confirmed'] for g in groups) and not omitted
    if cache[bad].get('collection_errors'):
        report['reason'] = 'Collection failed before individual tests could be grouped. Repair suggestions can still address the import/collection failure.'
    diff = git(repo, 'diff', good, bad, '--', directory)
    report['candidate_diff'] = bounded_text(diff, settings()["diff_chars"])
    report['repair_session'] = repair_loop(repo, directory, cache[bad], diff, attempts, consent)
    session = report['repair_session']
    report['model_request_attempted'] = bool(session['attempts'])
    report['ai_analysis']['status'] = ('completed' if any(a.get('proposal') for a in session['attempts']) else 'unavailable' if session['attempts'] else 'consent_required' if not consent else 'not_run')
    report['status'] = 'completed' if session['status'] == 'verified' else 'partial'
    report['reason'] = session['reason']
    if session['patch']:
        root = Path(reports_root)
        root.mkdir(parents=True, exist_ok=True)
        (root/(report['id']+'.patch')).write_text(session['patch'], encoding='utf-8', newline='')
        report['repair_patch_url'] = '/api/investigation/'+report['id']+'/repair.patch'
    for group in groups:
        group['resolved_after_repair'] = outcome(session['final_tests'], group['test_id']) == 'pass'
    return save()
