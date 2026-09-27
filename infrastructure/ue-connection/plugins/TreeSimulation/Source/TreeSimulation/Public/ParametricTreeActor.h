#pragma once

#include "CoreMinimal.h"
#include "GameFramework/Actor.h"
#include "TreeParams.h"
#include "ParametricTreeComponent.h"
#include "ParametricTreeActor.generated.h"

DECLARE_DYNAMIC_MULTICAST_DELEGATE_OneParam(FOnTreeParamsChanged, const FTreeParams&, Params);

UCLASS(Blueprintable)
class TREESIMULATION_API AParametricTree : public AActor
{
	GENERATED_BODY()

public:
	AParametricTree();

	UPROPERTY(EditAnywhere, BlueprintReadWrite, Category = "TreeSimulation|参数", meta = (ShowOnlyInnerProperties))
	FTreeParams Params;

	UPROPERTY(EditAnywhere, BlueprintReadWrite, Category = "TreeSimulation|材质")
	TObjectPtr<UMaterialInterface> BarkMaterial;

	UPROPERTY(EditAnywhere, BlueprintReadWrite, Category = "TreeSimulation|材质")
	TObjectPtr<UMaterialInterface> FoliageMaterial;

	UPROPERTY(VisibleAnywhere, BlueprintReadOnly, Category = "TreeSimulation")
	TObjectPtr<UParametricTreeComponent> TreeComponent;

	UPROPERTY(BlueprintAssignable, Category = "TreeSimulation")
	FOnTreeParamsChanged OnParamsChanged;

	UFUNCTION(BlueprintCallable, Category = "TreeSimulation")
	void ApplyParams(const FTreeParams& NewParams);

	virtual void OnConstruction(const FTransform& Transform) override;
	virtual void PostRegisterAllComponents() override;

#if WITH_EDITOR
	virtual void PostEditChangeProperty(FPropertyChangedEvent& PropertyChangedEvent) override;
#endif

private:
	void PushToComponent();

	bool bPendingRebuild = false;
};
