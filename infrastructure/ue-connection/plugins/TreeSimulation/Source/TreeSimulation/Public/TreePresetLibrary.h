#pragma once

#include "CoreMinimal.h"
#include "Kismet/BlueprintFunctionLibrary.h"
#include "TreeParams.h"
#include "TreePresetLibrary.generated.h"

UCLASS()
class TREESIMULATION_API UTreePresetLibrary : public UBlueprintFunctionLibrary
{
	GENERATED_BODY()

public:
	UFUNCTION(BlueprintPure, Category = "TreeSimulation|预设")
	static FTreeParams GetPreset_ChenShuiZhang();

	UFUNCTION(BlueprintPure, Category = "TreeSimulation|预设")
	static FTreeParams GetDefaultTreeParams();

	UFUNCTION(BlueprintPure, Category = "TreeSimulation|预设")
	static TArray<FString> GetPresetDisplayNames();

	UFUNCTION(BlueprintPure, Category = "TreeSimulation|预设")
	static FTreeParams GetPresetByDisplayName(const FString& DisplayName);

	UFUNCTION(BlueprintPure, Category = "TreeSimulation|派生值")
	static float GetDerivedCrownBaseHeight(const FTreeParams& Params);

	UFUNCTION(BlueprintPure, Category = "TreeSimulation|派生值")
	static float GetDerivedCrownDepth(const FTreeParams& Params);

	UFUNCTION(BlueprintPure, Category = "TreeSimulation|派生值")
	static int32 GetDerivedLeafClusterCount(const FTreeParams& Params);
};
