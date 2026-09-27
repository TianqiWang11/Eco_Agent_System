#include "TreeParamPanelWidget.h"

#include "ParametricTreeActor.h"
#include "TreeGeneratorSubsystem.h"
#include "TreePresetLibrary.h"

#include "Blueprint/WidgetTree.h"
#include "Components/Border.h"
#include "Components/Button.h"
#include "Components/CanvasPanel.h"
#include "Components/CanvasPanelSlot.h"
#include "Components/ComboBoxString.h"
#include "Components/HorizontalBox.h"
#include "Components/HorizontalBoxSlot.h"
#include "Components/ScrollBox.h"
#include "Components/SpinBox.h"
#include "Components/TextBlock.h"
#include "Components/VerticalBox.h"
#include "Components/VerticalBoxSlot.h"
#include "EngineUtils.h"
#include "Engine/GameInstance.h"

namespace
{
	FText MakeLabel(const FString& S) { return FText::FromString(S); }

	FSlateChildSize FillSize(float Value)
	{
		FSlateChildSize S;
		S.SizeRule = ESlateSizeRule::Fill;
		S.Value = Value;
		return S;
	}

	UTextBlock* MakeText(const FText& Text, const FLinearColor& Color = FLinearColor::White)
	{
		UTextBlock* TB = NewObject<UTextBlock>();
		TB->SetText(Text);
		TB->SetColorAndOpacity(FSlateColor(Color));
		return TB;
	}
}

void UTreeParamPanelWidget::NativeConstruct()
{
	Super::NativeConstruct();

	if (!Spin_TreeHeight)
	{
		BuildDefaultUI();
	}

	BuildParamRows();
	InitPresetCombo();
	BindWidgetEvents();
	BindActiveTree();
}

void UTreeParamPanelWidget::BuildDefaultUI()
{
	UCanvasPanel* Canvas = WidgetTree->ConstructWidget<UCanvasPanel>(UCanvasPanel::StaticClass(), TEXT("PanelCanvas"));
	WidgetTree->RootWidget = Canvas;

	UBorder* PanelBorder = WidgetTree->ConstructWidget<UBorder>(UBorder::StaticClass(), TEXT("PanelBorder"));
	PanelBorder->SetBrushColor(FLinearColor(0.02f, 0.025f, 0.03f, 0.85f));
	PanelBorder->SetPadding(FMargin(10, 8));
	UCanvasPanelSlot* BorderSlot = Canvas->AddChildToCanvas(PanelBorder);
	BorderSlot->SetAnchors(FAnchors(0.0f, 0.0f, 0.0f, 1.0f));
	BorderSlot->SetOffsets(FMargin(12.0f, 12.0f, 470.0f, -24.0f));

	UVerticalBox* ContentVB = WidgetTree->ConstructWidget<UVerticalBox>(UVerticalBox::StaticClass(), TEXT("ContentVB"));
	PanelBorder->SetContent(ContentVB);

	{
		UTextBlock* Title = MakeText(MakeLabel(TEXT("树木参数面板")), FLinearColor(0.85f, 0.95f, 1.0f));
		UVerticalBoxSlot* TitleSlot = ContentVB->AddChildToVerticalBox(Title);
		TitleSlot->SetPadding(FMargin(0, 0, 0, 4));
	}

	Text_Target = MakeText(MakeLabel(TEXT("目标：无激活树")), FLinearColor(1.0f, 0.8f, 0.4f));
	ContentVB->AddChildToVerticalBox(Text_Target)->SetPadding(FMargin(0, 0, 0, 2));

	Text_Derived = MakeText(MakeLabel(TEXT("—")), FLinearColor(0.75f, 0.85f, 0.75f));
	ContentVB->AddChildToVerticalBox(Text_Derived)->SetPadding(FMargin(0, 0, 0, 6));

	{
		UHorizontalBox* Row = WidgetTree->ConstructWidget<UHorizontalBox>(UHorizontalBox::StaticClass());
		ContentVB->AddChildToVerticalBox(Row)->SetPadding(FMargin(0, 2));
		UHorizontalBoxSlot* LabelSlot = Row->AddChildToHorizontalBox(
			MakeText(MakeLabel(TEXT("树种")), FLinearColor(0.8f, 0.8f, 0.8f)));
		LabelSlot->SetSize(FillSize(0.3f));
		LabelSlot->SetPadding(FMargin(0, 0, 8, 0));
		LabelSlot->SetVerticalAlignment(VAlign_Center);
		Combo_Preset = WidgetTree->ConstructWidget<UComboBoxString>(UComboBoxString::StaticClass(), TEXT("Combo_Preset"));
		UHorizontalBoxSlot* ComboSlot = Row->AddChildToHorizontalBox(Combo_Preset);
		ComboSlot->SetSize(FillSize(1.0f));
		ComboSlot->SetVerticalAlignment(VAlign_Center);
	}

	UScrollBox* RowsScroll = WidgetTree->ConstructWidget<UScrollBox>(UScrollBox::StaticClass(), TEXT("RowsScroll"));
	RowsScroll->SetScrollbarThickness(FVector2D(6.0f, 6.0f));
	UVerticalBoxSlot* ScrollSlot = ContentVB->AddChildToVerticalBox(RowsScroll);
	ScrollSlot->SetSize(FSlateChildSize(ESlateSizeRule::Fill));
	ScrollSlot->SetPadding(FMargin(0, 0, 0, 4));

	UVerticalBox* RowsVB = WidgetTree->ConstructWidget<UVerticalBox>(UVerticalBox::StaticClass(), TEXT("RowsVB"));
	RowsScroll->AddChild(RowsVB);

	auto AddSpin = [this, RowsVB](const FName& Name, const FString& Label, float Min, float Max, int32 Decimals, USpinBox*& OutSpin)
	{
		UHorizontalBox* Row = WidgetTree->ConstructWidget<UHorizontalBox>(UHorizontalBox::StaticClass());
		RowsVB->AddChildToVerticalBox(Row)->SetPadding(FMargin(0, 1.5f));
		UHorizontalBoxSlot* LSlot = Row->AddChildToHorizontalBox(
			MakeText(MakeLabel(Label), FLinearColor(0.8f, 0.8f, 0.8f)));
		LSlot->SetSize(FillSize(0.52f));
		LSlot->SetPadding(FMargin(0, 0, 8, 0));
		LSlot->SetVerticalAlignment(VAlign_Center);

		USpinBox* Spin = WidgetTree->ConstructWidget<USpinBox>(USpinBox::StaticClass(), Name);
		Spin->SetMinValue(Min);
		Spin->SetMaxValue(Max);
		Spin->SetMinFractionalDigits(0);
		Spin->SetMaxFractionalDigits(Decimals);
		Spin->SetDelta(0.f);
		UHorizontalBoxSlot* SSlot = Row->AddChildToHorizontalBox(Spin);
		SSlot->SetSize(FillSize(1.0f));
		SSlot->SetVerticalAlignment(VAlign_Center);
		OutSpin = Spin;
	};

	AddSpin(TEXT("Spin_TreeHeight"), TEXT("树高 (m)"), 0.5f, 120.0f, 2, Spin_TreeHeight);
	AddSpin(TEXT("Spin_DBH"), TEXT("胸径DBH (cm)"), 1.0f, 300.0f, 2, Spin_DBH);
	AddSpin(TEXT("Spin_CrownNS"), TEXT("冠幅南北 (m)"), 0.1f, 40.0f, 3, Spin_CrownNS);
	AddSpin(TEXT("Spin_CrownEW"), TEXT("冠幅东西 (m)"), 0.1f, 40.0f, 3, Spin_CrownEW);
	AddSpin(TEXT("Spin_CrownVolume"), TEXT("冠体积 (m³)"), 0.0f, 20000.0f, 1, Spin_CrownVolume);
	AddSpin(TEXT("Spin_CrownBaseHeight"), TEXT("枝下高 (m, 0=自动)"), 0.0f, 60.0f, 2, Spin_CrownBaseHeight);
	AddSpin(TEXT("Spin_RandomSeed"), TEXT("随机种子"), 0.0f, 9999999.0f, 0, Spin_RandomSeed);
	AddSpin(TEXT("Spin_Quality"), TEXT("质量档 1-3"), 1.0f, 3.0f, 0, Spin_Quality);
	AddSpin(TEXT("Spin_PrimaryBranches"), TEXT("主枝数"), 2.0f, 40.0f, 0, Spin_PrimaryBranches);
	AddSpin(TEXT("Spin_BranchAngle"), TEXT("分枝角 (°)"), 5.0f, 85.0f, 1, Spin_BranchAngle);
	AddSpin(TEXT("Spin_Taper"), TEXT("干形尖削度"), 0.3f, 1.8f, 2, Spin_Taper);
	AddSpin(TEXT("Spin_ApicalDominance"), TEXT("顶端优势 0-1"), 0.05f, 1.0f, 2, Spin_ApicalDominance);
	AddSpin(TEXT("Spin_LeafDensity"), TEXT("叶团密度 团/m³"), 1.0f, 300.0f, 0, Spin_LeafDensity);
	AddSpin(TEXT("Spin_LeafSize"), TEXT("叶团尺寸 (m)"), 0.05f, 2.0f, 2, Spin_LeafSize);
	AddSpin(TEXT("Spin_TrunkCount"), TEXT("主干数(丛生)"), 1.0f, 12.0f, 0, Spin_TrunkCount);

	UHorizontalBox* CurrentBtnRow = nullptr;
	int32 BtnRowCount = 0;
	auto AddBtn = [this, &CurrentBtnRow, &BtnRowCount](UVerticalBox* ParentVB, const FName& Name, const FString& Label, const FLinearColor& Tint, UButton*& OutBtn)
	{
		if (BtnRowCount % 3 == 0)
		{
			CurrentBtnRow = WidgetTree->ConstructWidget<UHorizontalBox>(UHorizontalBox::StaticClass());
			ParentVB->AddChildToVerticalBox(CurrentBtnRow)->SetPadding(FMargin(0, 2));
		}
		++BtnRowCount;
		UButton* Btn = WidgetTree->ConstructWidget<UButton>(UButton::StaticClass(), Name);
		Btn->SetBackgroundColor(Tint);
		Btn->SetContent(MakeText(MakeLabel(Label)));
		UHorizontalBoxSlot* BtnSlot = CurrentBtnRow->AddChildToHorizontalBox(Btn);
		BtnSlot->SetSize(FillSize(1.0f));
		BtnSlot->SetPadding(FMargin(3, 0));
		BtnSlot->SetVerticalAlignment(VAlign_Center);
		OutBtn = Btn;
	};
	AddBtn(ContentVB, TEXT("BTN_SpawnDefault"), TEXT("生成默认树"), FLinearColor(0.15f, 0.45f, 0.2f), BTN_SpawnDefault);
	AddBtn(ContentVB, TEXT("BTN_Apply"), TEXT("应用参数"), FLinearColor(0.15f, 0.3f, 0.5f), BTN_Apply);
	AddBtn(ContentVB, TEXT("BTN_RandomSeed"), TEXT("换随机种子"), FLinearColor(0.35f, 0.3f, 0.15f), BTN_RandomSeed);
	AddBtn(ContentVB, TEXT("BTN_Reset"), TEXT("重置预设"), FLinearColor(0.35f, 0.15f, 0.15f), BTN_Reset);
	AddBtn(ContentVB, TEXT("BTN_Close"), TEXT("关闭面板"), FLinearColor(0.25f, 0.25f, 0.28f), BTN_Close);
}

void UTreeParamPanelWidget::BuildParamRows()
{
	ParamRows.Reset();
	auto AddRow = [this](USpinBox* Spin, TFunction<float(const FTreeParams&)> Get, TFunction<void(FTreeParams&, float)> Set)
	{
		if (Spin)
		{
			ParamRows.Add({ Spin, MoveTemp(Get), MoveTemp(Set) });
		}
	};
	AddRow(Spin_TreeHeight,
		[](const FTreeParams& P) { return P.TreeHeight; },
		[](FTreeParams& P, float V) { P.TreeHeight = V; });
	AddRow(Spin_DBH,
		[](const FTreeParams& P) { return P.DBH * 100.0f; },
		[](FTreeParams& P, float V) { P.DBH = V / 100.0f; });
	AddRow(Spin_CrownNS,
		[](const FTreeParams& P) { return P.CrownWidthNS; },
		[](FTreeParams& P, float V) { P.CrownWidthNS = V; });
	AddRow(Spin_CrownEW,
		[](const FTreeParams& P) { return P.CrownWidthEW; },
		[](FTreeParams& P, float V) { P.CrownWidthEW = V; });
	AddRow(Spin_CrownVolume,
		[](const FTreeParams& P) { return P.CrownVolume; },
		[](FTreeParams& P, float V) { P.CrownVolume = V; });
	AddRow(Spin_CrownBaseHeight,
		[](const FTreeParams& P) { return P.CrownBaseHeight; },
		[](FTreeParams& P, float V) { P.CrownBaseHeight = V; });
	AddRow(Spin_RandomSeed,
		[](const FTreeParams& P) { return (float)P.RandomSeed; },
		[](FTreeParams& P, float V) { P.RandomSeed = (int32)V; });
	AddRow(Spin_Quality,
		[](const FTreeParams& P) { return (float)P.QualityLevel; },
		[](FTreeParams& P, float V) { P.QualityLevel = FMath::Clamp((int32)V, 1, 3); });
	AddRow(Spin_PrimaryBranches,
		[](const FTreeParams& P) { return (float)P.PrimaryBranchCount; },
		[](FTreeParams& P, float V) { P.PrimaryBranchCount = (int32)V; });
	AddRow(Spin_BranchAngle,
		[](const FTreeParams& P) { return P.BranchAngle; },
		[](FTreeParams& P, float V) { P.BranchAngle = V; });
	AddRow(Spin_Taper,
		[](const FTreeParams& P) { return P.Taper; },
		[](FTreeParams& P, float V) { P.Taper = V; });
	AddRow(Spin_ApicalDominance,
		[](const FTreeParams& P) { return P.ApicalDominance; },
		[](FTreeParams& P, float V) { P.ApicalDominance = V; });
	AddRow(Spin_LeafDensity,
		[](const FTreeParams& P) { return P.LeafClusterDensity; },
		[](FTreeParams& P, float V) { P.LeafClusterDensity = V; });
	AddRow(Spin_LeafSize,
		[](const FTreeParams& P) { return P.LeafClusterSize; },
		[](FTreeParams& P, float V) { P.LeafClusterSize = V; });
	AddRow(Spin_TrunkCount,
		[](const FTreeParams& P) { return (float)P.TrunkCount; },
		[](FTreeParams& P, float V) { P.TrunkCount = (int32)V; });
}

void UTreeParamPanelWidget::InitPresetCombo()
{
	if (!Combo_Preset)
	{
		return;
	}
	bSyncing = true;
	const TArray<FString> Names = UTreePresetLibrary::GetPresetDisplayNames();
	for (const FString& N : Names)
	{
		Combo_Preset->AddOption(N);
	}
	if (Names.Num() > 0)
	{
		Combo_Preset->SetSelectedOption(Names[0]);
	}
	bSyncing = false;
}

void UTreeParamPanelWidget::BindWidgetEvents()
{
	for (const FParamRow& Row : ParamRows)
	{
		if (Row.Spin)
		{
			Row.Spin->OnValueChanged.AddDynamic(this, &UTreeParamPanelWidget::HandleSpinValueChanged);
			Row.Spin->OnValueCommitted.AddDynamic(this, &UTreeParamPanelWidget::HandleSpinValueCommitted);
		}
	}
	if (Combo_Preset)
	{
		Combo_Preset->OnSelectionChanged.AddDynamic(this, &UTreeParamPanelWidget::HandlePresetChanged);
	}
	if (BTN_SpawnDefault) { BTN_SpawnDefault->OnClicked.AddDynamic(this, &UTreeParamPanelWidget::HandleSpawnClicked); }
	if (BTN_Apply)       { BTN_Apply->OnClicked.AddDynamic(this, &UTreeParamPanelWidget::HandleApplyClicked); }
	if (BTN_RandomSeed)  { BTN_RandomSeed->OnClicked.AddDynamic(this, &UTreeParamPanelWidget::HandleSeedClicked); }
	if (BTN_Reset)       { BTN_Reset->OnClicked.AddDynamic(this, &UTreeParamPanelWidget::HandleResetClicked); }
	if (BTN_Close)       { BTN_Close->OnClicked.AddDynamic(this, &UTreeParamPanelWidget::HandleCloseClicked); }
}

void UTreeParamPanelWidget::NativeDestruct()
{
	if (AParametricTree* Tree = BoundTree.Get())
	{
		Tree->OnParamsChanged.RemoveAll(this);
	}
	BoundTree = nullptr;
	Super::NativeDestruct();
}

void UTreeParamPanelWidget::NativeTick(const FGeometry& MyGeometry, float InDeltaTime)
{
	Super::NativeTick(MyGeometry, InDeltaTime);
	if (bCommitQueued && GetWorld() && GetWorld()->GetTimeSeconds() - LastChangeTime > 0.15)
	{
		bCommitQueued = false;
		CommitFromControls();
	}
}

void UTreeParamPanelWidget::CommitFromControls()
{
	if (bSyncing)
	{
		return;
	}
	AParametricTree* Tree = BoundTree.Get();
	if (!Tree)
	{
		if (UTreeGeneratorSubsystem* Subsystem = GetTreeSubsystem())
		{
			Tree = Subsystem->GetActiveTree();
			if (!Tree)
			{
				Tree = Subsystem->SpawnTree(UTreePresetLibrary::GetDefaultTreeParams(), FTransform::Identity);
			}
		}
		if (!Tree)
		{
			return;
		}
		BindActiveTree();
	}

	FTreeParams P = Tree->Params;
	for (const FParamRow& Row : ParamRows)
	{
		if (Row.Spin && Row.Set)
		{
			Row.Set(P, Row.Spin->GetValue());
		}
	}
	Tree->ApplyParams(P);
}

void UTreeParamPanelWidget::SyncFromTree()
{
	bSyncing = true;
	AParametricTree* Tree = BoundTree.Get();
	const FTreeParams P = Tree ? Tree->Params : UTreePresetLibrary::GetDefaultTreeParams();
	for (const FParamRow& Row : ParamRows)
	{
		if (Row.Spin && Row.Get)
		{
			Row.Spin->SetValue(Row.Get(P));
		}
	}
	if (Combo_Preset)
	{
		const TArray<FString> Names = UTreePresetLibrary::GetPresetDisplayNames();
		Combo_Preset->SetSelectedOption(Names.Num() > 0 ? Names[0] : TEXT(""));
	}
	bSyncing = false;

	if (Text_Target)
	{
		Text_Target->SetText(Tree
			? FText::FromString(FString::Printf(TEXT("目标：%s"), *Tree->GetName()))
			: FText::FromString(TEXT("目标：无激活树")));
	}
	RefreshDerived();
}

void UTreeParamPanelWidget::RefreshDerived()
{
	if (!Text_Derived)
	{
		return;
	}
	AParametricTree* Tree = BoundTree.Get();
	const FTreeParams P = Tree ? Tree->Params : UTreePresetLibrary::GetDefaultTreeParams();
	Text_Derived->SetText(FText::FromString(FString::Printf(
		TEXT("枝下高 %.2f m | 冠厚 %.2f m | 叶团 %d | 冠投影 %.1f m²"),
		UTreePresetLibrary::GetDerivedCrownBaseHeight(P),
		UTreePresetLibrary::GetDerivedCrownDepth(P),
		UTreePresetLibrary::GetDerivedLeafClusterCount(P),
		P.GetCrownProjectedArea())));
}

void UTreeParamPanelWidget::BindActiveTree()
{
	if (AParametricTree* Old = BoundTree.Get())
	{
		Old->OnParamsChanged.RemoveAll(this);
	}
	BoundTree = nullptr;
	if (UTreeGeneratorSubsystem* Subsystem = GetTreeSubsystem())
	{
		AParametricTree* Tree = Subsystem->GetActiveTree();
		if (!Tree)
		{
			if (UWorld* World = GetWorld())
			{
				for (TActorIterator<AParametricTree> It(World); It; ++It)
				{
					Tree = *It;
					break;
				}
			}
			if (Tree)
			{
				Subsystem->SetActiveTree(Tree);
			}
		}
		if (Tree)
		{
			BoundTree = Tree;
			Tree->OnParamsChanged.AddDynamic(this, &UTreeParamPanelWidget::HandleTreeParamsChanged);
		}
	}
	SyncFromTree();
}

void UTreeParamPanelWidget::HandleSpinValueChanged(float)
{
	if (bSyncing)
	{
		return;
	}
	bCommitQueued = true;
	LastChangeTime = GetWorld() ? GetWorld()->GetTimeSeconds() : 0.0;
}

void UTreeParamPanelWidget::HandleSpinValueCommitted(float, ETextCommit::Type CommitType)
{
	if (bSyncing || CommitType == ETextCommit::Default)
	{
		return;
	}
	bCommitQueued = true;
	LastChangeTime = 0.0;
}

void UTreeParamPanelWidget::HandlePresetChanged(FString SelectedItem, ESelectInfo::Type SelectionType)
{
	if (bSyncing || SelectedItem.IsEmpty())
	{
		return;
	}
	const FTreeParams Preset = UTreePresetLibrary::GetPresetByDisplayName(SelectedItem);
	if (UTreeGeneratorSubsystem* Subsystem = GetTreeSubsystem())
	{
		if (AParametricTree* Tree = Subsystem->GetActiveTree())
		{
			Tree->ApplyParams(Preset);
		}
		else
		{
			Subsystem->SpawnTree(Preset, FTransform::Identity);
			BindActiveTree();
		}
	}
}

void UTreeParamPanelWidget::HandleSpawnClicked()
{
	if (UTreeGeneratorSubsystem* Subsystem = GetTreeSubsystem())
	{
		Subsystem->DestroyActiveTree();
		Subsystem->SpawnTree(UTreePresetLibrary::GetDefaultTreeParams(), FTransform::Identity);
		BindActiveTree();
	}
}

void UTreeParamPanelWidget::HandleApplyClicked()
{
	CommitFromControls();
}

void UTreeParamPanelWidget::HandleSeedClicked()
{
	AParametricTree* Tree = BoundTree.Get();
	if (!Tree)
	{
		HandleSpawnClicked();
		Tree = BoundTree.Get();
		if (!Tree)
		{
			return;
		}
	}
	FTreeParams P = Tree->Params;
	P.RandomSeed = FMath::Rand() % 10000000;
	Tree->ApplyParams(P);
}

void UTreeParamPanelWidget::HandleResetClicked()
{
	if (UTreeGeneratorSubsystem* Subsystem = GetTreeSubsystem())
	{
		if (AParametricTree* Tree = Subsystem->GetActiveTree())
		{
			Tree->ApplyParams(UTreePresetLibrary::GetDefaultTreeParams());
		}
		else
		{
			Subsystem->SpawnTree(UTreePresetLibrary::GetDefaultTreeParams(), FTransform::Identity);
		}
		BindActiveTree();
	}
}

void UTreeParamPanelWidget::HandleCloseClicked()
{
	if (UTreeGeneratorSubsystem* Subsystem = GetTreeSubsystem())
	{
		Subsystem->CloseParamPanel();
	}
}

void UTreeParamPanelWidget::HandleTreeParamsChanged(const FTreeParams&)
{
	if (!bSyncing)
	{
		SyncFromTree();
	}
}

UTreeGeneratorSubsystem* UTreeParamPanelWidget::GetTreeSubsystem() const
{
	const UWorld* World = GetWorld();
	return (World && World->GetGameInstance()) ? World->GetGameInstance()->GetSubsystem<UTreeGeneratorSubsystem>() : nullptr;
}
