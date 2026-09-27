import unreal


ROOTS = (
    "/Game/Meimu",
    "/Game/Tree",
    "/Game/Chebaling",
    "/Game/DevelopMent",
)
DEFAULT_MARKERS = (
    "/Engine/EngineMaterials/DefaultMaterial",
    "/Engine/EngineMaterials/WorldGridMaterial",
)


def asset_path(obj):
    return obj.get_path_name() if obj else "<None>"


registry = unreal.AssetRegistryHelpers.get_asset_registry()
mesh_count = 0
slot_count = 0
bad_slots = []
material_objects = {}

for root in ROOTS:
    for data in registry.get_assets_by_path(root, recursive=True):
        class_name = str(data.asset_class_path.asset_name)
        if class_name not in ("StaticMesh", "SkeletalMesh"):
            continue
        mesh = data.get_asset()
        if mesh is None:
            unreal.log_warning(f"GRAY_DIAG LOAD_FAILED {data.package_name}")
            continue
        mesh_count += 1
        if class_name == "StaticMesh":
            materials = [slot.material_interface for slot in mesh.get_editor_property("static_materials")]
        else:
            materials = [slot.material_interface for slot in mesh.get_editor_property("materials")]
        for index, material in enumerate(materials):
            slot_count += 1
            path = asset_path(material)
            if material:
                material_objects[path] = material
            if material is None or any(marker in path for marker in DEFAULT_MARKERS):
                bad_slots.append((str(data.package_name), index, path))

parentless_instances = []
textureless_materials = []
bad_textures = []

for path in sorted(material_objects):
    material = material_objects[path]
    if material is None:
        continue
    if isinstance(material, unreal.MaterialInstanceConstant):
        parent = material.get_editor_property("parent")
        if parent is None:
            parentless_instances.append(path)
        base = parent
    else:
        base = material

    try:
        textures = unreal.MaterialEditingLibrary.get_used_textures(material)
    except Exception:
        textures = []
    if not textures:
        textureless_materials.append(path)
    for texture in textures:
        try:
            width = texture.blueprint_get_size_x()
            height = texture.blueprint_get_size_y()
        except Exception:
            width = height = -1
        if width <= 0 or height <= 0:
            bad_textures.append((path, asset_path(texture), width, height))

unreal.log(
    "GRAY_DIAG SUMMARY "
    f"meshes={mesh_count} slots={slot_count} unique_materials={len(material_objects)} "
    f"bad_slots={len(bad_slots)} parentless_instances={len(parentless_instances)} "
    f"textureless_materials={len(textureless_materials)} bad_textures={len(bad_textures)}"
)
for mesh_path, index, material_path in bad_slots:
    unreal.log_warning(f"GRAY_DIAG BAD_SLOT mesh={mesh_path} slot={index} material={material_path}")
for path in parentless_instances:
    unreal.log_warning(f"GRAY_DIAG PARENTLESS material={path}")
for path in textureless_materials:
    unreal.log_warning(f"GRAY_DIAG TEXTURELESS material={path}")
for material_path, texture_path, width, height in bad_textures:
    unreal.log_warning(
        f"GRAY_DIAG BAD_TEXTURE material={material_path} texture={texture_path} size={width}x{height}"
    )
