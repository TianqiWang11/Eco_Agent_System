#include "TreeParams.h"

float FTreeParams::GetCrownVerticalRadius() const
{
	const float A = CrownWidthNS * 0.5f;
	const float B = CrownWidthEW * 0.5f;

	float C = 0.0f;
	if (CrownVolume > 1.0f && A > 0.05f && B > 0.05f)
	{
		C = 3.0f * CrownVolume / (4.0f * PI * A * B);
	}
	else
	{
		C = 0.6f * FMath::Min(A, B) + 0.3f;
	}

	return FMath::Clamp(C, 0.2f, TreeHeight * 0.42f);
}

float FTreeParams::GetCrownBaseHeightResolved() const
{
	if (CrownBaseHeight > 0.01f)
	{
		return FMath::Clamp(CrownBaseHeight, TreeHeight * 0.05f, TreeHeight * 0.92f);
	}
	const float C = GetCrownVerticalRadius();
	const float Base = TreeHeight - 2.0f * C;
	return FMath::Clamp(Base, TreeHeight * 0.08f, TreeHeight * 0.92f);
}

float FTreeParams::GetCrownDepth() const
{
	return TreeHeight - GetCrownBaseHeightResolved();
}

float FTreeParams::GetCrownProjectedArea() const
{
	return PI * 0.25f * CrownWidthNS * CrownWidthEW;
}

int32 FTreeParams::GetEstimatedLeafClusterCount() const
{
	float Volume = CrownVolume;
	if (Volume <= 1.0f)
	{
		Volume = (4.0f / 3.0f) * PI
			* (CrownWidthNS * 0.5f) * (CrownWidthEW * 0.5f) * GetCrownVerticalRadius();
	}

	static constexpr int32 QualityCaps[3] = { 2500, 8000, 15000 };
	const int32 QualityIdx = FMath::Clamp(QualityLevel, 1, 3) - 1;
	const int32 Count = FMath::RoundToInt(Volume * LeafClusterDensity);
	return FMath::Clamp(Count, 100, QualityCaps[QualityIdx]);
}

void FTreeParams::Sanitize()
{
	DBH = FMath::Clamp(DBH, 0.01f, 3.0f);
	TreeHeight = FMath::Clamp(TreeHeight, 0.5f, 120.0f);
	CrownWidthNS = FMath::Clamp(CrownWidthNS, 0.1f, 40.0f);
	CrownWidthEW = FMath::Clamp(CrownWidthEW, 0.1f, 40.0f);
	CrownVolume = FMath::Clamp(CrownVolume, 0.0f, 20000.0f);
	CrownBaseHeight = FMath::Clamp(CrownBaseHeight, 0.0f, TreeHeight * 0.92f);
	TrunkCount = FMath::Clamp(TrunkCount, 1, 12);
	ApicalDominance = FMath::Clamp(ApicalDominance, 0.05f, 1.0f);
	BranchAngle = FMath::Clamp(BranchAngle, 5.0f, 85.0f);
	PrimaryBranchCount = FMath::Clamp(PrimaryBranchCount, 2, 40);
	Taper = FMath::Clamp(Taper, 0.3f, 1.8f);
	LeafClusterDensity = FMath::Clamp(LeafClusterDensity, 1.0f, 300.0f);
	LeafClusterSize = FMath::Clamp(LeafClusterSize, 0.05f, 2.0f);
	QualityLevel = FMath::Clamp(QualityLevel, 1, 3);
	RandomSeed = FMath::Abs(RandomSeed);
}
