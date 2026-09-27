import unreal


REPAIRS = {
    "/Game/Meimu/nongda5/光叶山矾2/0104069/0104069_Branch_Mat": (
        "/Game/Meimu/nongda5/光叶山矾2/0104069/0104069_Color_png_Tex",
        "/Game/Meimu/nongda5/光叶山矾2/0104069/0104069_Normal_png_Tex",
    ),
    "/Game/Meimu/nongda5/光叶山矾2/0104069/Material_Branch_Mat": (
        "/Game/Meimu/nongda5/光叶山矾2/0104069/Material_Color_png_Tex",
        "/Game/Meimu/nongda5/光叶山矾2/0104069/Material_Normal_png_Tex",
    ),
    "/Game/Meimu/nongda5/光叶山矾2/0612149/0612149_Branch_Mat": (
        "/Game/Meimu/nongda5/光叶山矾2/0612149/0612149_Color_png_Tex",
        "/Game/Meimu/nongda5/光叶山矾2/0612149/0612149_Normal_png_Tex",
    ),
    "/Game/Meimu/nongda5/光叶山矾2/0612149/Material_Branch_Mat": (
        "/Game/Meimu/nongda5/光叶山矾2/0612149/Material_Color_png_Tex",
        "/Game/Meimu/nongda5/光叶山矾2/0612149/Material_Normal_png_Tex",
    ),
    "/Game/Meimu/nongda5/钩毛紫珠2/2307041/shugan_Branch_Mat": (
        "/Game/Meimu/nongda5/钩毛紫珠2/2307041/shugan_Color_png_Tex",
        None,
    ),
    "/Game/Meimu/nongda5/钩毛紫珠2/2309011/2309011_Branch_Mat": (
        "/Game/Meimu/nongda5/钩毛紫珠2/2309011/2309011_Color_png_Tex",
        "/Game/Meimu/nongda5/钩毛紫珠2/2309011/2309011_Normal_png_Tex",
    ),
    "/Game/Meimu/nongda5/钩毛紫珠2/2309011/shugan_Branch_Mat": (
        "/Game/Meimu/nongda5/钩毛紫珠2/2309011/shugan_Color_png_Tex",
        None,
    ),
}


def load_required(path):
    asset = unreal.EditorAssetLibrary.load_asset(path)
    if asset is None:
        raise RuntimeError(f"Required asset is missing: {path}")
    return asset


def connect_texture_object(texture_object, texture_sample, label):
    input_names = unreal.MaterialEditingLibrary.get_material_expression_input_names(texture_sample)
    unreal.log(f"TREE_REPAIR {label}_inputs={','.join(str(name) for name in input_names)}")
    texture_input = next(
        (
            str(name)
            for name in input_names
            if str(name).lower() in ("tex", "texture", "textureobject")
        ),
        "Tex",
    )
    connected = unreal.MaterialEditingLibrary.connect_material_expressions(
        texture_object, "", texture_sample, texture_input
    )
    unreal.log(f"TREE_REPAIR {label}_connection={connected} input={texture_input}")
    if not connected:
        raise RuntimeError(f"Failed to connect {label} texture object")


for material_path, (color_path, normal_path) in REPAIRS.items():
    material = load_required(material_path)
    color_texture = load_required(color_path)
    normal_texture = load_required(normal_path) if normal_path else None

    unreal.MaterialEditingLibrary.delete_all_material_expressions(material)

    color_object = unreal.MaterialEditingLibrary.create_material_expression(
        material, unreal.MaterialExpressionTextureObjectParameter, -620, -80
    )
    color_object.set_editor_property("parameter_name", "BaseColorTexture")
    color_object.set_editor_property("texture", color_texture)
    color_sample = unreal.MaterialEditingLibrary.create_material_expression(
        material, unreal.MaterialExpressionTextureSample, -380, -80
    )
    connect_texture_object(color_object, color_sample, "color")
    unreal.MaterialEditingLibrary.connect_material_property(
        color_sample, "RGB", unreal.MaterialProperty.MP_BASE_COLOR
    )

    if material.get_editor_property("blend_mode") == unreal.BlendMode.BLEND_MASKED:
        unreal.MaterialEditingLibrary.connect_material_property(
            color_sample, "A", unreal.MaterialProperty.MP_OPACITY_MASK
        )

    if normal_texture is not None:
        normal_texture.set_editor_property(
            "compression_settings", unreal.TextureCompressionSettings.TC_NORMALMAP
        )
        normal_texture.set_editor_property("srgb", False)
        if not unreal.EditorAssetLibrary.save_loaded_asset(normal_texture, False):
            raise RuntimeError(f"Failed to save normal texture settings: {normal_path}")

        normal_object = unreal.MaterialEditingLibrary.create_material_expression(
            material, unreal.MaterialExpressionTextureObjectParameter, -620, 180
        )
        normal_object.set_editor_property("parameter_name", "NormalTexture")
        normal_object.set_editor_property("texture", normal_texture)
        normal_sample = unreal.MaterialEditingLibrary.create_material_expression(
            material, unreal.MaterialExpressionTextureSample, -380, 180
        )
        normal_sample.set_editor_property(
            "sampler_type", unreal.MaterialSamplerType.SAMPLERTYPE_NORMAL
        )
        connect_texture_object(normal_object, normal_sample, "normal")
        unreal.MaterialEditingLibrary.connect_material_property(
            normal_sample, "RGB", unreal.MaterialProperty.MP_NORMAL
        )

    unreal.MaterialEditingLibrary.recompile_material(material)
    if not unreal.EditorAssetLibrary.save_loaded_asset(material, False):
        raise RuntimeError(f"Failed to save repaired material: {material_path}")
    unreal.log(f"TREE_REPAIR repaired={material_path}")

unreal.log(f"TREE_REPAIR complete count={len(REPAIRS)}")
