"""Select bounded committed evidence only after explicit model-sharing consent."""
import re
import subprocess
from pathlib import Path
from causaltrace.build_doctor import SourceFile

CODE = {'.py', '.js', '.jsx', '.ts', '.tsx', '.mjs', '.cjs', '.java', '.go'}
CONFIG = {'package.json', 'pyproject.toml', 'requirements.txt', 'pom.xml', 'go.mod', 'tsconfig.json', 'pytest.ini', 'setup.cfg'}


def evidence(repo, directory='.', log='', diff=''):
    def git(*args):
        return subprocess.run(['git', *args], cwd=repo, capture_output=True, check=True,
            text=True, encoding='utf-8', errors='replace', timeout=30).stdout
    prefix = Path(directory).as_posix().rstrip('/')
    prefix = '' if prefix == '.' else prefix + '/'
    changed = set(re.findall(r'^\+\+\+ b/(.+)$', diff, flags=re.MULTILINE))
    candidates = []
    for path in git('ls-tree', '-r', '--name-only', 'HEAD').splitlines():
        if prefix and not path.startswith(prefix):
            continue
        relative = path[len(prefix):]
        name = Path(relative).name
        if any(part.startswith('.') for part in Path(relative).parts) or any(token in relative.lower() for token in ('credential', 'secret', 'private_key')):
            continue
        if Path(relative).suffix not in CODE and name not in CONFIG:
            continue
        if (Path(repo) / path).is_symlink():
            continue
        score = 100 if path in changed else 0
        score += 80 if relative in log or (len(name) > 4 and name in log) else 0
        score += 20 if name in CONFIG else 0
        candidates.append((-score, relative, path))
    files, omitted, size = [], [], 0
    for _, relative, path in sorted(candidates):
        if len(files) >= 12:
            omitted.append(relative)
            continue
        content = git('show', 'HEAD:' + path).lstrip('\ufeff')
        if len(content) > 30000 or size + len(content) > 100000:
            omitted.append(relative)
            continue
        try:
            file = SourceFile(path=relative, content=content)
        except ValueError:
            omitted.append(relative)
            continue
        files.append(file)
        size += len(content)
    return files, {'selected_files': [f.path for f in files], 'omitted_files': omitted,
                   'scope': 'Selected committed source/config only; not a whole-project correctness review.'}


def bounded_text(text, limit):
    if len(text) <= limit:
        return text
    marker = '\n[Evidence truncated to fit model context; middle omitted.]\n'
    first = min(8000, (limit - len(marker)) // 3)
    return text[:first] + marker + text[-(limit - len(marker) - first):]
