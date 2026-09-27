#pragma once

#include "CoreMinimal.h"
#include "TreeTypes.generated.h"

UENUM(BlueprintType)
enum class ETreeArchetype : uint8
{
	Broadleaf UMETA(DisplayName = "阔叶树 Broadleaf"),
	MultiStem UMETA(DisplayName = "丛生/灌木 MultiStem"),
	Liana UMETA(DisplayName = "藤本 Liana（预留）"),
	Palm UMETA(DisplayName = "棕榈 Palm（预留）")
};
