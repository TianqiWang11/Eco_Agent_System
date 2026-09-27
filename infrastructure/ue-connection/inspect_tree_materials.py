import unreal


MATERIALS = [
    "/Game/Meimu/nongda5/光叶山矾2/0104069/0104069_Branch_Mat",
    "/Game/Meimu/nongda5/光叶山矾2/0104069/Material_Branch_Mat",
    "/Game/Meimu/nongda5/光叶山矾2/0612149/0612149_Branch_Mat",
    "/Game/Meimu/nongda5/光叶山矾2/0612149/Material_Branch_Mat",
    "/Game/Meimu/nongda5/钩毛紫珠2/2307041/shugan_Branch_Mat",
    "/Game/Meimu/nongda5/钩毛紫珠2/2309011/2309011_Branch_Mat",
    "/Game/Meimu/nongda5/钩毛紫珠2/2309011/shugan_Branch_Mat",
]


unreal.log(
    "TREE_API MaterialEditingLibrary="
    + ",".join(name for name in dir(unreal.MaterialEditingLibrary) if "expression" in name.lower())
)
for class_name in ("MaterialEditorSubsystem", "MaterialEditingLibrary"):
    cls = getattr(unreal, class_name, None)
    unreal.log(
        f"TREE_API {class_name}="
        + (",".join(name for name in dir(cls) if "expression" in name.lower()) if cls else "<missing>")
    )

for material_path in MATERIALS:
    material = unreal.EditorAssetLibrary.load_asset(material_path)
    if material is None:
        unreal.log_error(f"TREE_MATERIAL missing material: {material_path}")
        continue

    unreal.log(f"TREE_MATERIAL material={material_path}")
    expressions = None
    for material_property in ("editor_only_data", "material_editor_only_data", "expression_collection"):
        try:
            value = material.get_editor_property(material_property)
            unreal.log(f"TREE_API material_property={material_property} value={value}")
        except Exception as error:
            unreal.log_warning(f"TREE_API material_property={material_property} error={error}")
            continue
        for collection_property in ("expressions", "expression_collection"):
            try:
                expressions = value.get_editor_property(collection_property)
                unreal.log(f"TREE_API collection_property={collection_property} count={len(expressions)}")
                break
            except Exception as error:
                unreal.log_warning(f"TREE_API collection_property={collection_property} error={error}")
        if expressions is not None:
            break
    if expressions is None:
        unreal.log_error("TREE_API no readable material expression API")
        break
    for index, expression in enumerate(expressions):
        if isinstance(expression, unreal.MaterialExpressionTextureSample):
            texture = expression.get_editor_property("texture")
            sampler_type = expression.get_editor_property("sampler_type")
            texture_path = texture.get_path_name() if texture else "<None>"
            unreal.log(
                f"TREE_SAMPLE index={index} sampler={sampler_type} texture={texture_path} "
                f"x={expression.material_expression_editor_x} y={expression.material_expression_editor_y}"
            )
