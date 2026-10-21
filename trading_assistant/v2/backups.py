"""Portable, consistent SQLite backups and verified restore into an empty directory."""
from __future__ import annotations

import hashlib
import json
import sqlite3
import zipfile
from datetime import datetime, timezone
from pathlib import Path, PurePosixPath
from tempfile import TemporaryDirectory


def create_backup(data_dir, output):
    root, output=Path(data_dir).resolve(),Path(output).resolve()
    if not root.is_dir():raise ValueError('Pasta de dados não encontrada')
    if output.exists():raise ValueError('Escolha um nome novo para preservar o backup existente')
    output.parent.mkdir(parents=True,exist_ok=True)
    manifest={'version':1,'created_at':datetime.now(timezone.utc).isoformat(),'files':{}}
    with TemporaryDirectory() as directory:
        staged=Path(directory)
        files=[path for path in root.rglob('*') if path.is_file() and path!=output
               and 'backups' not in path.relative_to(root).parts and path.suffix not in ('.zip','.tmp')
               and not str(path).endswith(('-wal','-shm'))]
        for path in files:
            relative=path.relative_to(root).as_posix()
            target=staged/relative;target.parent.mkdir(parents=True,exist_ok=True)
            if path.suffix=='.sqlite':
                source=sqlite3.connect(f'file:{path.as_posix()}?mode=ro',uri=True)
                dest=sqlite3.connect(target)
                try:source.backup(dest)
                finally:source.close();dest.close()
            else:
                target.write_bytes(path.read_bytes())
            manifest['files'][relative]=hashlib.sha256(target.read_bytes()).hexdigest()
        temporary=output.with_suffix(output.suffix+'.tmp')
        try:
            with zipfile.ZipFile(temporary,'w',compression=zipfile.ZIP_DEFLATED) as archive:
                archive.writestr('manifest.json',json.dumps(manifest,indent=2))
                for relative in manifest['files']:archive.write(staged/relative,'data/'+relative)
            temporary.replace(output)
        finally:
            if temporary.exists():temporary.unlink()
    return {'path':str(output),'files':len(manifest['files']),'sha256':hashlib.sha256(output.read_bytes()).hexdigest()}


def restore_backup(archive_path,destination):
    destination=Path(destination).resolve()
    if destination.exists() and (not destination.is_dir() or any(destination.iterdir())):
        raise ValueError('Restaure em uma pasta vazia; os dados atuais não serão sobrescritos')
    verified={}
    with zipfile.ZipFile(archive_path) as archive:
        manifest=json.loads(archive.read('manifest.json'))
        if manifest.get('version')!=1:raise ValueError('Versão de backup desconhecida')
        if sum(item.file_size for item in archive.infolist())>1_000_000_000:raise ValueError('Backup acima do limite de restauração')
        for relative,digest in manifest['files'].items():
            path=PurePosixPath(relative)
            target=(destination/relative).resolve()
            if path.is_absolute() or '..' in path.parts or ':' in relative or not target.is_relative_to(destination):
                raise ValueError('Caminho inválido no backup')
            raw=archive.read('data/'+relative)
            if hashlib.sha256(raw).hexdigest()!=digest:raise ValueError('Backup alterado ou incompleto: hash inválido')
            if relative.endswith('.sqlite'):
                with TemporaryDirectory() as directory:
                    temp=Path(directory)/'check.sqlite';temp.write_bytes(raw)
                    database=sqlite3.connect(temp)
                    try:
                        if database.execute('PRAGMA integrity_check').fetchone()[0]!='ok':raise ValueError('Banco corrompido no backup')
                    finally:database.close()
            verified[relative]=raw
    destination.mkdir(parents=True,exist_ok=True)
    for relative,raw in verified.items():
        target=destination/relative;target.parent.mkdir(parents=True,exist_ok=True);target.write_bytes(raw)
    return {'directory':str(destination),'files':len(verified)}
