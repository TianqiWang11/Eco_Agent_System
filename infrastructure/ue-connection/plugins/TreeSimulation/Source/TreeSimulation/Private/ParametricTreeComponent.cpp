#include "ParametricTreeComponent.h"

#include "Components/DynamicMeshComponent.h"
#include "DynamicMesh/DynamicMesh3.h"
#include "DynamicMesh/DynamicMeshAttributeSet.h"
#include "DynamicMesh/DynamicMeshOverlay.h"
#include "Materials/Material.h"
#include "MaterialDomain.h"

using UE::Geometry::FDynamicMesh3;
using UE::Geometry::FDynamicMeshAttributeSet;
using UE::Geometry::FDynamicMeshNormalOverlay;
using UE::Geometry::FDynamicMeshUVOverlay;
using UE::Geometry::FDynamicMeshColorOverlay;
using UE::Geometry::FIndex3i;

namespace TreeSim
{
	float Rand01(FRandomStream& S) { return S.FRand(); }
	float RandRange(FRandomStream& S, float Min, float Max) { return Min + (Max - Min) * S.FRand(); }
	int32 RandRangeI(FRandomStream& S, int32 Min, int32 Max) { return Min + (int32)(S.FRand() * (float)(Max - Min + 1)) ; }

	float Gauss(FRandomStream& S)
	{
		const float U = FMath::Max(S.FRand(), 1e-4f);
		const float V = S.FRand();
		return FMath::Sqrt(-2.0f * FMath::Loge(U)) * FMath::Sin(2.0f * PI * V);
	}

	FVector RandomUnitDir(FRandomStream& S)
	{
		const float Z = RandRange(S, -1.0f, 1.0f);
		const float A = RandRange(S, 0.0f, 2.0f * PI);
		const float R = FMath::Sqrt(FMath::Max(0.0f, 1.0f - Z * Z));
		return FVector(R * FMath::Cos(A), R * FMath::Sin(A), Z);
	}

	FVector SphericalDir(float AzDeg, float ElevDeg)
	{
		const float Az = FMath::DegreesToRadians(AzDeg);
		const float El = FMath::DegreesToRadians(ElevDeg);
		const float CE = FMath::Cos(El);
		return FVector(CE * FMath::Cos(Az), CE * FMath::Sin(Az), FMath::Sin(El));
	}

	struct FTubePoint
	{
		FVector Pos = FVector::ZeroVector;
		float Radius = 0.0f;
	};

	struct FCrownShape
	{
		FVector Center = FVector::ZeroVector;
		double A = 1, B = 1, C = 1;

		double Eval(const FVector& P) const
		{
			const double dx = (P.X - Center.X) / A;
			const double dy = (P.Y - Center.Y) / B;
			const double dz = (P.Z - Center.Z) / C;
			return dx * dx + dy * dy + dz * dz;
		}

		FVector SnapToRho(const FVector& P, double Rho) const
		{
			const double E = Eval(P);
			if (E < 1e-9)
			{
				return Center + FVector(Rho * A, 0, 0);
			}
			return Center + (P - Center) * (Rho / FMath::Sqrt(E));
		}

		bool ExitDistance(const FVector& P, const FVector& Dir, double& OutDist) const
		{
			const double ox = (P.X - Center.X) / A, oy = (P.Y - Center.Y) / B, oz = (P.Z - Center.Z) / C;
			const double dx = Dir.X / A, dy = Dir.Y / B, dz = Dir.Z / C;
			const double a = dx * dx + dy * dy + dz * dz;
			const double b = 2.0 * (ox * dx + oy * dy + oz * dz);
			const double c = ox * ox + oy * oy + oz * oz - 1.0;
			if (a < 1e-12)
			{
				return false;
			}
			const double Disc = b * b - 4.0 * a * c;
			if (Disc < 0.0)
			{
				return false;
			}
			const double Sq = FMath::Sqrt(Disc);
			const double T = (-b + Sq) / (2.0 * a);
			if (T <= 0.05)
			{
				return false;
			}
			OutDist = T;
			return true;
		}
	};

	struct FTreeSkeleton
	{
		TArray<TArray<FTubePoint>> MeshedPaths;
		TArray<int32> RadialSegs;
		TArray<FVector> FoliageTips;
		FCrownShape Crown;
	};

	void EnsureVertexAttributes(FDynamicMesh3& Mesh)
	{
		if (!Mesh.HasVertexNormals()) { Mesh.EnableVertexNormals(FVector3f(0, 0, 1)); }
		if (!Mesh.HasVertexUVs()) { Mesh.EnableVertexUVs(FVector2f::ZeroVector); }
		if (!Mesh.HasVertexColors()) { Mesh.EnableVertexColors(FVector3f(1, 1, 1)); }
	}

	void BakeVertexAttrsToOverlays(FDynamicMesh3& Mesh)
	{
		EnsureVertexAttributes(Mesh);
		Mesh.EnableAttributes();
		FDynamicMeshAttributeSet* Attrs = Mesh.Attributes();
		Attrs->SetNumUVLayers(1);
		Attrs->SetNumNormalLayers(1);
		if (!Attrs->HasPrimaryColors()) { Attrs->EnablePrimaryColors(); }

		FDynamicMeshNormalOverlay* NormalOv = Attrs->PrimaryNormals();
		FDynamicMeshUVOverlay* UVOv = Attrs->PrimaryUV();
		FDynamicMeshColorOverlay* ColorOv = Attrs->PrimaryColors();
		if (!NormalOv || !UVOv || !ColorOv)
		{
			return;
		}

		for (int TID : Mesh.TriangleIndicesItr())
		{
			const FIndex3i Tri = Mesh.GetTriangle(TID);

			FVector3f Ns[3], Cs[3];
			FVector2f UVs[3];
			for (int j = 0; j < 3; ++j)
			{
				Ns[j] = Mesh.GetVertexNormal(Tri[j]);
				UVs[j] = Mesh.GetVertexUV(Tri[j]);
				Cs[j] = Mesh.GetVertexColor(Tri[j]);
			}

			NormalOv->SetTriangle(TID, FIndex3i(
				NormalOv->AppendElement(Ns[0]),
				NormalOv->AppendElement(Ns[1]),
				NormalOv->AppendElement(Ns[2])));
			UVOv->SetTriangle(TID, FIndex3i(
				UVOv->AppendElement(UVs[0]),
				UVOv->AppendElement(UVs[1]),
				UVOv->AppendElement(UVs[2])));
			ColorOv->SetTriangle(TID, FIndex3i(
				ColorOv->AppendElement(FVector4f(Cs[0], 1)),
				ColorOv->AppendElement(FVector4f(Cs[1], 1)),
				ColorOv->AppendElement(FVector4f(Cs[2], 1))));
		}
	}

	void AppendTaperedTube(
		FDynamicMesh3& Mesh,
		const TArray<FTubePoint>& Path,
		int32 RadialSegs,
		bool bCapStart,
		bool bCapEnd,
		float UVLengthScale,
		float FluteStrength,
		int32 FluteLobes,
		FRandomStream& RNG,
		const FColor& Tint)
	{
		const int32 N = Path.Num();
		if (N < 2 || RadialSegs < 3)
		{
			return;
		}
		EnsureVertexAttributes(Mesh);

		TArray<FVector> Tangents;
		Tangents.SetNum(N);
		for (int32 i = 0; i < N; ++i)
		{
			FVector T = (i == 0) ? (Path[1].Pos - Path[0].Pos)
				: (i == N - 1) ? (Path[N - 1].Pos - Path[N - 2].Pos)
				: (Path[i + 1].Pos - Path[i - 1].Pos);
			Tangents[i] = (T.SizeSquared() < 1e-10) ? FVector::UpVector : T.GetSafeNormal();
		}

		FVector Ref = (FMath::Abs(Tangents[0].Z) < 0.95) ? FVector::UpVector : FVector(1, 0, 0);
		FVector U = FVector::CrossProduct(Tangents[0], Ref);
		if (U.SizeSquared() < 1e-8) { U = FVector(1, 0, 0); }
		U = U.GetSafeNormal();

		TArray<float> ArcLen;
		ArcLen.SetNum(N);
		ArcLen[0] = 0.0f;
		for (int32 i = 1; i < N; ++i)
		{
			ArcLen[i] = ArcLen[i - 1] + (float)FVector::Dist(Path[i].Pos, Path[i - 1].Pos);
		}
		if (UVLengthScale <= 1.0f)
		{
			UVLengthScale = FMath::Max(ArcLen[N - 1] * 0.5f, 0.5f);
		}

		const float FlutePhase = RandRange(RNG, 0.0f, 2.0f * (float)PI);

		TArray<TArray<int32>> Rings;
		Rings.SetNum(N);
		for (int32 i = 0; i < N; ++i)
		{
			if (i > 0)
			{
				U = U - Tangents[i] * FVector::DotProduct(U, Tangents[i]);
				if (U.SizeSquared() < 1e-8)
				{
					U = FVector::CrossProduct(Tangents[i], FVector::UpVector);
					if (U.SizeSquared() < 1e-8) { U = FVector(1, 0, 0); }
				}
				U = U.GetSafeNormal();
			}
			const FVector W = FVector::CrossProduct(Tangents[i], U).GetSafeNormal();

			Rings[i].Reserve(RadialSegs + 1);
			const float HeightFrac = ArcLen[i] / FMath::Max(ArcLen[N - 1], 1.0f);
			const float RingJitter = RandRange(RNG, 0.92f, 1.06f);
			const float Shade = FMath::Lerp(0.72f, 1.12f, HeightFrac) * RingJitter;
			const FLinearColor VertColor = FLinearColor(Tint) * Shade;

			for (int32 k = 0; k <= RadialSegs; ++k)
			{
				const double Theta = (double)k / (double)RadialSegs * 2.0 * PI;
				const double Cs = FMath::Cos(Theta), Sn = FMath::Sin(Theta);
				double R = Path[i].Radius;
				if (FluteStrength > 0.0 && R > 0.01)
				{
					R *= 1.0 + (double)FluteStrength *
						FMath::Sin((double)FluteLobes * Theta + FlutePhase + Path[i].Pos.Z * 1.7);
				}
				const FVector RadialDir = (U * Cs + W * Sn);
				const FVector Pos = Path[i].Pos + RadialDir * R;

				const int32 VID = Mesh.AppendVertex(FVector3d(Pos));
				Mesh.SetVertexNormal(VID, FVector3f(RadialDir.GetSafeNormal()));
				Mesh.SetVertexUV(VID, FVector2f((float)k / (float)RadialSegs, ArcLen[i] / UVLengthScale));
				Mesh.SetVertexColor(VID, FVector3f(VertColor.R, VertColor.G, VertColor.B));
				Rings[i].Add(VID);
			}
		}

		for (int32 i = 0; i + 1 < N; ++i)
		{
			for (int32 k = 0; k < RadialSegs; ++k)
			{
				const int32 A0 = Rings[i][k];
				const int32 A1 = Rings[i][k + 1];
				const int32 B0 = Rings[i + 1][k];
				const int32 B1 = Rings[i + 1][k + 1];
				Mesh.AppendTriangle(A0, B1, B0);
				Mesh.AppendTriangle(A0, A1, B1);
			}
		}

		if (bCapStart && Path[0].Radius > 0.003)
		{
			const FLinearColor CapColor = FLinearColor(Tint) * 0.6f;
			const int32 C = Mesh.AppendVertex(FVector3d(Path[0].Pos));
			Mesh.SetVertexNormal(C, FVector3f(-Tangents[0]));
			Mesh.SetVertexUV(C, FVector2f(0.5f, 0.0f));
			Mesh.SetVertexColor(C, FVector3f(CapColor.R, CapColor.G, CapColor.B));
			for (int32 k = 0; k < RadialSegs; ++k)
			{
				Mesh.AppendTriangle(C, Rings[0][k + 1], Rings[0][k]);
			}
		}
		if (bCapEnd && Path[N - 1].Radius > 0.003)
		{
			const FLinearColor CapColor = FLinearColor(Tint) * 1.05f;
			const int32 C = Mesh.AppendVertex(FVector3d(Path[N - 1].Pos));
			Mesh.SetVertexNormal(C, FVector3f(Tangents[N - 1]));
			Mesh.SetVertexUV(C, FVector2f(0.5f, 1.0f));
			Mesh.SetVertexColor(C, FVector3f(CapColor.R, CapColor.G, CapColor.B));
			for (int32 k = 0; k < RadialSegs; ++k)
			{
				Mesh.AppendTriangle(C, Rings[N - 1][k], Rings[N - 1][k + 1]);
			}
		}
	}

	float TrunkRadiusAt(const FTreeParams& P, float H, float h, float BaseFlare, float RadiusScale)
	{
		const float R13 = P.DBH * 0.5f * RadiusScale;
		if (h <= 1.3f)
		{
			const float T = (h <= 0.0f) ? 0.0f : h / 1.3f;
			return R13 * FMath::Lerp(BaseFlare, 1.0f, T);
		}
		const float Numer = FMath::Max(H - h, 0.0f);
		const float Denom = FMath::Max(H - 1.3f, 0.1f);
		return FMath::Max(R13 * FMath::Pow(Numer / Denom, (double)P.Taper), 0.012f);
	}

	void BuildTrunkPath(const FTreeParams& P, FRandomStream& RNG, int32 StemIdx, int32 StemCount, TArray<FTubePoint>& OutPath)
	{
		const float H = P.TreeHeight;
		const float R13 = P.DBH * 0.5f;

		const float RadiusScale = (StemCount > 1) ? 1.0f / FMath::Sqrt((float)StemCount) : 1.0f;
		FVector BaseOffset = FVector::ZeroVector;
		FVector LeanDir = FVector::ZeroVector;
		if (StemIdx > 0)
		{
			const float Ang = 2.0f * (float)PI * (float)StemIdx / (float)StemCount + RandRange(RNG, -0.3f, 0.3f);
			BaseOffset = FVector(FMath::Cos(Ang), FMath::Sin(Ang), 0) * FMath::Max(R13, 0.25f) * 0.8f;
			LeanDir = FVector(FMath::Cos(Ang), FMath::Sin(Ang), 0);
		}

		const float BaseFlare = RandRange(RNG, 1.3f, 1.62f);
		const float BendAmp = H * 0.012f * RandRange(RNG, 0.5f, 1.2f);
		const float BendPhaseX = RandRange(RNG, 0.0f, 2.0f * (float)PI);
		const float BendPhaseY = RandRange(RNG, 0.0f, 2.0f * (float)PI);

		const int32 NumRings = FMath::Clamp(FMath::RoundToInt(H * 1.5f * (0.75f + 0.25f * (float)P.QualityLevel)), 14, 56);
		OutPath.Reset(NumRings);
		for (int32 i = 0; i < NumRings; ++i)
		{
			const float h = H * (float)i / (float)(NumRings - 1);
			FVector Pos = BaseOffset;
			if (!LeanDir.IsNearlyZero())
			{
				Pos += LeanDir * (h * FMath::Tan(FMath::DegreesToRadians(6.0f)));
			}
			Pos.X += FMath::Sin(h * 0.33f + BendPhaseX) * BendAmp;
			Pos.Y += FMath::Sin(h * 0.29f + BendPhaseY) * BendAmp;
			Pos.Z = h;

			FTubePoint Pt;
			Pt.Pos = Pos;
			Pt.Radius = TrunkRadiusAt(P, H, h, BaseFlare, RadiusScale);
			OutPath.Add(Pt);
		}
		OutPath.Last().Radius = FMath::Min(OutPath.Last().Radius, 0.02f);
	}

	bool SampleTrunkAt(const TArray<FTubePoint>& Path, float Z, FVector& OutPos, float& OutRadius)
	{
		if (Path.Num() < 2 || Z < Path[0].Pos.Z || Z > Path.Last().Pos.Z)
		{
			return false;
		}
		for (int32 i = 1; i < Path.Num(); ++i)
		{
			if (Z <= Path[i].Pos.Z)
			{
				const float T = (float)((Z - Path[i - 1].Pos.Z) / FMath::Max(Path[i].Pos.Z - Path[i - 1].Pos.Z, 1e-5));
				OutPos = FMath::Lerp(Path[i - 1].Pos, Path[i].Pos, T);
				OutRadius = FMath::Lerp(Path[i - 1].Radius, Path[i].Radius, T);
				return true;
			}
		}
		return false;
	}

	void MakeBranchPath(
		const FVector& Attach, const FVector& End,
		float Droop, float ZigAmp,
		int32 NumPts, float BaseRadius, float TipRadius,
		TArray<FTubePoint>& OutPath, FRandomStream& RNG)
	{
		NumPts = FMath::Max(NumPts, 3);
		OutPath.Reset(NumPts);
		const FVector Dir = End - Attach;
		const float Len = Dir.Size();
		const FVector LateralRef = (FMath::Abs(Dir.Z) < 0.9f) ? FVector::UpVector : FVector(1, 0, 0);
		FVector Lateral = FVector::CrossProduct(Dir, LateralRef).GetSafeNormal();
		if (Lateral.SizeSquared() < 1e-6) { Lateral = FVector(1, 0, 0); }
		const float Phase = RandRange(RNG, 0.0f, 2.0f * (float)PI);
		for (int32 i = 0; i < NumPts; ++i)
		{
			const float S = (float)i / (float)(NumPts - 1);
			FVector Pos = FMath::Lerp(Attach, End, S);
			Pos.Z += Droop * Len * FMath::Sin(S * PI);
			Pos += Lateral * (ZigAmp * Len * FMath::Sin(2.0f * (float)PI * S + Phase) * FMath::Sin(S * PI));
			FTubePoint Pt;
			Pt.Pos = Pos;
			Pt.Radius = FMath::Lerp(BaseRadius, TipRadius, FMath::Pow(S, 0.75));
			OutPath.Add(Pt);
		}
	}

	void BuildBranchesForTrunk(
		const FTreeParams& P,
		FRandomStream& RNG,
		const TArray<FTubePoint>& TrunkPath,
		int32 StemIdx,
		int32 StemCount,
		FTreeSkeleton& Skel)
	{
		const float H = P.TreeHeight;
		const float CrownBase = P.GetCrownBaseHeightResolved();
		const float CrownTop = H * 0.985f;
		const FCrownShape& Crown = Skel.Crown;
		const float MaxA = FMath::Max(Crown.A, Crown.B);
		const float CrownDepth = FMath::Max(CrownTop - CrownBase, 0.5f);

		const int32 TotalPrimaries = FMath::Max(2, P.PrimaryBranchCount / StemCount);
		const float GoldenAngle = 137.508f;
		const float AzOffset = (float)StemIdx * 90.0f;

		const int32 TierCount = FMath::Clamp(FMath::RoundToInt(CrownDepth / 1.7f), 3, 5);
		TArray<float> TierWeights;
		float WeightSum = 0.0f;
		for (int32 t = 0; t < TierCount; ++t)
		{
			const float W = FMath::Lerp(1.3f, 0.7f, (float)t / (float)(TierCount - 1));
			TierWeights.Add(W);
			WeightSum += W;
		}
		TArray<int32> TierCounts;
		int32 Allocated = 0;
		for (int32 t = 0; t < TierCount; ++t)
		{
			const int32 C = FMath::Max(1, FMath::RoundToInt((float)TotalPrimaries * TierWeights[t] / WeightSum));
			TierCounts.Add(C);
			Allocated += C;
		}
		const int32 Remainder = TotalPrimaries - Allocated;
		TierCounts[TierCount / 2] = FMath::Max(1, TierCounts[TierCount / 2] + Remainder);

		int32 BranchGlobalIdx = 0;
		for (int32 t = 0; t < TierCount; ++t)
		{
			const float TierFrac = (TierCount > 1) ? (float)t / (float)(TierCount - 1) : 0.0f;
			const float TierZ = FMath::Lerp(CrownBase + 0.06f * CrownDepth, CrownTop - 0.02f * CrownDepth, TierFrac)
				+ RandRange(RNG, -0.12f, 0.12f) * CrownDepth / (float)TierCount;

			for (int32 b = 0; b < TierCounts[t]; ++b, ++BranchGlobalIdx)
			{
				FVector Attach; float AttachR = 0.05f;
				if (!SampleTrunkAt(TrunkPath, TierZ, Attach, AttachR))
				{
					Attach = FVector(0, 0, TierZ);
				}
				const float HeightFrac = FMath::Clamp((TierZ - CrownBase) / CrownDepth, 0.0f, 1.0f);

				const float Az = (float)BranchGlobalIdx * GoldenAngle + (float)t * 47.0f + AzOffset + RandRange(RNG, -24.0f, 24.0f);
				float Elev = P.BranchAngle * FMath::Lerp(0.85f, 1.55f, HeightFrac) + RandRange(RNG, -7.0f, 7.0f);
				if (t == TierCount - 1 && P.ApicalDominance < 0.6f)
				{
					Elev += RandRange(RNG, 6.0f, 16.0f);
				}
				Elev = FMath::Clamp(Elev, 12.0f, 82.0f);
				const FVector Dir = SphericalDir(Az, Elev);

				double HitDist = 0.5 * MaxA;
				const float LenScale = FMath::Lerp(1.0f, 0.55f, HeightFrac) * RandRange(RNG, 0.82f, 1.08f);
				if (Crown.ExitDistance(Attach, Dir, HitDist))
				{
					HitDist *= LenScale;
				}
				else
				{
					HitDist = 0.5 * MaxA * LenScale;
				}
				const float Len = FMath::Clamp((float)HitDist, 0.4f, 0.95f * MaxA);

				const float Droop = -FMath::Lerp(0.16f, 0.045f, HeightFrac) * RandRange(RNG, 0.7f, 1.3f);
				const float ZigAmp = RandRange(RNG, 0.02f, 0.055f);

				const FVector End = Attach + Dir * Len;
				const float ThickFactor = FMath::Clamp(Len / (0.55f * MaxA), 0.45f, 1.4f);
				const float BaseR = FMath::Clamp(AttachR * 0.24f * ThickFactor, 0.015f, 0.32f);

				TArray<FTubePoint> Path;
				MakeBranchPath(Attach, End, Droop, ZigAmp, 10, BaseR, 0.012f, Path, RNG);
				Skel.MeshedPaths.Add(Path);
				Skel.RadialSegs.Add(7);
				const int32 PathN = Path.Num();

				const int32 SecCount = RandRangeI(RNG, 2, 4);
				for (int32 j = 0; j < SecCount; ++j)
				{
					const float S0 = RandRange(RNG, 0.3f, 0.85f);
					const FVector SecAttach = Path[FMath::Clamp(FMath::RoundToInt(S0 * (PathN - 1)), 0, PathN - 1)].Pos;
					const float SecAz = Az + RandRange(RNG, -80.0f, 80.0f);
					const float SecElev = FMath::Clamp(Elev * FMath::Lerp(1.0f, 0.55f, S0) + RandRange(RNG, -10.0f, 18.0f), -8.0f, 70.0f);
					const FVector SecDir = SphericalDir(SecAz, SecElev);

					float SecLen = Len * FMath::Lerp(0.5f, 0.26f, S0) * RandRange(RNG, 0.8f, 1.15f);
					FVector SecEnd = SecAttach + SecDir * SecLen;
					if (Crown.Eval(SecEnd) > 0.7744)
					{
						SecEnd = Crown.SnapToRho(SecEnd, RandRange(RNG, 0.7f, 0.88f));
					}
					SecLen = (float)FVector::Dist(SecAttach, SecEnd);

					TArray<FTubePoint> SecPath;
					const float SecBaseR = FMath::Clamp(BaseR * 0.42f, 0.008f, 0.1f);
					MakeBranchPath(SecAttach, SecEnd, -SecLen * 0.10f * RandRange(RNG, 0.6f, 1.3f), RandRange(RNG, 0.02f, 0.06f), 6, SecBaseR, 0.006f, SecPath, RNG);
					if (SecBaseR >= 0.011f && SecLen > 0.35f)
					{
						Skel.MeshedPaths.Add(SecPath);
						Skel.RadialSegs.Add(5);
					}
					const int32 SecN = SecPath.Num();

					const int32 TwigCount = RandRangeI(RNG, 3, 5);
					for (int32 tw = 0; tw < TwigCount; ++tw)
					{
						const float ST = RandRange(RNG, 0.45f, 1.0f);
						const FVector TwigAttach = SecPath[FMath::Clamp(FMath::RoundToInt(ST * (SecN - 1)), 0, SecN - 1)].Pos;
						FVector TwigDir = SecDir + RandomUnitDir(RNG) * 0.6f + FVector(0, 0, 0.25f);
						TwigDir.Normalize();
						FVector Tip = TwigAttach + TwigDir * SecLen * RandRange(RNG, 0.25f, 0.45f);
						if (Crown.Eval(Tip) > 0.9409)
						{
							Tip = Crown.SnapToRho(Tip, RandRange(RNG, 0.6f, 0.97f));
						}
						Skel.FoliageTips.Add(Tip);
					}
					Skel.FoliageTips.Add(SecPath.Last().Pos);
				}
			}
		}
	}

	void BuildFoliageMesh(const FTreeParams& P, FRandomStream& RNG, const FTreeSkeleton& Skel, FDynamicMesh3& Mesh)
	{
		EnsureVertexAttributes(Mesh);
		const FCrownShape& Crown = Skel.Crown;
		const int32 TargetCount = P.GetEstimatedLeafClusterCount();
		const float CardSize = P.LeafClusterSize;
		const int32 TipCount = Skel.FoliageTips.Num();

		for (int32 n = 0; n < TargetCount; ++n)
		{
			FVector Pos;
			if (TipCount > 0 && Rand01(RNG) < 0.78f)
			{
				const FVector& Tip = Skel.FoliageTips[RandRangeI(RNG, 0, TipCount - 1)];
				Pos = Tip + FVector(Gauss(RNG), Gauss(RNG), Gauss(RNG)) * 0.42f;
			}
			else
			{
				Pos = Crown.SnapToRho(Crown.Center + RandomUnitDir(RNG) * 1000.0, RandRange(RNG, 0.55f, 0.98f));
			}
			const double E = Crown.Eval(Pos);
			if (E > 1.1) { Pos = Crown.SnapToRho(Pos, RandRange(RNG, 0.6f, 0.98f)); }
			else if (E < 0.16) { Pos = Crown.SnapToRho(Pos, RandRange(RNG, 0.45f, 0.9f)); }

			const float Yaw = RandRange(RNG, 0.0f, 360.0f);
			const float Tilt = FMath::DegreesToRadians(RandRange(RNG, -24.0f, 24.0f));
			const float Scale = CardSize * RandRange(RNG, 0.75f, 1.3f);
			const float Half = Scale * 0.5f;

			const float ShellShade = FMath::Lerp(0.70f, 1.08f, FMath::Clamp((float)FMath::Sqrt(E), 0.0f, 1.0f));
			const FLinearColor Tint = FMath::Lerp(
				FLinearColor(0.16f, 0.26f, 0.08f),
				FLinearColor(0.40f, 0.55f, 0.18f),
				Rand01(RNG)) * ShellShade;

			for (int32 k = 0; k < 3; ++k)
			{
				const float Theta = FMath::DegreesToRadians(Yaw + 60.0f * (float)k);
				FVector Right = FVector(FMath::Cos(Theta), FMath::Sin(Theta), 0) * Half;
				FVector Up = FVector(0, 0, 1);
				Up = Up.RotateAngleAxis(FMath::RadiansToDegrees(Tilt), Right.GetSafeNormal()) * Half;
				const FVector3f CardN = (FVector3f)FVector::CrossProduct(Right, Up).GetSafeNormal();

				const int32 V0 = Mesh.AppendVertex(FVector3d(Pos - Right - Up));
				const int32 V1 = Mesh.AppendVertex(FVector3d(Pos + Right - Up));
				const int32 V2 = Mesh.AppendVertex(FVector3d(Pos + Right + Up));
				const int32 V3 = Mesh.AppendVertex(FVector3d(Pos - Right + Up));

				const FVector3f Col(Tint.R, Tint.G, Tint.B);
				const FVector2f UVs[4] = { FVector2f(0,1), FVector2f(1,1), FVector2f(1,0), FVector2f(0,0) };
				const int32 Vs[4] = { V0, V1, V2, V3 };
				for (int32 v = 0; v < 4; ++v)
				{
					Mesh.SetVertexNormal(Vs[v], CardN);
					Mesh.SetVertexUV(Vs[v], UVs[v]);
					Mesh.SetVertexColor(Vs[v], Col);
				}
				Mesh.AppendTriangle(V0, V1, V2);
				Mesh.AppendTriangle(V0, V2, V3);
			}
		}
	}
}

UParametricTreeComponent::UParametricTreeComponent()
{
	PrimaryComponentTick.bCanEverTick = false;

	BarkMeshComponent = CreateDefaultSubobject<UDynamicMeshComponent>(TEXT("BarkMesh"));
	BarkMeshComponent->SetupAttachment(this);
	BarkMeshComponent->SetMobility(EComponentMobility::Movable);
	BarkMeshComponent->SetCollisionEnabled(ECollisionEnabled::NoCollision);
	BarkMeshComponent->SetCastShadow(true);

	FoliageMeshComponent = CreateDefaultSubobject<UDynamicMeshComponent>(TEXT("FoliageMesh"));
	FoliageMeshComponent->SetupAttachment(this);
	FoliageMeshComponent->SetMobility(EComponentMobility::Movable);
	FoliageMeshComponent->SetCollisionEnabled(ECollisionEnabled::NoCollision);
	FoliageMeshComponent->SetCastShadow(true);
}

void UParametricTreeComponent::ApplyMaterialsInternal()
{
	static UMaterialInterface* CachedBark = []()
	{
		UMaterialInterface* Material = LoadObject<UMaterialInterface>(
			nullptr, TEXT("/TreeSimulation/Materials/M_TreeBark_Default.M_TreeBark_Default"));
		return Material ? Material : LoadObject<UMaterialInterface>(
			nullptr,
			TEXT("/Game/MWBroadleafForest/Materials/Trees/Oak/MTL_BF_TreeOakBark_A.MTL_BF_TreeOakBark_A"));
	}();
	static UMaterialInterface* CachedLeaf = []()
	{
		UMaterialInterface* Material = LoadObject<UMaterialInterface>(
			nullptr, TEXT("/TreeSimulation/Materials/M_TreeLeaf_Default.M_TreeLeaf_Default"));
		return Material ? Material : LoadObject<UMaterialInterface>(
			nullptr,
			TEXT("/Game/MWBroadleafForest/Materials/Trees/MTL_BF_TreeLeavesOak.MTL_BF_TreeLeavesOak"));
	}();

	UMaterialInterface* BarkMat = BarkMaterial
		? BarkMaterial.Get()
		: (CachedBark ? CachedBark : UMaterial::GetDefaultMaterial(MD_Surface));
	UMaterialInterface* LeafMat = FoliageMaterial
		? FoliageMaterial.Get()
		: (CachedLeaf ? CachedLeaf : UMaterial::GetDefaultMaterial(MD_Surface));

	UE_LOG(LogTemp, Display, TEXT("[TreeSimulation] 材质: Bark=%s Leaf=%s"),
		*BarkMat->GetName(), *LeafMat->GetName());

	BarkMeshComponent->SetMaterial(0, BarkMat);
	FoliageMeshComponent->SetMaterial(0, LeafMat);
}

void UParametricTreeComponent::SetTreeMaterials(UMaterialInterface* InBarkMaterial, UMaterialInterface* InFoliageMaterial)
{
	BarkMaterial = InBarkMaterial;
	FoliageMaterial = InFoliageMaterial;
	ApplyMaterialsInternal();
}

void UParametricTreeComponent::RebuildTree(const FTreeParams& InParams)
{
	using namespace TreeSim;

	FTreeParams P = InParams;
	P.Sanitize();
	FRandomStream RNG(P.RandomSeed);

	if (BarkMeshComponent)  { BarkMeshComponent->SetRelativeScale3D(FVector(100.f)); }
	if (FoliageMeshComponent) { FoliageMeshComponent->SetRelativeScale3D(FVector(100.f)); }

	const float CrownBase = P.GetCrownBaseHeightResolved();
	FTreeSkeleton Skel;
	Skel.Crown.Center = FVector(0, 0, (P.TreeHeight + CrownBase) * 0.5f);
	Skel.Crown.A = P.CrownWidthNS * 0.5f;
	Skel.Crown.B = P.CrownWidthEW * 0.5f;
	Skel.Crown.C = FMath::Max((P.TreeHeight - CrownBase) * 0.5f, 0.1f);

	const int32 StemCount = (P.Archetype == ETreeArchetype::MultiStem) ? FMath::Max(1, P.TrunkCount) : 1;
	const FColor BarkTint(0.42f * 255, 0.30f * 255, 0.20f * 255);
	for (int32 StemIdx = 0; StemIdx < StemCount; ++StemIdx)
	{
		TArray<FTubePoint> TrunkPath;
		BuildTrunkPath(P, RNG, StemIdx, StemCount, TrunkPath);
		Skel.MeshedPaths.Add(TrunkPath);
		Skel.RadialSegs.Add(P.QualityLevel >= 3 ? 14 : (P.QualityLevel == 2 ? 10 : 8));
		BuildBranchesForTrunk(P, RNG, TrunkPath, StemIdx, StemCount, Skel);
	}

	FDynamicMesh3 BarkMesh;
	const float BarkUVScale = FMath::Max(P.TreeHeight * 0.35f, 0.8f);
	const int32 FluteLobes = 6;
	for (int32 i = 0; i < Skel.MeshedPaths.Num(); ++i)
	{
		const bool bIsTrunk = (i < StemCount);
		AppendTaperedTube(
			BarkMesh,
			Skel.MeshedPaths[i],
			Skel.RadialSegs[i],
			bIsTrunk,
			true,
			BarkUVScale,
			bIsTrunk ? 0.045f : 0.0f,
			FluteLobes,
			RNG,
			BarkTint);
	}
	if (BarkMeshComponent)
	{
		BakeVertexAttrsToOverlays(BarkMesh);
		BarkMeshComponent->SetMesh(MoveTemp(BarkMesh));
		BarkMeshComponent->NotifyMeshUpdated();
	}

	FDynamicMesh3 FoliageMesh;
	BuildFoliageMesh(P, RNG, Skel, FoliageMesh);
	if (FoliageMeshComponent)
	{
		BakeVertexAttrsToOverlays(FoliageMesh);
		FoliageMeshComponent->SetMesh(MoveTemp(FoliageMesh));
		FoliageMeshComponent->NotifyMeshUpdated();
	}

	ApplyMaterialsInternal();

	UE_LOG(LogTemp, Display,
		TEXT("[TreeSimulation] 重建完成: 枝干路径%d条 干枝三角%d 叶幕三角%d 叶团目标%d 枝下高%.2f"),
		Skel.MeshedPaths.Num(),
		BarkMeshComponent ? BarkMeshComponent->GetMesh()->TriangleCount() : 0,
		FoliageMeshComponent ? FoliageMeshComponent->GetMesh()->TriangleCount() : 0,
		P.GetEstimatedLeafClusterCount(),
		P.GetCrownBaseHeightResolved());
}
