#include "ParametricTreeActor.h"

AParametricTree::AParametricTree()
{
	PrimaryActorTick.bCanEverTick = false;

	TreeComponent = CreateDefaultSubobject<UParametricTreeComponent>(TEXT("TreeComponent"));
	SetRootComponent(TreeComponent);
}

void AParametricTree::PushToComponent()
{
	if (TreeComponent)
	{
		TreeComponent->SetTreeMaterials(BarkMaterial, FoliageMaterial);
		TreeComponent->RebuildTree(Params);
	}
}

void AParametricTree::ApplyParams(const FTreeParams& NewParams)
{
	Params = NewParams;
	PushToComponent();
	OnParamsChanged.Broadcast(Params);
}

void AParametricTree::OnConstruction(const FTransform& Transform)
{
	Super::OnConstruction(Transform);
	bPendingRebuild = true;
}

void AParametricTree::PostRegisterAllComponents()
{
	Super::PostRegisterAllComponents();
	if (bPendingRebuild)
	{
		bPendingRebuild = false;
		PushToComponent();
	}
}

#if WITH_EDITOR
void AParametricTree::PostEditChangeProperty(FPropertyChangedEvent& PropertyChangedEvent)
{
	Super::PostEditChangeProperty(PropertyChangedEvent);
	PushToComponent();
}
#endif
