"""Run each pinned full upstream repository through CausalTrace and save real reports."""
import argparse
import json
from causaltrace.upstream_projects import PUBLIC_IDS, ROOT, ensure_upstream, profile
from causaltrace.pipeline import run_investigation


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('project', nargs='?', choices=[*PUBLIC_IDS, 'all'], default='all')
    parser.add_argument('--mode', choices=['full', 'regression', 'reproduce'], default='full')
    parser.add_argument('--history-limit', type=int, choices=range(2, 2049), metavar='2..2048', default=64)
    args = parser.parse_args()
    for name in PUBLIC_IDS if args.project == 'all' else [args.project]:
        spec = profile(name)
        print('Investigating ' + spec['name'], flush=True)
        report = run_investigation(ensure_upstream(name), '.', name, ROOT / 'reports',
            investigation_type=args.mode, test_runner=spec['runner'], runner_image=spec['image'],
            history_limit=args.history_limit)
        baseline = report['baseline']
        print(json.dumps({'project': name, 'report_id': report['id'], 'status': report['status'],
            'reason': report['reason'], 'revision': report['baseline_revision'],
            'tests': len(baseline.get('test_ids', [])), 'passed': len(baseline.get('passed_ids', [])),
            'failed': len(baseline.get('failed_ids', [])), 'skipped': len(baseline.get('skipped_ids', [])),
            'collection_errors': baseline.get('collection_errors', [])}), flush=True)

if __name__ == '__main__':
    main()
