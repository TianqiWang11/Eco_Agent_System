"""Export UE actor names/tags for an exact database tree-id audit.

Run inside UnrealEditor-Cmd with PythonScriptPlugin enabled. This script only
loads levels and reads actor metadata; it never saves a level or modifies an
asset.
"""

from __future__ import annotations

import json
import os
import traceback

import unreal


DEFAULT_MAPS = [
    "/Game/Maps/Map_HomePag",
    "/Game/Base/Maps/CheBaLing_EarthL1",
    "/Game/Base/Maps/CheBaLing_L2",
    "/Game/Base/Maps/CheBaLing_L3",
    "/Game/Base/Maps/Map_11",
    "/Game/Base/Maps/Sub_LCCAreaBorder",
    "/Game/Chebaling/Map/Chebaling",
    "/Game/Chebaling/Map/Chebaling1",
    "/Game/Chebaling/Map/Chebaling2",
    "/Game/Chebaling/Map/Chebaling2_New",
    "/Game/Chebaling/Map/Chebaling3",
]


def _actor_record(actor: unreal.Actor) -> dict[str, object]:
    tags = [str(tag) for tag in actor.get_editor_property("tags")]
    try:
        label = actor.get_actor_label()
    except Exception:
        label = ""
    return {
        "name": actor.get_name(),
        "label": label,
        "tags": tags,
        "class": actor.get_class().get_name(),
    }


def main() -> None:
    output = os.environ.get("CHEBALING_UE_AUDIT_OUTPUT")
    if not output:
        raise RuntimeError("CHEBALING_UE_AUDIT_OUTPUT is required")
    requested = os.environ.get("CHEBALING_UE_AUDIT_MAPS", "")
    maps = [item.strip() for item in requested.split(";") if item.strip()] or DEFAULT_MAPS
    result: dict[str, object] = {"maps": [], "errors": []}

    for map_path in maps:
        unreal.log(f"CHEBALING_AUDIT loading {map_path}")
        try:
            if not unreal.EditorAssetLibrary.does_asset_exist(map_path):
                raise RuntimeError("map asset does not exist")
            unreal.EditorLevelLibrary.load_level(map_path)
            actors = unreal.EditorLevelLibrary.get_all_level_actors()
            result["maps"].append(
                {
                    "map": map_path,
                    "actor_count": len(actors),
                    "actors": [_actor_record(actor) for actor in actors if actor],
                }
            )
            unreal.log(f"CHEBALING_AUDIT read {len(actors)} actors from {map_path}")
        except Exception as exc:
            result["errors"].append(
                {"map": map_path, "error": str(exc), "traceback": traceback.format_exc()}
            )
            unreal.log_error(f"CHEBALING_AUDIT failed {map_path}: {exc}")

    os.makedirs(os.path.dirname(os.path.abspath(output)), exist_ok=True)
    with open(output, "w", encoding="utf-8") as handle:
        json.dump(result, handle, ensure_ascii=False, indent=2)
    unreal.log(f"CHEBALING_AUDIT wrote {output}")


if __name__ == "__main__":
    main()
