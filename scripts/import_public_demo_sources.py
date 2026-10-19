"""Download pinned, public source evidence for the four attributed demo replays."""
import json
from pathlib import Path
from urllib.request import Request, urlopen

ROOT = Path(__file__).resolve().parent.parent
CACHE = ROOT / '.causaltrace' / 'public_upstream'


def download(url):
    with urlopen(Request(url, headers={'User-Agent': 'CausalTrace-demo-research'}), timeout=60) as response:
        return response.read().decode('utf-8')


def main():
    CACHE.mkdir(parents=True, exist_ok=True)
    fixed = '3690ec5a31b3cd4e2d3374198cf19f7023d3d72d'
    parent = '392aef707c0e74341ab4a51420984e9ea6b566c5'
    sources = {
        'humanize_fixed.py': f'https://raw.githubusercontent.com/python-humanize/humanize/{fixed}/src/humanize/number.py',
        'humanize_buggy.py': f'https://raw.githubusercontent.com/python-humanize/humanize/{parent}/src/humanize/number.py',
        'humanize_LICENSE': f'https://raw.githubusercontent.com/python-humanize/humanize/{fixed}/LICENCE',
        'pysnooper_buggy.py': 'https://raw.githubusercontent.com/cool-RR/PySnooper/e21a31162f4c54be693d8ca8260e42393b39abd3/pysnooper/tracer.py',
        'pysnooper_fixed.py': 'https://raw.githubusercontent.com/cool-RR/PySnooper/56f22f8ffe1c6b2be4d2cf3ad1987fdb66113da2/pysnooper/tracer.py',
        'pysnooper_LICENSE': 'https://raw.githubusercontent.com/cool-RR/PySnooper/56f22f8ffe1c6b2be4d2cf3ad1987fdb66113da2/LICENSE',
        'cookiecutter_fixed.py': 'https://raw.githubusercontent.com/cookiecutter/cookiecutter/7f6804c4953a18386809f11faf4d86898570debc/cookiecutter/generate.py',
        'cookiecutter_buggy.py': 'https://raw.githubusercontent.com/cookiecutter/cookiecutter/c15633745df6abdb24e02746b82aadb20b8cdf8c/cookiecutter/generate.py',
        'cookiecutter_LICENSE': 'https://raw.githubusercontent.com/cookiecutter/cookiecutter/7f6804c4953a18386809f11faf4d86898570debc/LICENSE',
        'csv_fixed.java': 'https://raw.githubusercontent.com/apache/commons-csv/de1838ea067f3fbc4c7c21b9eeae077c739ecb73/src/main/java/org/apache/commons/csv/ExtendedBufferedReader.java',
        'csv_LICENSE': 'https://raw.githubusercontent.com/apache/commons-csv/de1838ea067f3fbc4c7c21b9eeae077c739ecb73/LICENSE.txt',
        'csv_NOTICE': 'https://raw.githubusercontent.com/apache/commons-csv/de1838ea067f3fbc4c7c21b9eeae077c739ecb73/NOTICE.txt',
    }
    (CACHE / 'humanize_commits.json').write_text(json.dumps({'fixed': fixed, 'buggy': parent}, indent=2))
    for filename, url in sources.items():
        content = download(url)
        (CACHE / filename).write_text(content, encoding='utf-8')
        print(filename, len(content))
    (CACHE / 'urls.json').write_text(json.dumps(sources, indent=2))


if __name__ == '__main__':
    main()
