#!/usr/bin/env python3
import argparse
import hashlib
import json
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import quote

SKIPPED_ROOTS = {".git", ".gradle", "build"}
STATE_FILE_NAME = ".manifest-state.json"

STATIC_MODS = [
    {
        "path": "mods/enderscape-neoforge-2.1.0+mc1.21.1.jar",
        "url": "https://github.com/stepreme/IWNIL/releases/download/es-2.10/enderscape-neoforge-2.1.0+mc1.21.1.jar",
        "sha512": "a3aedb8acfb05e6a7cec7623d814aa6150fefd8d8bf06ee9a811d9dc4c0dfed7eb013c3deb403ed4600d3a9d1a1a3400b6afaffc7115c6003d89b7453e0aa9d6"
    },
    {
        "path": "mods/timm-1.1.3-NeoForge.jar",
        "url": "https://github.com/CrawKatt/timm/releases/download/NeoForge/timm-1.1.3-NeoForge.jar",
        "sha512": "1f5974106ca001e08e2f34245a43ab277aa863dd034da15b1dbf605f5bd14229c282cd3bde8cbfabb3d324525a52a6be97a14d2581f585ae347f2fb665217486"
    }
]


def sha512_file(file_path: Path) -> str:
    digest = hashlib.sha512()
    with file_path.open("rb") as stream:
        while True:
            chunk = stream.read(1024 * 1024)
            if not chunk:
                break
            digest.update(chunk)
    return digest.hexdigest()


def make_url(base_url: str, relative_path: str) -> str:
    return f"{base_url.rstrip('/')}/{quote(relative_path, safe='/-_.~')}"


def collect_files(pack_root: Path, base_url: str) -> list[dict[str, str]]:
    files: list[dict[str, str]] = []

    for source_root in sorted(pack_root.iterdir()):
        if not source_root.is_dir():
            continue
        if source_root.name.startswith(".") or source_root.name in SKIPPED_ROOTS:
            continue

        for file_path in sorted(source_root.rglob("*")):
            if not file_path.is_file():
                continue

            relative = file_path.relative_to(pack_root).as_posix()
            
            # Пропускаем modrinth.index.json, если он находится в pack_root
            if relative == "modrinth.index.json":
                continue

            files.append(
                {
                    "path": relative,
                    "url": make_url(base_url, relative),
                    "sha512": sha512_file(file_path),
                }
            )

    options_path = pack_root / "options.txt"
    if options_path.is_file():
        relative = "options.txt"
        files.append(
            {
                "path": relative,
                "url": make_url(base_url, relative),
                "sha512": sha512_file(options_path),
            }
        )

    files.sort(key=lambda item: item["path"])
    return files


def load_known_paths(state_path: Path) -> set[str]:
    if not state_path.is_file():
        return set()

    try:
        state = json.loads(state_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return set()

    paths = state.get("knownPaths", [])
    if not isinstance(paths, list):
        return set()
    return {path for path in paths if isinstance(path, str)}


def save_known_paths(state_path: Path, known_paths: set[str]) -> None:
    state_path.write_text(
        json.dumps({"knownPaths": sorted(known_paths)}, indent=2, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )


def load_resource_packs_to_remove(file_path: Path) -> list[str]:
    if not file_path.is_file():
        return []
    
    resource_packs = []
    with file_path.open("r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if line and not line.startswith("#"):
                resource_packs.append(line)
    return resource_packs

def load_mods_to_remove(file_path: Path) -> list[str]:
    if not file_path.is_file():
        return []
    
    mods = []
    with file_path.open("r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if line and not line.startswith("#"):
                mods.append(line)
    return mods

def load_modrinth(modrinth_path: Path) -> list[dict[str, str]]:
    if not modrinth_path.is_file():
        return []
    
    try:
        with modrinth_path.open("r", encoding="utf-8") as f:
            index = json.load(f)
            
        files = []
        for file_data in index.get("files", []):
            path_str = file_data.get("path", "")
            
            # Игнорируем отключенные моды (.disabled)
            if path_str.endswith(".disabled"):
                continue

            files.append({
                "path": path_str,
                "url": file_data["downloads"][0],
                "sha512": file_data["hashes"]["sha512"]
            })
        return files
    except Exception as e:
        print(f"Warning: Failed to parse modrinth.index.json: {e}")
        return []


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Generate PackPulseMod manifest.json")
    parser.add_argument("--pack-root", required=True, help="Folder with mods/config/resourcepacks/shaderpacks")
    parser.add_argument(
        "--base-url", 
        default="https://raw.githubusercontent.com/stepreme/IWNIL/main/opt/packpulse/server-pack/", 
        help="Base URL for files"
    )
    parser.add_argument("--output", required=True, help="Output path for manifest.json")
    parser.add_argument("--modrinth", default="modrinth.index.json", help="Path to modrinth.index.json file")
    parser.add_argument("--name", default="PackPulse Pack", help="Manifest pack name")
    parser.add_argument("--version", default=datetime.now(timezone.utc).strftime("%Y.%m.%d-%H%M%S"), help="Pack version")
    parser.add_argument("--minecraft-version", default="1.21.1", help="Minecraft version")
    parser.add_argument("--loader", default="neoforge", help="Loader name")
    parser.add_argument("--neoforge-version", default="21.1.228", help="NeoForge version")
    parser.add_argument("--version-id", default="packpulse-pack", help="Version id")
    parser.add_argument("--profile-name", default="PackPulse Pack", help="Profile name")
    parser.add_argument("--mods-to-remove", default=None, help="Path to a .txt file listing mod IDs to remove")
    parser.add_argument("--resource-packs-to-remove", default=None, help="Path to a .txt file listing resource pack IDs to remove")
    return parser.parse_args()


def main() -> None:
    args = parse_args()

    pack_root = Path(args.pack_root).resolve()
    output_path = Path(args.output).resolve()
    output_path.parent.mkdir(parents=True, exist_ok=True)
    
    modrinth_path = Path(args.modrinth).resolve()
    if not modrinth_path.is_file():
        modrinth_path = Path.cwd() / "modrinth.index.json"

    final_files = []
    seen_paths = set()

    # 1. Локальные файлы (приоритет 1)
    local_files = collect_files(pack_root, args.base_url)
    for file_obj in local_files:
        final_files.append(file_obj)
        seen_paths.add(file_obj["path"])

    # 2. Статичные моды (приоритет 2)
    for sm in STATIC_MODS:
        if sm["path"] not in seen_paths:
            final_files.append(sm)
            seen_paths.add(sm["path"])

    # 3. Modrinth (приоритет 3 - с фильтрацией дублей и .disabled файлов)
    modrinth_files = load_modrinth(modrinth_path)
    for mf in modrinth_files:
        if mf["path"] not in seen_paths:
            final_files.append(mf)
            seen_paths.add(mf["path"])

    current_paths = {item["path"] for item in final_files}
    state_path = output_path.parent / STATE_FILE_NAME
    known_paths = load_known_paths(state_path)
    delete_paths = sorted(known_paths - current_paths)
    save_known_paths(state_path, known_paths | current_paths)

    mods_to_remove_list = []
    if args.mods_to_remove:
        mods_to_remove_path = Path(args.mods_to_remove).resolve()
        mods_to_remove_list = load_mods_to_remove(mods_to_remove_path)

    resource_packs_to_remove_list = []
    if args.resource_packs_to_remove:
        resource_packs_to_remove_path = Path(args.resource_packs_to_remove).resolve()
        resource_packs_to_remove_list = load_resource_packs_to_remove(resource_packs_to_remove_path)

    manifest = {
        "name": args.name,
        "version": args.version,
        "minecraftVersion": args.minecraft_version,
        "loader": args.loader,
        "neoForgeVersion": args.neoforge_version,
        "versionId": args.version_id,
        "profileName": args.profile_name,
        "files": final_files,
        "delete": delete_paths,
        "modsToRemove": mods_to_remove_list,
        "resourcePacksToRemove": resource_packs_to_remove_list,
    }

    with output_path.open("w", encoding="utf-8") as stream:
        json.dump(manifest, stream, indent=2, ensure_ascii=False)
        stream.write("\n")

    print(f"Manifest generated: {output_path}")
    print(f"Total files in manifest: {len(final_files)}")
    print(f"Files marked for delete: {len(delete_paths)}")
    print(f"Mods marked for selective removal: {len(mods_to_remove_list)}")
    print(f"Resource packs marked for selective removal: {len(resource_packs_to_remove_list)}")
    args = parse_args()

    pack_root = Path(args.pack_root).resolve()
    output_path = Path(args.output).resolve()
    output_path.parent.mkdir(parents=True, exist_ok=True)
    
    modrinth_path = Path(args.modrinth).resolve()
    if not modrinth_path.is_file():
        modrinth_path = Path.cwd() / "modrinth.index.json"

    final_files = []
    seen_paths = set()

    # 1. Локальные файлы (приоритет 1)
    local_files = collect_files(pack_root, args.base_url)
    for file_obj in local_files:
        final_files.append(file_obj)
        seen_paths.add(file_obj["path"])

    # 2. Статичные моды (приоритет 2)
    for sm in STATIC_MODS:
        if sm["path"] not in seen_paths:
            final_files.append(sm)
            seen_paths.add(sm["path"])

    # 3. Modrinth (приоритет 3 - с фильтрацией дублей и .disabled файлов)
    modrinth_files = load_modrinth(modrinth_path)
    for mf in modrinth_files:
        if mf["path"] not in seen_paths:
            final_files.append(mf)
            seen_paths.add(mf["path"])

    current_paths = {item["path"] for item in final_files}
    state_path = output_path.parent / STATE_FILE_NAME
    known_paths = load_known_paths(state_path)
    delete_paths = sorted(known_paths - current_paths)
    save_known_paths(state_path, known_paths | current_paths)

    manifest = {
        "name": args.name,
        "version": args.version,
        "minecraftVersion": args.minecraft_version,
        "loader": args.loader,
        "neoForgeVersion": args.neoforge_version,
        "versionId": args.version_id,
        "profileName": args.profile_name,
        "files": final_files,
        "delete": delete_paths,
    }

    with output_path.open("w", encoding="utf-8") as stream:
        json.dump(manifest, stream, indent=2, ensure_ascii=False)
        stream.write("\n")

    print(f"Manifest generated: {output_path}")
    print(f"Total files in manifest: {len(final_files)}")
    print(f"Files marked for delete: {len(delete_paths)}")


if __name__ == "__main__":
    main()