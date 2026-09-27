# Local Tools: business computation/retrieval, without agent orchestration.
# Agent local ecology capability.
import pandas as pd


def build_agb_report(summary: dict, species_df: pd.DataFrame) -> dict:
    """
    组装 AGB 结果的人类可读报告文本。

    Args:
        summary: AGB 汇总统计（总量、均值、缺失等）。
        species_df: 物种 AGB 贡献表（通常为 Top N）。

    Returns:
        包含 answer/note/summary/top_species 的响应字典。
    """
    top_species_text = "、".join(
        [f"{row['species_cn']}（{row['agb_kg']:.1f} kg）" for _, row in species_df.iterrows()]
    )

    answer = (
        f"基于当前可计算样本，共有 {summary['valid_agb_records']} 条单木记录完成了地上生物量（AGB）估算，"
        f"约有 {summary['missing_agb_records']} 条记录因树高或木材密度缺失未参与计算。"
        f"当前样本的 AGB 总量约为 {summary['agb_sum_kg']:.2f} kg，"
        f"平均单木 AGB 约为 {summary['agb_mean_kg']:.2f} kg，"
        f"最大单木 AGB 约为 {summary['agb_max_kg']:.2f} kg。"
        f"从树种贡献来看，当前样本中 AGB 贡献较高的树种包括：{top_species_text}。"
    )

    note = (
        "说明：该结果基于当前 Excel 子集数据和论文中的 AGB 异速生长方程计算，"
        "属于地上生物量估算结果，不等同于最终正式碳汇结论。"
    )

    return {
        "answer": answer,
        "note": note,
        "summary": summary,
        "top_species": species_df.to_dict(orient="records"),
    }
