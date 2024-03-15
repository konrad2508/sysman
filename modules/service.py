_name = 'service'
_desc = 'Manage services ran on your system by declaring them in a json file'

import json
import os
import shutil
import subprocess
from dataclasses import dataclass, is_dataclass, fields, asdict


SERVICEFILE_DIR = f'{os.environ["HOME"]}/.config/sysman'
SERVICEFILE = f'{SERVICEFILE_DIR}/services.json'
SERVICEFILE_OLD = f'{SERVICEFILE}.old'


@dataclass
class Service:
    name: str
    comment: str
    svc_type: str

    def __hash__(self) -> int:
        return hash(self.name + self.svc_type)

    def __eq__(self, __value: object) -> bool:
        return self.name == __value.name\
            and self.svc_type == __value.svc_type


@dataclass
class LocalService(Service):
    service_file: str
    service_script_file: str

    def __hash__(self) -> int:
        return hash(self.name + self.svc_type + self.service_file + self.service_script_file)

    def __eq__(self, __value: object) -> bool:
        return self.name == __value.name\
            and self.svc_type == __value.svc_type\
            and self.service_file == __value.service_file\
            and self.service_script_file == __value.service_script_file


@dataclass
class ServiceFile:
    system_services: list[Service]
    local_system_services: list[LocalService]
    user_services: list[Service]
    local_user_services: list[LocalService]

    def get_all_services(self) -> list[Service]:
        return self.system_services + self.user_services
    
    def get_all_local_services(self) -> list[LocalService]:
        return self.local_system_services + self.local_user_services


class CustomJsonEncoder(json.JSONEncoder):
    def default(self, o):
        if type(o) is ServiceFile:
            return { k.name: self.default(getattr(o, k.name)) for k in fields(o) }

        if type(o) is list:
            return [ self.default(i) for i in o ]

        if type(o) is Service:
            obj_dict = asdict(o)
            del obj_dict['svc_type']

            return f'##<{obj_dict}>##'

        if is_dataclass(o):
            obj_dict = asdict(o)
            del obj_dict['svc_type']

            return obj_dict

        return super().default(o)


def read_file_to_servicefile(path: str) -> ServiceFile:
    with open(path, 'r') as f:
        file_content = json.load(f)

    services = ServiceFile(
        [ Service(**o, svc_type='system') for o in file_content.get('system_services', []) ],
        [ LocalService(**o, svc_type='system') for o in file_content.get('local_system_services', []) ],
        [ Service(**o, svc_type='user') for o in file_content.get('user_services', []) ],
        [ LocalService(**o, svc_type='user') for o in file_content.get('local_user_services', []) ]
    )

    return services

def get_states_of_services(queried_services: list[Service]) -> list[tuple[Service, str]]:
    system_services = [ svc for svc in queried_services if svc.svc_type == 'system' ]
    user_services = [ svc for svc in queried_services if svc.svc_type == 'user' ]

    if len(system_services) > 0:
        system_services_states = subprocess.run([
            'sudo',
            'systemctl',
            'is-enabled',
            *[ svc.name for svc in system_services ]], stdout=subprocess.PIPE, text=True).stdout.split('\n')[:-1]
    else:
        system_services_states = []

    if len(user_services) > 0:
        user_services_states = subprocess.run([
            'systemctl',
            '--user',
            'is-enabled',
            *[ svc.name for svc in user_services ]], stdout=subprocess.PIPE, text=True).stdout.split('\n')[:-1]
    else:
        user_services_states = []

    services_states = zip(system_services + user_services, system_services_states + user_services_states)

    return list(services_states)

def enable_system_service(svc: Service):
    subprocess.run(['sudo', 'systemctl', 'enable', '--now', svc.name])

def enable_user_service(svc: Service):
    subprocess.run(['systemctl', '--user', 'enable', '--now', svc.name])

def enable_service(svc: Service):
    if svc.svc_type == 'system':
        enable_system_service(svc)
    else:
        enable_user_service(svc)

def disable_system_service(svc: Service):
    subprocess.run(['sudo', 'systemctl', 'disable', svc.name])

def disable_user_service(svc: Service):
    subprocess.run(['systemctl', '--user', 'disable', svc.name])

def disable_service(svc: Service):
    if svc.svc_type == 'system':
        disable_system_service(svc)
    else:
        disable_user_service(svc)

def sudo_copy(src: str, dst: str):
    expanded_src = os.path.expanduser(src)

    if not os.path.isfile(expanded_src):
        raise FileNotFoundError(f'File {src} does not exist')

    subprocess.run(['sudo', 'cp', expanded_src, dst])

def sudo_remove(file: str):
    if os.path.isfile(file):
        subprocess.run(['sudo', 'rm', file])

def install_system_service_file(svc: LocalService):
    svc_filepath = svc.service_file
    svc_file = svc_filepath.split('/')[-1]

    sudo_copy(svc_filepath, f'/etc/systemd/system/{svc_file}')

def install_user_service_file(svc: LocalService):
    svc_filepath = svc.service_file
    svc_file = svc_filepath.split('/')[-1]

    sudo_copy(svc_filepath, f'/etc/systemd/user/{svc_file}')

def install_service_file(svc: LocalService):
    if svc.svc_type == 'system':
        install_system_service_file(svc)
    else:
        install_user_service_file(svc)

def uninstall_system_service_file(svc: LocalService):
    svc_filepath = svc.service_file
    svc_file = svc_filepath.split('/')[-1]

    sudo_remove(f'/etc/systemd/system/{svc_file}')

def uninstall_user_service_file(svc: LocalService):
    svc_filepath = svc.service_file
    svc_file = svc_filepath.split('/')[-1]

    sudo_remove(f'/etc/systemd/user/{svc_file}')

def uninstall_service_file(svc: LocalService):
    if svc.svc_type == 'system':
        uninstall_system_service_file(svc)
    else:
        uninstall_user_service_file(svc)

def install_system_service_script(svc: LocalService):
    svc_script_filepath = svc.service_script_file

    if svc_script_filepath != '':
        svc_script = svc_script_filepath.split('/')[-1]

        sudo_copy(svc_script_filepath, f'/usr/bin/{svc_script}')

def install_user_service_script(svc: LocalService):
    svc_script_filepath = svc.service_script_file

    if svc_script_filepath != '':
        svc_script = svc_script_filepath.split('/')[-1]

        sudo_copy(svc_script_filepath, f'/usr/bin/{svc_script}')

def install_service_script(svc: LocalService):
    if svc.svc_type == 'system':
        install_system_service_script(svc)
    else:
        install_user_service_script(svc)

def uninstall_system_service_script(svc: LocalService):
    svc_script_filepath = svc.service_script_file

    if svc_script_filepath != '':
        svc_script = svc_script_filepath.split('/')[-1]

        sudo_remove(f'/usr/bin/{svc_script}')

def uninstall_user_service_script(svc: LocalService):
    svc_script_filepath = svc.service_script_file

    if svc_script_filepath != '':
        svc_script = svc_script_filepath.split('/')[-1]

        sudo_remove(f'/usr/bin/{svc_script}')

def uninstall_service_script(svc: LocalService):
    if svc.svc_type == 'system':
        uninstall_system_service_script(svc)
    else:
        uninstall_user_service_script(svc)

def generate():
    if os.path.isfile(SERVICEFILE):
        raise FileExistsError(f'Service file already exists at {SERVICEFILE}. Move it or delete it, then run this command again.')

    stub_servicefile = ServiceFile(
        [ Service('name of the service', 'comment for the service', 'system') ],
        [ LocalService(
            'name of the service',
            'comment for the service',
            'system',
            'absolute path to the .service file',
            '(optional) absolute path to the script used in the .service file, if unused put empty string here')
        ],
        [ Service('name of the service', 'comment for the service', 'user') ],
        [ LocalService(
            'name of the service',
            'comment for the service',
            'user',
            'absolute path to the .service file',
            '(optional) absolute path to the script used in the .service file, if unused put empty string here')
        ]
    )

    stub_json = json.dumps(stub_servicefile, indent=4, cls=CustomJsonEncoder)
    stub_json = stub_json.replace('"##<', "").replace('>##"', "").replace('\'', "\"")

    with open(SERVICEFILE, mode='w+') as f:
        f.write(stub_json)

    print(f'Generated stub file at {SERVICEFILE}.')

def sync():
    if not os.path.isfile(SERVICEFILE):
        raise FileNotFoundError(f"Service file doesn't exists at {SERVICEFILE}. Generate it using sysman service generate.")

    services = read_file_to_servicefile(SERVICEFILE)

    # 1. deactivate activated services from services.old
    if os.path.isfile(SERVICEFILE_OLD):
        services_old = read_file_to_servicefile(SERVICEFILE_OLD)

        services_setified = set(services.get_all_services() + services.get_all_local_services())
        services_old_setified = set(services_old.get_all_services() + services_old.get_all_local_services())
        services_old_to_remove = list(services_old_setified - services_setified)

        services_old_states = get_states_of_services(services_old_to_remove)

        active_services_old = filter(lambda o: type(o[0]) is Service and o[1] != 'disabled', services_old_states)
        for svc in active_services_old:
            service = svc[0]
            state = svc[1]

            if state == 'enabled':
                disable_service(service)

        active_services_old_local = filter(lambda o: type(o[0]) is LocalService and o[1] != 'not-found', services_old_states)
        for svc in active_services_old_local:
            service = svc[0]
            state = svc[1]

            if state == 'enabled':
                disable_service(service)

            uninstall_service_file(service)
            uninstall_service_script(service)

    # 2. activate inactive services
    services_states = get_states_of_services(services.get_all_services() + services.get_all_local_services())
    inactive_services = filter(lambda o: o[1] != 'enabled', services_states)

    for svc in inactive_services:
        service = svc[0]
        state = svc[1]

        if state == 'not-found':
            if type(service) is Service:
                raise FileNotFoundError(f'Service {service.name} does not exist')

            install_service_script(service)
            install_service_file(service)

        enable_service(service)

    # 3. overwrite servicefile.old
    if os.path.isfile(SERVICEFILE_OLD):
        os.remove(SERVICEFILE_OLD)
    shutil.copy2(SERVICEFILE, SERVICEFILE_OLD)

def edit():
    if not os.path.isfile(SERVICEFILE):
        raise FileNotFoundError(f"Service file doesn't exists at {SERVICEFILE}. Generate it using sysman service generate.")

    subprocess.run([os.environ['EDITOR'], SERVICEFILE])

def reinstall(service_name: str):
    if not os.path.isfile(SERVICEFILE):
        raise FileNotFoundError(f"Service file doesn't exists at {SERVICEFILE}. Generate it using sysman service generate.")

    if not os.path.isfile(SERVICEFILE_OLD):
        raise FileNotFoundError(f"Sync system with sysman service sync first before running this command.")

    services = read_file_to_servicefile(SERVICEFILE)
    services_old = read_file_to_servicefile(SERVICEFILE_OLD)

    services_filtered = list(filter(lambda svc: svc.name == service_name, services.get_all_services() + services.get_all_local_services()))
    services_old_filtered = list(filter(lambda svc: svc.name == service_name, services_old.get_all_services() + services_old.get_all_local_services()))

    if len(services_filtered) == 0 or len(services_old_filtered) == 0:
        raise FileNotFoundError(f'Service {service_name} not found in the service file.')

    svc = get_states_of_services(services_filtered)[0]

    service = svc[0]
    service_old = services_old_filtered[0]
    state = svc[1]

    if state == 'enabled':
        disable_service(service)

    if type(service) is LocalService:
        uninstall_service_file(service_old)
        uninstall_service_script(service_old)

        install_service_script(service)
        install_service_file(service)

    enable_service(service)

    os.remove(SERVICEFILE_OLD)
    shutil.copy2(SERVICEFILE, SERVICEFILE_OLD)


def help():
    print('Usage: sysman service COMMAND [ARGUMENT]')
    print()
    print('Available COMMANDs:')
    print(f'{"help":<20}Prints this message.')
    print(f'{"sync":<20}Syncs services with the service file.')
    print(f'{"generate":<20}Generates an empty service file.')
    print(f'{"edit":<20}Opens the service file in $EDITOR.')
    print(f'{"reinstall":<20}Reinstalls the service specified by ARGUMENT.')

def main(args: list[str]):
    if len(args) == 0 or args[0] not in [ 'sync', 'generate', 'edit', 'reinstall' ]:
        help()

    elif args[0] == 'sync':
        sync()
    
    elif args[0] == 'generate':
        generate()
    
    elif args[0] == 'edit':
        edit()
    
    elif args[0] == 'reinstall':
        if len(args) == 1:
            help()
        
        else:
            reinstall(args[1])
