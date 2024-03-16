_name = 'update'
_desc = 'Update the system or rollback previous update.'

import collections
import datetime
import glob
import json
import os
import pathlib
import subprocess
from dataclasses import dataclass, asdict


CONFIG_DIR = f'{os.environ["HOME"]}/.config/sysman'
PIPELINE_FILE = f'{CONFIG_DIR}/update_pipeline.json'
TIMESTAMP_FILE = f'{CONFIG_DIR}/tmp/timestamp'
PACMAN_LOG = '/var/log/pacman.log'
PACMAN_CACHE_LOC = '/var/cache/pacman/pkg'
CACHE_DIR = f'{os.getenv("HOME")}/.cache'
AUR_CACHE_LOC = f'{CACHE_DIR}/yay'
AUR_REBUILD_CACHE_LOC = f'{CACHE_DIR}/yay-rebuild'


@dataclass
class UpdateStep:
    command: str
    special_env: str


class CustomJsonEncoder(json.JSONEncoder):
    def default(self, o):
        if type(o) is list:
            return [ self.default(i) for i in o ]

        if type(o) is UpdateStep:
            obj_dict = asdict(o)

            return f'##<{obj_dict}>##'

        return super().default(o)


def read_timestamp() -> datetime.datetime:
    with open(TIMESTAMP_FILE, 'r') as f:
        timestamp = datetime.datetime.fromisoformat(f.readline().strip())

    return timestamp

def write_timestamp() -> str:
    with open(TIMESTAMP_FILE, 'w+') as f:
        timestamp = datetime.datetime.now().astimezone().replace(microsecond=0).isoformat()

        f.write(timestamp)

    return timestamp

def read_update_pipeline_file(timestamp: str) -> list[UpdateStep]:
    with open(PIPELINE_FILE, 'r') as f:
        file_content = json.load(f)

    update_pipeline = []
    for step in file_content:
        cmd = step['command'].split(' ')

        special_env = step['special_env']
        if special_env == 'cache_rebuild':
            env = { **os.environ, 'XDG_CACHE_HOME': f'{AUR_REBUILD_CACHE_LOC}/{timestamp}' }

        else:
            env = None

        update_pipeline.append([ cmd, env ])
    
    return update_pipeline


def is_date(string: str) -> bool:
    try:
        datetime.datetime.fromisoformat(string)
        return True

    except ValueError:
        return False

def search_cache(pkgs: list[str, str], pacman_cache: list[str], aur_cache: list[str]) -> list[str]:
    cache_hits = []
    for pkg in pkgs:
        pacman_hit = [ cache for cache in pacman_cache if f'/{pkg[0]}-{pkg[1]}' in cache ]
        aur_hit = [ cache for cache in aur_cache if f'/{pkg[0]}-{pkg[1]}' in cache ]
        cache_hit = f'{pacman_hit[0]}' if len(pacman_hit) > 0 else f'{aur_hit[0]}' if len(aur_hit) > 0 else None

        if cache_hit is not None:
            cache_hits.append(cache_hit)

    return cache_hits

def create_rollback_process(args: list[list[str], list[str], dict[str, str]]) -> list[list[str], dict[str, str]]:
    rollback_process = []
    for arg in args:
        if len(arg[1]) > 0:
            rollback_process.append([ [*arg[0], *arg[1]], arg[2] ])
    
    return rollback_process

def subprocess_run_sync(args: list[list[str], dict[str, str]]):
    for arg in args:
        pipes_idx = [ -1 ] + [ i for i, o in enumerate(arg[0]) if o == '|' ] + [ None ]

        ret = None
        for i in range(1, len(pipes_idx)):
            cmd = arg[0][pipes_idx[i - 1]+1:pipes_idx[i]]

            if ret is None and pipes_idx[i] is None: # no pipes
                subprocess_args = { 'env': arg[1], 'check': True }

            elif ret is None: # pipes but first command
                subprocess_args = { 'env': arg[1], 'check': True, 'capture_output': True }
            
            elif pipes_idx[i] is not None: # pipes but not last command
                subprocess_args = { 'env': arg[1], 'check': True, 'input': ret.stdout, 'capture_output': True }
            
            else: # pipes and last command
                subprocess_args = { 'env': arg[1], 'check': True, 'input': ret.stdout }

            ret = subprocess.run(cmd, **subprocess_args)

def update_system():
    timestamp = write_timestamp()

    update_pipeline = read_update_pipeline_file(timestamp)

    subprocess_run_sync(update_pipeline)

def rollback_update():
    if not os.path.isfile(TIMESTAMP_FILE):
        raise FileNotFoundError('No update performed on this system yet')

    timestamp = read_timestamp()

    with open(PACMAN_LOG, 'r') as f:
        operations = [
            [
                datetime.datetime.fromisoformat(log.split(']')[0][1:]), # time 0
                log.split(']')[2][1:].split(' ')[0], # operation 1
                log.split(']')[2][1:].split(' ')[1], # package name 2
                log.split(']')[2][1:].split('(')[1][:-2] # version 3
            ]
            for log in f.readlines()
            if is_date(log.split(']')[0][1:])
                and log.split(']')[1][2:] == 'ALPM'
                and log.split(']')[2][1:].split(' ')[0] in ['installed', 'upgraded', 'removed', 'reinstalled']
                and datetime.datetime.fromisoformat(log.split(']')[0][1:]) >= timestamp
        ]

    inst_and_rem = [ [line[2], line[3], line[1]] for line in operations if line[1] in ['installed', 'removed'] ]
    tallier = collections.defaultdict(lambda: 0)    
    for pkg in inst_and_rem:
        if pkg[2] == 'installed':
            tallier[pkg[0]] += 1
        else:
            tallier[pkg[0]] -= 1

    upg_names = []
    upgrades = []
    for line in operations:
        if line[1] != 'upgraded' or line[2] in upg_names:
            continue
            
        upgrades.append([line[2], line[3].split(' -> ')[0]])
        upg_names.append(line[2])

    rem_names = []
    removals = []
    for line in operations:
        if line[1] != 'removed' or tallier[line[2]] >= 0 or line[2] in [ upg[0] for upg in upgrades ] or line[2] in rem_names:
            continue

        removals.append([line[2], line[3]])
        rem_names.append(line[2])

    installs = [ [line[2], line[3]] for line in operations if line[1] == 'installed' and tallier[line[2]] > 0 ]
    reinstalls = [ [line[2], line[3]] for line in operations if line[1] == 'reinstalled' ]

    package_glob = '*.pkg.tar.*[!.sig]'
    pacman_cache = glob.glob(f'{PACMAN_CACHE_LOC}/{package_glob}')
    aur_cache = glob.glob(f'{AUR_CACHE_LOC}/**/{package_glob}')
    aur_rebuild_cache = glob.glob(f'{AUR_REBUILD_CACHE_LOC}/{timestamp.isoformat()}/**/{package_glob}', recursive=True)

    upgrades_matched = search_cache(upgrades, pacman_cache, aur_cache)
    installs_matched = [ line[0] for line in installs ]
    removals_matched = search_cache(removals, pacman_cache, aur_cache)
    reinstalls_matched = search_cache(reinstalls, [], aur_rebuild_cache)

    rollback_process_blueprint = [
        [ ['sudo', 'pacman', '-U', '--noconfirm'], upgrades_matched, None ], # must be first
        [ ['sudo', 'pacman', '-R', '--noconfirm'], installs_matched, None ], # before installing removed packages due to incompatibilities
        [ ['sudo', 'pacman', '-U', '--noconfirm'], removals_matched, None ], # see above
        [ ['sudo', 'pacman', '-U', '--noconfirm'], reinstalls_matched, None ] # must be last; reinstall only packages reinstalled during an update
    ]

    rollback_process = create_rollback_process(rollback_process_blueprint)
    subprocess_run_sync(rollback_process)

    write_timestamp()

def generate():
    if os.path.isfile(PIPELINE_FILE):
        raise FileExistsError(f'Pipeline file already exists at {PIPELINE_FILE}. Move it or delete it, then run this command again.')

    stub_pipeline = [
        UpdateStep('put your update command here', 'put a (case sensitive) keyword here to use special environment, leave this field empty to not use it; valid keywords are explained below'),
        UpdateStep('commands defined here run sequentially', 'cache_rebuild -> modifies XDG_CACHE_HOME, use this keyword when rebuilding AUR packages')
    ]

    stub_json = json.dumps(stub_pipeline, indent=4, cls=CustomJsonEncoder)
    stub_json = stub_json.replace('"##<', "").replace('>##"', "").replace('\'', "\"")

    with open(PIPELINE_FILE, mode='w+') as f:
        f.write(stub_json)

    print(f'Generated stub file at {PIPELINE_FILE}.')

def edit():
    if not os.path.isfile(PIPELINE_FILE):
        raise FileNotFoundError(f"Pipeline file doesn't exists at {PIPELINE_FILE}. Generate it using sysman update generate.")

    subprocess.run([os.environ['EDITOR'], PIPELINE_FILE])

def help():
    print('Usage: sysman update COMMAND')
    print()
    print('Available COMMANDs:')
    print(f'{"help":<20}Prints this message.')
    print(f'{"generate":<20}Generates an empty pipeline file.')
    print(f'{"edit":<20}Opens the pipeline file in $EDITOR.')
    print(f'{"run":<20}Updates the system according to the pipeline file.')
    print(f'{"rollback":<20}Rollbacks the system to the state before the last update. All changes in packages (installs, uninstalls) since that time will be lost!')

def main(args: list[str]):
    pathlib.Path(CACHE_DIR).mkdir(parents=True, exist_ok=True)

    if len(args) != 1 or args[0] not in [ 'generate', 'edit', 'run', 'rollback' ]:
        help()

    elif args[0] == 'generate':
        generate()

    elif args[0] == 'edit':
        edit()
    
    elif args[0] == 'run':
        update_system()
    
    elif args[0] == 'rollback':
        choice = input('Are you sure? y/N: ')

        if choice != '' and choice in 'Yy':
            rollback_update()
