"""Package committed source and a built frontend; never include local credentials."""
import argparse
import hashlib
import io
import json
import subprocess
import zipfile
from pathlib import Path


def git(root, *args):
    return subprocess.run(['git', *args], cwd=root, check=True, capture_output=True).stdout


def package(root, output_directory):
    root = Path(root).resolve()
    if git(root, 'status', '--porcelain', '--untracked-files=no').strip():
        raise ValueError('Commit tracked edits before packaging the reviewed source.')
    revision = git(root, 'rev-parse', 'HEAD').decode().strip()
    records = git(root, 'ls-tree', '-r', '-z', 'HEAD').split(b'\0')
    for record in filter(None, records):
        metadata, raw_name = record.split(b'\t', 1)
        name = Path(raw_name.decode('utf-8'))
        if metadata.startswith(b'120000'):
            raise ValueError('Tracked symbolic links are not supported in the test build.')
        if any(part == '.env' or (part.startswith('.env.') and part != '.env.example')
               or part.lower() in {'credentials', 'secrets', '.aws'} for part in name.parts):
            raise ValueError('Credential paths must not be tracked in a submission build.')
    dist = root / 'frontend' / 'dist'
    if not (dist / 'index.html').is_file():
        raise ValueError('Build the frontend before packaging.')
    files = {}
    with zipfile.ZipFile(io.BytesIO(git(root, 'archive', '--format=zip', 'HEAD'))) as source:
        for entry in source.infolist():
            if not entry.is_dir():
                files[entry.filename] = source.read(entry)
    for path in dist.rglob('*'):
        if path.is_symlink() or not path.resolve().is_relative_to(dist.resolve()):
            raise ValueError('Frontend assets must stay inside the build directory.')
        if path.is_file():
            if path.name.startswith('.env'):
                raise ValueError('Environment files cannot be packaged as frontend assets.')
            files[path.relative_to(root).as_posix()] = path.read_bytes()
    manifest = {'commit': revision, 'frontend': 'prebuilt',
                'files': {name: hashlib.sha256(data).hexdigest() for name, data in sorted(files.items())}}
    output_directory = Path(output_directory)
    output_directory.mkdir(parents=True, exist_ok=True)
    destination = output_directory / f'causaltrace-{revision[:12]}-test-build.zip'
    with zipfile.ZipFile(destination, 'x', compression=zipfile.ZIP_DEFLATED) as archive:
        for name, data in sorted(files.items()):
            archive.writestr('causalTrace/' + name, data)
        archive.writestr('causalTrace/BUILD.json', json.dumps(manifest, indent=2) + '\n')
    digest = hashlib.sha256(destination.read_bytes()).hexdigest()
    destination.with_suffix('.zip.sha256').write_text(f'{digest}  {destination.name}\n', encoding='utf-8')
    return destination


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output-dir', type=Path, default=Path('submission-builds'))
    args = parser.parse_args()
    print(package(Path(__file__).resolve().parent.parent, args.output_dir))


if __name__ == '__main__':
    main()
