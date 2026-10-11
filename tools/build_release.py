"""Build only reviewed runtime files into a reproducible local executable archive."""
import argparse
import hashlib
import io
import os
from pathlib import Path
import zipfile

RUNTIME = tuple('minoetic/' + name + '.py' for name in
                ('__init__', '__main__', 'models', 'contracts', 'brief', 'storage', 'workflow', 'cli'))
ENTRY = b'''import sys
if sys.platform != 'darwin' or not (3, 11) <= sys.version_info[:2] <= (3, 14):
    print('{"overall":"checker_error","exit_code":3,"result_saved":false,"checks":[{"id":"checker","state":"failed","reason":"unsupported_platform","source":null,"field":null}]}')
    raise SystemExit(3)
from minoetic.cli import main
raise SystemExit(main())
'''


def build_archive(root: Path, destination: Path) -> str:
    files = {name: (root / name).read_bytes() for name in RUNTIME}
    files['__main__.py'] = ENTRY
    if (root / 'LICENSE').is_file():
        files['LICENSE'] = (root / 'LICENSE').read_bytes()
    buffer = io.BytesIO()
    buffer.write(b'#!/usr/bin/env -S python3 -I -S\n')
    with zipfile.ZipFile(buffer, 'w', compression=zipfile.ZIP_STORED) as archive:
        for name, data in sorted(files.items()):
            info = zipfile.ZipInfo(name, date_time=(2020, 1, 1, 0, 0, 0))
            info.create_system = 3
            info.external_attr = 0o100644 << 16
            archive.writestr(info, data)
    data = buffer.getvalue()
    with destination.open('xb') as output:
        os.fchmod(output.fileno(), 0o700)
        output.write(data)
        output.flush()
        os.fsync(output.fileno())
    return hashlib.sha256(data).hexdigest()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', required=True, type=Path)
    args = parser.parse_args()
    if not args.output.is_absolute():
        parser.error('output must be an explicit absolute new path')
    print(build_archive(Path(__file__).resolve().parents[1], args.output))


if __name__ == '__main__':
    main()
