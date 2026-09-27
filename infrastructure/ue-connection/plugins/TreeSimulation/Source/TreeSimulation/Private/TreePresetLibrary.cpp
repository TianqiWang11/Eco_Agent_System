#include "TreePresetLibrary.h"

FTreeParams UTreePresetLibrary::GetPreset_ChenShuiZhang()
{
	FTreeParams P;
	P.DBH = 0.2464f;
	P.TreeHeight = 21.94f;
	P.CrownWidthNS = 7.869f;
	P.CrownWidthEW = 7.252f;
	P.CrownVolume = 173.1f;
	P.CrownBaseHeight = 0.0f;
	P.Archetype = ETreeArchetype::Broadleaf;
	P.TrunkCount = 1;
	P.ApicalDominance = 0.6f;
	P.BranchAngle = 45.0f;
	P.PrimaryBranchCount = 9;
	P.Taper = 0.9f;
	P.LeafClusterDensity = 40.0f;
	P.LeafClusterSize = 0.35f;
	P.RandomSeed = 704236;
	P.QualityLevel = 2;
	return P;
}

FTreeParams UTreePresetLibrary::GetDefaultTreeParams()
{
	return GetPreset_ChenShuiZhang();
}

namespace
{
	struct FTreePresetEntry
	{
		const TCHAR* DisplayName;
		FTreeParams (*Make)();
	};

	const FTreePresetEntry GPresetRegistry[] = {
		{ TEXT("沉水樟 (0704236·2030)"), &UTreePresetLibrary::GetPreset_ChenShuiZhang },
	};
}

TArray<FString> UTreePresetLibrary::GetPresetDisplayNames()
{
	TArray<FString> Names;
	for (const FTreePresetEntry& E : GPresetRegistry)
	{
		Names.Add(E.DisplayName);
	}
	return Names;
}

FTreeParams UTreePresetLibrary::GetPresetByDisplayName(const FString& DisplayName)
{
	for (const FTreePresetEntry& E : GPresetRegistry)
	{
		if (DisplayName == E.DisplayName)
		{
			return E.Make();
		}
	}
	return GetDefaultTreeParams();
}

float UTreePresetLibrary::GetDerivedCrownBaseHeight(const FTreeParams& Params)
{
	return Params.GetCrownBaseHeightResolved();
}

int32 UTreePresetLibrary::GetDerivedLeafClusterCount(const FTreeParams& Params)
{
	return Params.GetEstimatedLeafClusterCount();
}

float UTreePresetLibrary::GetDerivedCrownDepth(const FTreeParams& Params)
{
	return Params.GetCrownDepth();
}
