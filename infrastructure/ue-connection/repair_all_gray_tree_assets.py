import re

import unreal


ROOTS = ("/Game/Meimu", "/Game/Tree")


def package_asset_path(data):
    return f"{data.package_name}.{data.asset_name}"


def connect_texture(material, texture, parameter_name, sampler_type, y, output_name, prop):
    texture_object = unreal.MaterialEditingLibrary.create_material_expression(
        material, unreal.MaterialExpressionTextureObjectParameter, -660, y
    )
    texture_object.set_editor_property("parameter_name", parameter_name)
    texture_object.set_editor_property("texture", texture)

    sample = unreal.MaterialEditingLibrary.create_material_expression(
        material, unreal.MaterialExpressionTextureSample, -400, y
    )
    sample.set_editor_property("sampler_type", sampler_type)
    connected = unreal.MaterialEditingLibrary.connect_material_expressions(
        texture_object, "", sample, "Tex"
    )
    if not connected:
        raise RuntimeError(f"Could not connect {parameter_name} on {material.get_path_name()}")
    if not unreal.MaterialEditingLibrary.connect_material_property(
        sample, output_name, prop
    ):
        raise RuntimeError(f"Could not connect {prop} on {material.get_path_name()}")
    return sample


registry = unreal.AssetRegistryHelpers.get_asset_registry()
repaired_materials = 0
repaired_slots = 0

for root in ROOTS:
    assets = registry.get_assets_by_path(root, recursive=True)
    by_folder = {}
    for data in assets:
        by_folder.setdefault(str(data.package_path), []).append(data)

    for data in assets:
        if str(data.asset_class_path.asset_name) != "Material":
            continue
        material = data.get_asset()
        if material is None:
            continue
        if unreal.MaterialEditingLibrary.get_used_textures(material):
            continue

        material_name = str(data.asset_name)
        prefix = re.sub(r"(?:_Branch|_Mesh)?_Mat$", "", material_name)
        if prefix == material_name:
            continue

        siblings = {
            str(item.asset_name).lower(): item
            for item in by_folder.get(str(data.package_path), [])
        }
        color_data = siblings.get(f"{prefix}_Color_png_Tex".lower())
        normal_data = siblings.get(f"{prefix}_Normal_png_Tex".lower())
        if color_data is None:
            unreal.log_warning(
                f"GRAY_REPAIR no exact color texture for {data.package_name}"
            )
            continue

        color = color_data.get_asset()
        normal = normal_data.get_asset() if normal_data else None
        if color is None:
            raise RuntimeError(f"Color texture failed to load: {color_data.package_name}")

        unreal.MaterialEditingLibrary.delete_all_material_expressions(material)
        color_sample = connect_texture(
            material,
            color,
            "BaseColorTexture",
            unreal.MaterialSamplerType.SAMPLERTYPE_COLOR,
            -100,
            "RGB",
            unreal.MaterialProperty.MP_BASE_COLOR,
        )

        if material.get_editor_property("blend_mode") == unreal.BlendMode.BLEND_MASKED:
            unreal.MaterialEditingLibrary.connect_material_property(
                color_sample, "A", unreal.MaterialProperty.MP_OPACITY_MASK
            )

        if normal is not None:
            normal.set_editor_property(
                "compression_settings", unreal.TextureCompressionSettings.TC_NORMALMAP
            )
            normal.set_editor_property("srgb", False)
            unreal.EditorAssetLibrary.save_loaded_asset(normal, False)
            connect_texture(
                material,
                normal,
                "NormalTexture",
                unreal.MaterialSamplerType.SAMPLERTYPE_NORMAL,
                170,
                "RGB",
                unreal.MaterialProperty.MP_NORMAL,
            )

        roughness = unreal.MaterialEditingLibrary.create_material_expression(
            material, unreal.MaterialExpressionConstant, -390, 390
        )
        roughness.set_editor_property("r", 0.68)
        unreal.MaterialEditingLibrary.connect_material_property(
            roughness, "", unreal.MaterialProperty.MP_ROUGHNESS
        )

        unreal.MaterialEditingLibrary.recompile_material(material)
        if not unreal.EditorAssetLibrary.save_loaded_asset(material, False):
            raise RuntimeError(f"Material failed to save: {data.package_name}")
        repaired_materials += 1
        unreal.log(f"GRAY_REPAIR material={data.package_name}")


for root in ROOTS:
    for data in registry.get_assets_by_path(root, recursive=True):
        if str(data.asset_class_path.asset_name) != "StaticMesh":
            continue
        mesh = data.get_asset()
        if mesh is None:
            continue
        slots = list(mesh.get_editor_property("static_materials"))
        if not any(slot.material_interface is None for slot in slots):
            continue

        folder_assets = registry.get_assets_by_path(str(data.package_path), recursive=False)
        materials = {
            str(item.asset_name).lower(): item.get_asset()
            for item in folder_assets
            if str(item.asset_class_path.asset_name) in ("Material", "MaterialInstanceConstant")
        }
        fallback_materials = [value for key, value in sorted(materials.items()) if value]
        changed = False
        for index, slot in enumerate(slots):
            if slot.material_interface is not None:
                continue
            slot_name = str(slot.material_slot_name).lower()
            replacement = materials.get(slot_name)
            if replacement is None and index < len(fallback_materials):
                replacement = fallback_materials[index]
            if replacement is None:
                unreal.log_warning(
                    f"GRAY_REPAIR no material for empty slot mesh={data.package_name} slot={index} name={slot_name}"
                )
                continue
            slot.set_editor_property("material_interface", replacement)
            repaired_slots += 1
            changed = True
            unreal.log(
                f"GRAY_REPAIR slot mesh={data.package_name} slot={index} material={replacement.get_path_name()}"
            )
        if changed:
            mesh.set_editor_property("static_materials", slots)
            if not unreal.EditorAssetLibrary.save_loaded_asset(mesh, False):
                raise RuntimeError(f"Mesh failed to save: {data.package_name}")


unreal.log(
    f"GRAY_REPAIR SUMMARY materials={repaired_materials} slots={repaired_slots}"
)

