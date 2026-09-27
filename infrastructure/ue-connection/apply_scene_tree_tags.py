"""Copy database-matched numeric Actor Labels into runtime Actor Tags.

Run inside UnrealEditor-Cmd. The allowlist and report paths are supplied by
environment variables. Only actors whose exact label is in the allowlist are
modified, and only the map packages containing those actors are saved.
"""

from __future__ import annotations

import json
import os
import sys
import traceback

import unreal

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from audit_scene_actor_ids import DEFAULT_MAPS


def main() -> None:
    allowlist_path = os.environ.get("CHEBALING_UE_TAG_ALLOWLIST")
    report_path = os.environ.get("CHEBALING_UE_TAG_REPORT")
    if not allowlist_path or not report_path:
        raise RuntimeError("CHEBALING_UE_TAG_ALLOWLIST and CHEBALING_UE_TAG_REPORT are required")

    with open(allowlist_path, encoding="utf-8") as handle:
        payload = json.load(handle)
    allowed = {str(row["tree_id"]).strip() for row in payload["trees"]}
    requested = os.environ.get("CHEBALING_UE_AUDIT_MAPS", "")
    maps = [item.strip() for item in requested.split(";") if item.strip()] or DEFAULT_MAPS
    report: dict[str, object] = {
        "allowlist_count": len(allowed),
        "tagged_tree_ids": [],
        "modified_actor_count": 0,
        "already_tagged_actor_count": 0,
        "modified_packages": {},
        "errors": [],
    }
    tagged_ids: set[str] = set()
    modified_actor_paths: set[str] = set()
    already_tagged_paths: set[str] = set()
    package_counts: dict[str, int] = {}

    for map_path in maps:
        unreal.log(f"CHEBALING_TAG loading {map_path}")
        try:
            unreal.EditorLevelLibrary.load_level(map_path)
            packages_to_save: set[str] = set()
            for actor in unreal.EditorLevelLibrary.get_all_level_actors():
                if not actor:
                    continue
                label = str(actor.get_actor_label()).strip()
                if label not in allowed:
                    continue
                tagged_ids.add(label)
                actor_path = actor.get_path_name()
                existing = [str(tag) for tag in actor.get_editor_property("tags")]
                if any(tag.casefold() == label.casefold() for tag in existing):
                    already_tagged_paths.add(actor_path)
                    continue
                actor.modify()
                actor.set_editor_property("tags", [*actor.get_editor_property("tags"), unreal.Name(label)])
                modified_actor_paths.add(actor_path)
                package = actor.get_outermost().get_name()
                packages_to_save.add(package)
                package_counts[package] = package_counts.get(package, 0) + 1

            for package in sorted(packages_to_save):
                if not unreal.EditorAssetLibrary.save_asset(package, only_if_is_dirty=True):
                    raise RuntimeError(f"failed to save modified map package {package}")
        except Exception as exc:
            report["errors"].append(
                {"map": map_path, "error": str(exc), "traceback": traceback.format_exc()}
            )
            unreal.log_error(f"CHEBALING_TAG failed {map_path}: {exc}")

    report["tagged_tree_ids"] = sorted(tagged_ids)
    report["tagged_tree_id_count"] = len(tagged_ids)
    report["modified_actor_count"] = len(modified_actor_paths)
    report["already_tagged_actor_count"] = len(already_tagged_paths)
    report["modified_packages"] = package_counts
    missing = sorted(allowed - tagged_ids)
    report["missing_tree_ids"] = missing
    report["missing_tree_id_count"] = len(missing)

    os.makedirs(os.path.dirname(os.path.abspath(report_path)), exist_ok=True)
    with open(report_path, "w", encoding="utf-8") as handle:
        json.dump(report, handle, ensure_ascii=False, indent=2)
    unreal.log(
        f"CHEBALING_TAG tagged_ids={len(tagged_ids)} actors={len(modified_actor_paths)} "
        f"packages={len(package_counts)} missing={len(missing)}"
    )
    if report["errors"] or missing:
        raise RuntimeError("scene tree tag migration was incomplete; inspect the report")


main()
