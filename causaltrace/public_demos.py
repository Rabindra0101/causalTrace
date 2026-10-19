"""Public upstream catalog and lookup of previously cached replay histories."""
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
PROJECTS = {'humanize': {'name': 'humanize — significant figures',
              'upstream_buggy': '392aef707c0e74341ab4a51420984e9ea6b566c5',
              'upstream_fixed': '3690ec5a31b3cd4e2d3374198cf19f7023d3d72d',
              'source': 'https://raw.githubusercontent.com/python-humanize/humanize/3690ec5a31b3cd4e2d3374198cf19f7023d3d72d/src/humanize/number.py',
              'note': 'Focused extracted source with compatibility harness; newly authored '
                      'regression test. Three-commit replay history is reconstructed, not upstream '
                      'history.'},
 'pysnooper': {'name': 'PySnooper — Unicode source',
               'upstream_buggy': 'e21a31162f4c54be693d8ca8260e42393b39abd3',
               'upstream_fixed': '56f22f8ffe1c6b2be4d2cf3ad1987fdb66113da2',
               'source': 'https://raw.githubusercontent.com/cool-RR/PySnooper/56f22f8ffe1c6b2be4d2cf3ad1987fdb66113da2/pysnooper/tracer.py',
               'note': 'Focused extracted source with compatibility harness; newly authored '
                       'regression test. Three-commit replay history is reconstructed, not '
                       'upstream history.'},
 'cookiecutter': {'name': 'Cookiecutter — UTF-8 context',
                  'upstream_buggy': 'c15633745df6abdb24e02746b82aadb20b8cdf8c',
                  'upstream_fixed': '7f6804c4953a18386809f11faf4d86898570debc',
                  'source': 'https://raw.githubusercontent.com/cookiecutter/cookiecutter/7f6804c4953a18386809f11faf4d86898570debc/cookiecutter/generate.py',
                  'note': 'Focused extracted source with compatibility harness; newly authored '
                          'regression test. Three-commit replay history is reconstructed, not '
                          'upstream history.'},
 'commons_csv': {'name': 'Apache Commons CSV — CR line counting',
                 'upstream_buggy': '0833f45bffd40f44ba6f294d84e9bac8a9ba0a37',
                 'upstream_fixed': 'de1838ea067f3fbc4c7c21b9eeae077c739ecb73',
                 'source': 'https://raw.githubusercontent.com/apache/commons-csv/de1838ea067f3fbc4c7c21b9eeae077c739ecb73/src/main/java/org/apache/commons/csv/ExtendedBufferedReader.java',
                 'note': 'Complete upstream reader class, newly authored JUnit test; reconstructed '
                         'history for Defects4J Csv-1 / CSV-75.'}}
PUBLIC_IDS = tuple(PROJECTS)


def metadata(name):
    return dict(PROJECTS[name])


def catalog():
    from causaltrace.upstream_projects import profile
    return [{'id': name, 'name': profile(name)['name'] + ' (full upstream repository)'} for name in PUBLIC_IDS]


def ensure_public_demo(name):
    """Old reports can use their existing cache; obsolete replays are not regenerated."""
    if name not in PUBLIC_IDS:
        raise ValueError('Unknown public project.')
    target = ROOT / '.causaltrace' / 'demos' / ('public-' + name)
    if not (target / '.git').is_dir():
        raise RuntimeError('This retired replay history is not cached. The saved report remains available; run a new upstream investigation for its timeline.')
    return target
