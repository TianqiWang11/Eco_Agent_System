#pragma once

#include "CoreMinimal.h"
#include "Subsystems/GameInstanceSubsystem.h"
#include "Engine/World.h"
#include "TreeParams.h"
#include "TreeGeneratorSubsystem.generated.h"

class AParametricTree;
class UTreeParamPanelWidget;

UCLASS()
class TREESIMULATION_API UTreeGeneratorSubsystem : public UGameInstanceSubsystem
{
	GENERATED_BODY()

public:
	virtual void Initialize(FSubsystemCollectionBase& Collection) override;
	virtual void Deinitialize() override;

	UFUNCTION(BlueprintCallable, Category = "TreeSimulation")
	AParametricTree* SpawnTree(const FTreeParams& Params, const FTransform& Transform);

	UFUNCTION(BlueprintCallable, Category = "TreeSimulation")
	void SetActiveTree(AParametricTree* InTree);

	UFUNCTION(BlueprintPure, Category = "TreeSimulation")
	AParametricTree* GetActiveTree() const;

	UFUNCTION(BlueprintCallable, Category = "TreeSimulation")
	void DestroyActiveTree();

	UFUNCTION(BlueprintCallable, Category = "TreeSimulation")
	AParametricTree* SpawnDefaultTree(FVector Location);

	UFUNCTION(BlueprintCallable, Category = "TreeSimulation|面板")
	UTreeParamPanelWidget* OpenParamPanel();

	UFUNCTION(BlueprintCallable, Category = "TreeSimulation|面板")
	void CloseParamPanel();

	UFUNCTION(BlueprintCallable, Category = "TreeSimulation|面板")
	void ToggleParamPanel();

	UFUNCTION(BlueprintPure, Category = "TreeSimulation|面板")
	bool IsParamPanelOpen() const;

private:
	void OnPostWorldInitialization(UWorld* World, const UWorld::InitializationValues InitializationValues);
	void OnGameWorldBeginPlay();

	UPROPERTY()
	TWeakObjectPtr<AParametricTree> ActiveTree;

	UPROPERTY(Transient)
	TWeakObjectPtr<UTreeParamPanelWidget> ParamPanel;

	FDelegateHandle WorldInitHandle;
};
