#pragma once

#include "CoreMinimal.h"
#include "Blueprint/UserWidget.h"
#include "TreeParams.h"
#include "TreeParamPanelWidget.generated.h"

class AParametricTree;
class UButton;
class UComboBoxString;
class UScrollBox;
class USpinBox;
class UTextBlock;
class UTreeGeneratorSubsystem;
class UVerticalBox;

UCLASS(Blueprintable)
class TREESIMULATION_API UTreeParamPanelWidget : public UUserWidget
{
	GENERATED_BODY()

public:
	virtual void NativeConstruct() override;
	virtual void NativeDestruct() override;
	virtual void NativeTick(const FGeometry& MyGeometry, float InDeltaTime) override;

	UPROPERTY(BlueprintReadWrite, meta = (BindWidget), Category = "面板绑定")
	USpinBox* Spin_TreeHeight = nullptr;
	UPROPERTY(BlueprintReadWrite, meta = (BindWidget), Category = "面板绑定")
	USpinBox* Spin_DBH = nullptr;
	UPROPERTY(BlueprintReadWrite, meta = (BindWidget), Category = "面板绑定")
	USpinBox* Spin_CrownNS = nullptr;
	UPROPERTY(BlueprintReadWrite, meta = (BindWidget), Category = "面板绑定")
	USpinBox* Spin_CrownEW = nullptr;
	UPROPERTY(BlueprintReadWrite, meta = (BindWidget), Category = "面板绑定")
	USpinBox* Spin_CrownVolume = nullptr;
	UPROPERTY(BlueprintReadWrite, meta = (BindWidget), Category = "面板绑定")
	USpinBox* Spin_CrownBaseHeight = nullptr;
	UPROPERTY(BlueprintReadWrite, meta = (BindWidget), Category = "面板绑定")
	USpinBox* Spin_RandomSeed = nullptr;
	UPROPERTY(BlueprintReadWrite, meta = (BindWidget), Category = "面板绑定")
	USpinBox* Spin_Quality = nullptr;
	UPROPERTY(BlueprintReadWrite, meta = (BindWidget), Category = "面板绑定")
	USpinBox* Spin_PrimaryBranches = nullptr;
	UPROPERTY(BlueprintReadWrite, meta = (BindWidget), Category = "面板绑定")
	USpinBox* Spin_BranchAngle = nullptr;
	UPROPERTY(BlueprintReadWrite, meta = (BindWidget), Category = "面板绑定")
	USpinBox* Spin_Taper = nullptr;
	UPROPERTY(BlueprintReadWrite, meta = (BindWidget), Category = "面板绑定")
	USpinBox* Spin_ApicalDominance = nullptr;
	UPROPERTY(BlueprintReadWrite, meta = (BindWidget), Category = "面板绑定")
	USpinBox* Spin_LeafDensity = nullptr;
	UPROPERTY(BlueprintReadWrite, meta = (BindWidget), Category = "面板绑定")
	USpinBox* Spin_LeafSize = nullptr;
	UPROPERTY(BlueprintReadWrite, meta = (BindWidget), Category = "面板绑定")
	USpinBox* Spin_TrunkCount = nullptr;

	UPROPERTY(BlueprintReadWrite, meta = (BindWidget), Category = "面板绑定")
	UComboBoxString* Combo_Preset = nullptr;

	UPROPERTY(BlueprintReadWrite, meta = (BindWidget, OptionalWidget = true), Category = "面板绑定")
	UTextBlock* Text_Derived = nullptr;
	UPROPERTY(BlueprintReadWrite, meta = (BindWidget, OptionalWidget = true), Category = "面板绑定")
	UTextBlock* Text_Target = nullptr;

	UPROPERTY(BlueprintReadWrite, meta = (BindWidget, OptionalWidget = true), Category = "面板绑定")
	UButton* BTN_SpawnDefault = nullptr;
	UPROPERTY(BlueprintReadWrite, meta = (BindWidget, OptionalWidget = true), Category = "面板绑定")
	UButton* BTN_Apply = nullptr;
	UPROPERTY(BlueprintReadWrite, meta = (BindWidget, OptionalWidget = true), Category = "面板绑定")
	UButton* BTN_RandomSeed = nullptr;
	UPROPERTY(BlueprintReadWrite, meta = (BindWidget, OptionalWidget = true), Category = "面板绑定")
	UButton* BTN_Reset = nullptr;
	UPROPERTY(BlueprintReadWrite, meta = (BindWidget, OptionalWidget = true), Category = "面板绑定")
	UButton* BTN_Close = nullptr;

private:
	void BuildDefaultUI();
	void BuildParamRows();
	void InitPresetCombo();
	void BindWidgetEvents();

	void CommitFromControls();
	void SyncFromTree();
	void RefreshDerived();
	void BindActiveTree();

	UFUNCTION() void HandleSpinValueChanged(float Value);
	UFUNCTION() void HandleSpinValueCommitted(float Value, ETextCommit::Type CommitType);
	UFUNCTION() void HandlePresetChanged(FString SelectedItem, ESelectInfo::Type SelectionType);
	UFUNCTION() void HandleSpawnClicked();
	UFUNCTION() void HandleApplyClicked();
	UFUNCTION() void HandleSeedClicked();
	UFUNCTION() void HandleResetClicked();
	UFUNCTION() void HandleCloseClicked();
	UFUNCTION() void HandleTreeParamsChanged(const FTreeParams& Params);

	struct FParamRow
	{
		TObjectPtr<USpinBox> Spin;
		TFunction<float(const FTreeParams&)> Get;
		TFunction<void(FTreeParams&, float)> Set;
	};
	TArray<FParamRow> ParamRows;

	bool bSyncing = false;
	bool bCommitQueued = false;
	double LastChangeTime = 0.0;

	TWeakObjectPtr<AParametricTree> BoundTree;

	UTreeGeneratorSubsystem* GetTreeSubsystem() const;
};
