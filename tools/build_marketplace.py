"""Build the public Camicus marketplace tree, without installation or publication."""
import argparse
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import shutil
import tempfile

_spec=importlib.util.spec_from_file_location('_camicus_plugin_builder',Path(__file__).resolve().with_name('build_plugin.py'))
_plugin=importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(_plugin)


def build_marketplace(root: Path, destination: Path) -> str:
    destination=Path(destination)
    if not destination.is_absolute() or '..' in destination.parts:
        raise ValueError('output must be an explicit absolute new directory')
    if os.path.lexists(destination):raise FileExistsError(str(destination))
    parent=_plugin._directory(destination.parent)
    stage=None
    try:
        stage=Path(tempfile.mkdtemp(prefix='.camicus-marketplace-',dir=destination.parent))
        (stage/'plugins').mkdir(mode=0o700)
        digest=_plugin.build_plugin(Path(root),stage/'plugins/camicus')
        codex={'name':'camicus','plugins':[{'name':'camicus','source':{'source':'local','path':'./plugins/camicus'},'policy':{'installation':'AVAILABLE','authentication':'ON_INSTALL'},'category':'Productivity'}]}
        claude={'name':'camicus','description':'Camicus local evidence workflows for Codex and Claude Code.','owner':{'name':'Modern Labyrinth'},'plugins':[{'name':'camicus','source':'./plugins/camicus','description':'Local weekly-brief checks and bounded read-only Mac audit.'}]}
        for path,data in (('.agents/plugins/marketplace.json',codex),('.claude-plugin/marketplace.json',claude)):
            target=stage/path;target.parent.mkdir(parents=True,mode=0o700)
            target.write_text(json.dumps(data,indent=2)+'\n')
            target.chmod(0o600)
        lines=[]
        for path in sorted(p for p in stage.rglob('*') if p.is_file()):
            lines.append(hashlib.sha256(path.read_bytes()).hexdigest()+'  '+path.relative_to(stage).as_posix()+'\n')
        (stage/'SHA256SUMS').write_text(''.join(lines));(stage/'SHA256SUMS').chmod(0o600)
        _plugin._publish(stage,destination,parent)
        stage=None
        os.fsync(parent)
        return digest
    finally:
        if stage is not None:shutil.rmtree(stage)
        os.close(parent)


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output',type=Path,required=True)
    args=parser.parse_args()
    try:print(build_marketplace(Path(__file__).resolve().parents[1],args.output))
    except (OSError,ValueError) as error:parser.exit(2,str(error)+'\n')

if __name__=='__main__':main()
