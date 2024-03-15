_name = 'package'
_desc = 'Manage packages on your system by declaring them in a json file.'

import json
import subprocess
import os
import tempfile
from dataclasses import dataclass


LISTFILE_DIR = f'{os.environ["HOME"]}/.config/sysman'
LISTFILE = f'{LISTFILE_DIR}/packages.json'
AUR_HELPER = 'yay'


@dataclass
class Package:
    name: str
    group: str
    comment: str

    def __hash__(self) -> int:
        return hash(self.name)

    def __eq__(self, __value: object) -> bool:
        return self.name == __value.name


@dataclass
class PackagePrettified:
    name: str
    comment: str


@dataclass
class PackageGroup:
    group_name: str
    packages: list[str]


class CustomJsonEncoder(json.JSONEncoder):
    def default(self, o):
        if isinstance(o, PackagePrettified | Package):
            return f'##<{o.__dict__}>##'


def get_listfile_packages(listfile_path: str) -> set[Package]:
    listfile_packages = []

    if os.path.exists(listfile_path):
        with open(listfile_path) as f:
            data = json.load(f)

            for pac_group in data:
                group_name = pac_group['group_name']
                listfile_packages = listfile_packages + [ Package(package['name'], group_name, package['comment']) for package in pac_group['packages'] ]

    listfile_packages = set(listfile_packages)

    return listfile_packages

def get_all_packages() -> set[Package]:
    pacman_output = subprocess.run(['pacman', '-Qqe'], stdout=subprocess.PIPE, text=True)
    pacman_output = pacman_output.stdout.split('\n')[:-1]

    all_packages = set([ Package(package, '', '') for package in pacman_output ])

    return all_packages

def affirmative(decision: str) -> bool:
    return decision in ['Y', 'y', 'yes', 'Yes', 'YES']

def install_packages(packages: set[Package]) -> None:
    pkgs = [ package.name for package in packages ]
    subprocess.run([AUR_HELPER, '-S', *pkgs])

def uninstall_packages(packages: set[Package]) -> None:
    pkgs = [ package.name for package in packages ]
    subprocess.run(['sudo', 'pacman', '-Rs', *pkgs])

def json_dump_correct_format(obj: list) -> str:
    formatted_json = json.dumps(obj, indent=4, cls=CustomJsonEncoder)
    formatted_json = formatted_json.replace('"##<', "").replace('>##"', "").replace('\'', "\"")

    return formatted_json

def save_packages_to_listfile(listfile: str, packages: set[Package]) -> None:
    package_groups = { package.group for package in packages }

    parsed_package_groups = []
    for group in package_groups:
        sorted_group_packages = sorted([
            PackagePrettified(package.name, package.comment)
            for package in packages
            if package.group == group ], key=lambda x: x.name.lower()
        )

        parsed_package_groups.append(PackageGroup(group, sorted_group_packages))

    parsed_package_groups = sorted(parsed_package_groups, key=lambda x: x.group_name.lower() if x.group_name != '' else ' ') # else &nbsp

    with open(listfile, mode='w+') as f:
        f.write(json_dump_correct_format([ group.__dict__ for group in parsed_package_groups ]))

def get_user_edited_packages(unedited_packages: set[Package]) -> list[Package]:
    sorted_unedited_packages = sorted(unedited_packages, key=lambda x: x.name.lower())

    tmp = tempfile.NamedTemporaryFile(delete=False, mode='w')
    tmp.write(json_dump_correct_format(sorted_unedited_packages))
    tmp.close()

    subprocess.run([os.environ['EDITOR'], tmp.name])

    with open(tmp.name) as f:
        edited_packages = json.load(f)
        edited_packages = [
            Package(package['name'], package['group'] if package['group'] else '', package['comment'])
            for package in edited_packages
        ]

    os.remove(tmp.name)

    edited_packages = set(edited_packages)

    return edited_packages

def sync():
    listfile_packages = get_listfile_packages(LISTFILE)
    system_packages = get_all_packages()

    # 1. packages from the list are missing in the system
    sys_missing_packages = listfile_packages - system_packages
    sys_missing_packages_count = len(sys_missing_packages)

    if sys_missing_packages_count > 0:
        print(f'There are {sys_missing_packages_count} packages missing from the system:')
        print(', '.join(sorted([ package.name for package in sys_missing_packages ])))
        decision = input('Install them? y/N: ')

        if affirmative(decision):
            install_packages(sys_missing_packages)

        else:
            decision = input('Remove these packages from the list? y/N: ')

            if affirmative(decision):
                listfile_packages = { package for package in listfile_packages if package not in sys_missing_packages }
                save_packages_to_listfile(LISTFILE, listfile_packages)

    # 2. packages in the system are missing from the list
    list_missing_packages = system_packages - listfile_packages
    list_missing_packages_count = len(list_missing_packages)

    if list_missing_packages_count > 0:
        print(f'There are {list_missing_packages_count} packages missing from the list:')
        print(', '.join(sorted([ package.name for package in list_missing_packages ])))
        decision = input('Add them to the list? y/N: ')

        if affirmative(decision):
            edited_new_packages = get_user_edited_packages(list_missing_packages)

            listfile_packages = listfile_packages | edited_new_packages
            save_packages_to_listfile(LISTFILE, listfile_packages)

        else:
            decision = input('Remove these packages from the system? y/N: ')

            if affirmative(decision):
                uninstall_packages(list_missing_packages)

def edit():
    subprocess.run([os.environ['EDITOR'], LISTFILE])

def help():
    print('Usage: sysman package COMMAND')
    print()
    print('Available COMMANDs:')
    print(f'{"help":<20}Prints this message.')
    print(f'{"sync":<20}Syncs system packages with the package file.')
    print(f'{"edit":<20}Opens the package file in $EDITOR.')

def main(args: list[str]):
    if len(args) != 1 or args[0] not in [ 'sync', 'edit' ]:
        help()

    elif args[0] == 'sync':
        sync()
    
    elif args[0] == 'edit':
        edit()
