#pragma once

#include "CoreMinimal.h"
#include "TreeTypes.h"
#include "TreeParams.generated.h"

USTRUCT(BlueprintType)
struct TREESIMULATION_API FTreeParams
{
	GENERATED_BODY()

	UPROPERTY(EditAnywhere, BlueprintReadWrite, Category = "测量", meta = (ClampMin = "0.01", ClampMax = "3.0"))
	float DBH = 0.2464f;

	UPROPERTY(EditAnywhere, BlueprintReadWrite, Category = "测量", meta = (ClampMin = "0.5", ClampMax = "120"))
	float TreeHeight = 21.94f;

	UPROPERTY(EditAnywhere, BlueprintReadWrite, Category = "测量", meta = (ClampMin = "0.1", ClampMax = "40"))
	float CrownWidthNS = 7.869f;

	UPROPERTY(EditAnywhere, BlueprintReadWrite, Category = "测量", meta = (ClampMin = "0.1", ClampMax = "40"))
	float CrownWidthEW = 7.252f;

	UPROPERTY(EditAnywhere, BlueprintReadWrite, Category = "测量", meta = (ClampMin = "0.0", ClampMax = "20000"))
	float CrownVolume = 173.1f;

	UPROPERTY(EditAnywhere, BlueprintReadWrite, Category = "测量", meta = (ClampMin = "0.0"))
	float CrownBaseHeight = 0.0f;

	UPROPERTY(EditAnywhere, BlueprintReadWrite, Category = "形态")
	ETreeArchetype Archetype = ETreeArchetype::Broadleaf;

	UPROPERTY(EditAnywhere, BlueprintReadWrite, Category = "形态", meta = (ClampMin = "1", ClampMax = "12"))
	int32 TrunkCount = 1;

	UPROPERTY(EditAnywhere, BlueprintReadWrite, Category = "形态", meta = (ClampMin = "0.05", ClampMax = "1.0"))
	float ApicalDominance = 0.6f;

	UPROPERTY(EditAnywhere, BlueprintReadWrite, Category = "形态", meta = (ClampMin = "5", ClampMax = "85"))
	float BranchAngle = 45.0f;

	UPROPERTY(EditAnywhere, BlueprintReadWrite, Category = "形态", meta = (ClampMin = "2", ClampMax = "40"))
	int32 PrimaryBranchCount = 7;

	UPROPERTY(EditAnywhere, BlueprintReadWrite, Category = "形态", meta = (ClampMin = "0.3", ClampMax = "1.8"))
	float Taper = 0.9f;

	UPROPERTY(EditAnywhere, BlueprintReadWrite, Category = "形态", meta = (ClampMin = "1", ClampMax = "300"))
	float LeafClusterDensity = 40.0f;

	UPROPERTY(EditAnywhere, BlueprintReadWrite, Category = "形态", meta = (ClampMin = "0.05", ClampMax = "2.0"))
	float LeafClusterSize = 0.35f;

	UPROPERTY(EditAnywhere, BlueprintReadWrite, Category = "形态")
	int32 RandomSeed = 704236;

	UPROPERTY(EditAnywhere, BlueprintReadWrite, Category = "质量", meta = (ClampMin = "1", ClampMax = "3"))
	int32 QualityLevel = 2;

	float GetCrownVerticalRadius() const;

	float GetCrownBaseHeightResolved() const;

	float GetCrownDepth() const;

	float GetCrownProjectedArea() const;

	int32 GetEstimatedLeafClusterCount() const;

	void Sanitize();
};
