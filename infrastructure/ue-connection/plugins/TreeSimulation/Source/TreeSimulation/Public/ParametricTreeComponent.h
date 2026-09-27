#pragma once

#include "CoreMinimal.h"
#include "Components/SceneComponent.h"
#include "TreeParams.h"
#include "ParametricTreeComponent.generated.h"

class UDynamicMeshComponent;
class UMaterialInterface;

UCLASS(ClassGroup = (TreeSimulation), meta = (BlueprintSpawnableComponent))
class TREESIMULATION_API UParametricTreeComponent : public USceneComponent
{
	GENERATED_BODY()

public:
	UParametricTreeComponent();

	UFUNCTION(BlueprintCallable, Category = "TreeSimulation")
	void RebuildTree(const FTreeParams& InParams);

	UFUNCTION(BlueprintCallable, Category = "TreeSimulation")
	void SetTreeMaterials(UMaterialInterface* InBarkMaterial, UMaterialInterface* InFoliageMaterial);

	UPROPERTY(EditAnywhere, BlueprintReadWrite, Category = "TreeSimulation|材质")
	TObjectPtr<UMaterialInterface> BarkMaterial;

	UPROPERTY(EditAnywhere, BlueprintReadWrite, Category = "TreeSimulation|材质")
	TObjectPtr<UMaterialInterface> FoliageMaterial;

	UPROPERTY(VisibleAnywhere, BlueprintReadOnly, Category = "TreeSimulation")
	TObjectPtr<UDynamicMeshComponent> BarkMeshComponent;

	UPROPERTY(VisibleAnywhere, BlueprintReadOnly, Category = "TreeSimulation")
	TObjectPtr<UDynamicMeshComponent> FoliageMeshComponent;

private:
	void ApplyMaterialsInternal();
};
