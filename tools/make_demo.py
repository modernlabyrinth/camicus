"""Create fresh fictional inputs in a new directory; never repair real records."""
import argparse
from datetime import datetime, timezone
import json
import os
from pathlib import Path


def create_demo(destination: Path, now: datetime) -> None:
    if not destination.is_absolute() or '..' in destination.parts:
        raise ValueError('demo destination must be an explicit absolute new path')
    destination.mkdir(mode=0o700)
    destination.chmod(0o700)
    timestamp = now.astimezone(timezone.utc).isoformat(timespec='seconds').replace('+00:00', 'Z')
    shared = dict(schema_version='minoetic.weekly-input/1', project_id='fictional-demo', as_of=timestamp)
    values = {
        'project.json': shared | dict(summary='A fictional weekly-brief demonstration.'),
        'tasks.json': shared | dict(tasks=[
            dict(id='demo-1', title='Draft fictional outline', state='todo'),
            dict(id='demo-2', title='Await fictional review', state='blocked'),
            dict(id='demo-3', title='Create fictional checklist', state='done')])}
    for name, value in values.items():
        with (destination / name).open('xb') as output:
            os.fchmod(output.fileno(), 0o600)
            output.write(json.dumps(value, ensure_ascii=False, allow_nan=False, separators=(',', ':')).encode())


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--workspace', required=True, type=Path)
    args = parser.parse_args()
    create_demo(args.workspace, datetime.now(timezone.utc))
    print('Created two fictional inputs; existing directories are never updated.')


if __name__ == '__main__':
    main()
