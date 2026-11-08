"""Historial duradero en un repositorio privado, con versiones por commit atómico."""
from contextlib import contextmanager
from datetime import datetime, timezone
import json
import os
from pathlib import Path
import shlex
import subprocess
from tempfile import TemporaryDirectory
import time

from etiquetas import Registro


def configuracion():
    url, key = os.environ.get('HISTORIAL_GIT_URL'), os.environ.get('HISTORIAL_SSH_KEY')
    if not url:
        try:
            import streamlit as st
            url = st.secrets.get('HISTORIAL_GIT_URL')
            key = st.secrets.get('HISTORIAL_SSH_KEY')
        except (FileNotFoundError, KeyError, ImportError):
            pass
    return url, key


def git(folder, *args, env=None, check=True):
    result = subprocess.run(['git', '-C', str(folder), *args], env=env,
                            capture_output=True, text=True, timeout=45)
    if check and result.returncode:
        raise OSError('No se pudo acceder al historial permanente. Revisa su configuración de GitHub.')
    return result


@contextmanager
def checkout():
    url, key = configuracion()
    with TemporaryDirectory(prefix='etiquetas_historial_') as tmp:
        folder = Path(tmp)
        env = os.environ.copy()
        env['GIT_TERMINAL_PROMPT'] = '0'
        if key:
            private = folder / 'key'
            private.write_text(key.strip() + '\n', encoding='utf-8')
            private.chmod(0o600)
            known = Path(__file__).with_name('github_known_hosts')
            env['GIT_SSH_COMMAND'] = ('ssh -i ' + shlex.quote(str(private)) +
                ' -o IdentitiesOnly=yes -o StrictHostKeyChecking=yes -o UserKnownHostsFile=' + shlex.quote(str(known)))
        repo = folder / 'repo'
        git(folder, 'clone', '--depth=1', '--branch=main', url, str(repo), env=env)
        path = repo / 'versiones.json'
        records = json.loads(path.read_text(encoding='utf-8')) if path.exists() else []
        yield repo, records, env


def listar():
    with checkout() as (_, records, __):
        return [item['datos'] for item in reversed(records)]


def siguiente(proyecto, clave):
    with checkout() as (_, records, __):
        return max((item['datos']['version'] for item in records if item['clave'] == clave(proyecto)), default=0) + 1


def generar_y_guardar(proyecto, fecha, responsable, copias, exportador, clave):
    for attempt in range(5):
        with checkout() as (repo, records, env):
            version = max((item['datos']['version'] for item in records if item['clave'] == clave(proyecto)), default=0) + 1
            record = Registro.crear(proyecto, version, fecha, responsable)
            files = exportador(record, copias)
            records.append({'clave': clave(proyecto), 'datos': json.loads(record.codigo),
                            'creado': datetime.now(timezone.utc).isoformat()})
            (repo / 'versiones.json').write_text(json.dumps(records, ensure_ascii=False, indent=2), encoding='utf-8')
            git(repo, 'add', 'versiones.json', env=env)
            git(repo, '-c', 'user.name=Etiquetas de planos', '-c', 'user.email=etiquetas@users.noreply.github.com',
                'commit', '-m', 'Guardar versión de proyecto', env=env)
            # Un push rechazado por otro guardado concurrente recalcula la versión.
            if git(repo, 'push', 'origin', 'HEAD:main', env=env, check=False).returncode == 0:
                return record, files
        time.sleep(.1 * (attempt + 1))
    raise OSError('Otro usuario está guardando versiones. Vuelve a generar en unos segundos.')
