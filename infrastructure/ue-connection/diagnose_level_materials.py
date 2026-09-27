import unreal


MAPS = (
    "/Game/Chebaling/Map/Chebaling2_New",
    "/Game/DevelopMent/Maps/Nongda1",
    "/Game/DevelopMent/Maps/Nongda2",
    "/Game/DevelopMent/Maps/Nongda3",
    "/Game/DevelopMent/Maps/Nongda4",
)
DEFAULT_MARKERS = (
    "/Engine/EngineMaterials/DefaultMaterial",
    "/Engine/EngineMaterials/WorldGridMaterial",
)


def object_path(obj):
    return obj.get_path_name() if obj else "<None>"


level_subsystem = unreal.get_editor_subsystem(unreal.LevelEditorSubsystem)
actor_subsystem = unreal.get_editor_subsystem(unreal.EditorActorSubsystem)

for map_path in MAPS:
    if not level_subsystem.load_level(map_path):
        unreal.log_error(f"LEVEL_DIAG LOAD_FAILED map={map_path}")
        continue

    actors = actor_subsystem.get_all_level_actors()
    component_count = 0
    slot_count = 0
    bad = []
    material_uses = {}
    landscapes = []

    for actor in actors:
        actor_name = actor.get_path_name()
        class_name = actor.get_class().get_name()

        if "Landscape" in class_name:
            for prop in ("landscape_material", "landscape_hole_material"):
                try:
                    material = actor.get_editor_property(prop)
                except Exception:
                    continue
                landscapes.append((actor_name, prop, object_path(material)))

        components = []
        seen = set()
        for component_class in (
            unreal.StaticMeshComponent,
            unreal.InstancedStaticMeshComponent,
            unreal.HierarchicalInstancedStaticMeshComponent,
            unreal.SkeletalMeshComponent,
        ):
            for component in actor.get_components_by_class(component_class):
                key = component.get_path_name()
                if key not in seen:
                    seen.add(key)
                    components.append(component)

        for component in components:
            component_count += 1
            try:
                count = component.get_num_materials()
            except Exception:
                continue
            for index in range(count):
                slot_count += 1
                material = component.get_material(index)
                path = object_path(material)
                if material:
                    material_uses.setdefault(path, (material, component.get_path_name()))
                if material is None or any(marker in path for marker in DEFAULT_MARKERS):
                    mesh = None
                    for prop in ("static_mesh", "skeletal_mesh"):
                        try:
                            mesh = component.get_editor_property(prop)
                        except Exception:
                            continue
                        if mesh:
                            break
                    bad.append(
                        (
                            actor_name,
                            component.get_path_name(),
                            object_path(mesh),
                            index,
                            path,
                        )
                    )

    unreal.log(
        f"LEVEL_DIAG SUMMARY map={map_path} actors={len(actors)} "
        f"components={component_count} slots={slot_count} bad={len(bad)} "
        f"landscapes={len(landscapes)} unique_materials={len(material_uses)}"
    )
    for actor_name, component_name, mesh_path, index, material_path in bad:
        unreal.log_warning(
            f"LEVEL_DIAG BAD map={map_path} actor={actor_name} component={component_name} "
            f"mesh={mesh_path} slot={index} material={material_path}"
        )
    for actor_name, prop, material_path in landscapes:
        unreal.log(
            f"LEVEL_DIAG LANDSCAPE map={map_path} actor={actor_name} "
            f"property={prop} material={material_path}"
        )
    inputless = []
    for material_path, (material, component_name) in material_uses.items():
        try:
            base = material.get_base_material()
        except Exception:
            base = material
        try:
            node = unreal.MaterialEditingLibrary.get_material_property_input_node(
                base, unreal.MaterialProperty.MP_BASE_COLOR
            )
        except Exception as error:
            unreal.log_warning(
                f"LEVEL_DIAG INPUT_API_FAILED material={material_path} error={error}"
            )
            node = "<api-failed>"
        if node is None:
            inputless.append((material_path, object_path(base), component_name))
    unreal.log(
        f"LEVEL_DIAG MATERIALS map={map_path} inputless_base_color={len(inputless)}"
    )
    for material_path, base_path, component_name in inputless:
        unreal.log_warning(
            f"LEVEL_DIAG INPUTLESS map={map_path} material={material_path} "
            f"base={base_path} component={component_name}"
        )
