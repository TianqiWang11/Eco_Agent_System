#include "TreeGeneratorSubsystem.h"
#include "ParametricTreeActor.h"
#include "TreeParamPanelWidget.h"
#include "TreePresetLibrary.h"

#include "Blueprint/UserWidget.h"
#include "GameFramework/PlayerController.h"
#include "Engine/GameInstance.h"
#include "HAL/IConsoleManager.h"
#include "Kismet/GameplayStatics.h"

AParametricTree* UTreeGeneratorSubsystem::SpawnTree(const FTreeParams& Params, const FTransform& Transform)
{
	UWorld* World = GetGameInstance() ? GetGameInstance()->GetWorld() : nullptr;
	if (!World)
	{
		UE_LOG(LogTemp, Warning, TEXT("[TreeSimulation] SpawnTree失败：无有效World"));
		return nullptr;
	}

	FActorSpawnParameters SpawnParams;
	SpawnParams.SpawnCollisionHandlingOverride = ESpawnActorCollisionHandlingMethod::AlwaysSpawn;
	AParametricTree* Tree = World->SpawnActor<AParametricTree>(AParametricTree::StaticClass(), Transform, SpawnParams);
	if (Tree)
	{
		Tree->ApplyParams(Params);
		SetActiveTree(Tree);
	}
	return Tree;
}

void UTreeGeneratorSubsystem::SetActiveTree(AParametricTree* InTree)
{
	ActiveTree = InTree;
}

AParametricTree* UTreeGeneratorSubsystem::GetActiveTree() const
{
	return ActiveTree.IsValid() ? ActiveTree.Get() : nullptr;
}

void UTreeGeneratorSubsystem::DestroyActiveTree()
{
	AParametricTree* Tree = GetActiveTree();
	if (Tree)
	{
		Tree->Destroy();
	}
	ActiveTree = nullptr;
}

AParametricTree* UTreeGeneratorSubsystem::SpawnDefaultTree(FVector Location)
{
	return SpawnTree(UTreePresetLibrary::GetPreset_ChenShuiZhang(), FTransform(Location));
}

void UTreeGeneratorSubsystem::Initialize(FSubsystemCollectionBase& Collection)
{
	Super::Initialize(Collection);

	WorldInitHandle = FWorldDelegates::OnPostWorldInitialization.AddUObject(this, &UTreeGeneratorSubsystem::OnPostWorldInitialization);
}

void UTreeGeneratorSubsystem::Deinitialize()
{
	if (WorldInitHandle.IsValid())
	{
		FWorldDelegates::OnPostWorldInitialization.Remove(WorldInitHandle);
	}
	Super::Deinitialize();
}

void UTreeGeneratorSubsystem::OnPostWorldInitialization(UWorld* World, const UWorld::InitializationValues InitializationValues)
{
	if (World && (World->WorldType == EWorldType::PIE || World->WorldType == EWorldType::Game))
	{
		World->OnWorldBeginPlay.AddUObject(this, &UTreeGeneratorSubsystem::OnGameWorldBeginPlay);
	}
}

void UTreeGeneratorSubsystem::OnGameWorldBeginPlay()
{
	// Platform mode: do not cover the streamed forest with the editor demo panel.
}

UTreeParamPanelWidget* UTreeGeneratorSubsystem::OpenParamPanel()
{
	if (ParamPanel.IsValid())
	{
		return ParamPanel.Get();
	}
	UWorld* World = GetGameInstance() ? GetGameInstance()->GetWorld() : nullptr;
	if (!World)
	{
		return nullptr;
	}
	UClass* WidgetClass = LoadObject<UClass>(nullptr, TEXT("/Game/UI/WBP_TreeParamPanel.WBP_TreeParamPanel_C"));
	if (!WidgetClass || !WidgetClass->IsChildOf<UTreeParamPanelWidget>())
	{
		WidgetClass = UTreeParamPanelWidget::StaticClass();
	}
	UTreeParamPanelWidget* Panel = CreateWidget<UTreeParamPanelWidget>(World, WidgetClass);
	if (!Panel)
	{
		return nullptr;
	}
	ParamPanel = Panel;
	Panel->AddToViewport(10);

	if (APlayerController* PC = UGameplayStatics::GetPlayerController(World, 0))
	{
		PC->SetInputMode(FInputModeGameAndUI());
		PC->bShowMouseCursor = true;
	}
	return Panel;
}

void UTreeGeneratorSubsystem::CloseParamPanel()
{
	if (UTreeParamPanelWidget* Panel = ParamPanel.Get())
	{
		Panel->RemoveFromParent();
	}
	ParamPanel = nullptr;

	if (UWorld* World = GetGameInstance() ? GetGameInstance()->GetWorld() : nullptr)
	{
		if (APlayerController* PC = UGameplayStatics::GetPlayerController(World, 0))
		{
			PC->SetInputMode(FInputModeGameOnly());
			PC->bShowMouseCursor = false;
		}
	}
}

void UTreeGeneratorSubsystem::ToggleParamPanel()
{
	if (IsParamPanelOpen())
	{
		CloseParamPanel();
	}
	else
	{
		OpenParamPanel();
	}
}

bool UTreeGeneratorSubsystem::IsParamPanelOpen() const
{
	return ParamPanel.IsValid();
}

static FAutoConsoleCommandWithWorldAndArgs GTreePanelCmd(
	TEXT("Tree.Panel"),
	TEXT("开/关树木参数调试面板"),
	FConsoleCommandWithWorldAndArgsDelegate::CreateLambda([](const TArray<FString>& Args, UWorld* World)
	{
		if (World && World->GetGameInstance())
		{
			if (auto* Subsystem = World->GetGameInstance()->GetSubsystem<UTreeGeneratorSubsystem>())
			{
				Subsystem->ToggleParamPanel();
			}
		}
	}));

static FAutoConsoleCommandWithWorldAndArgs GTreeSpawnDefaultCmd(
	TEXT("Tree.SpawnDefault"),
	TEXT("用沉水樟预设种一棵树。可选参数: X Y Z（默认0 0 0）"),
	FConsoleCommandWithWorldAndArgsDelegate::CreateLambda([](const TArray<FString>& Args, UWorld* World)
	{
		if (!World || !World->GetGameInstance())
		{
			return;
		}
		auto* Subsystem = World->GetGameInstance()->GetSubsystem<UTreeGeneratorSubsystem>();
		if (!Subsystem)
		{
			return;
		}
		FVector Location = FVector::ZeroVector;
		if (Args.Num() >= 3)
		{
			Location = FVector(FCString::Atof(*Args[0]), FCString::Atof(*Args[1]), FCString::Atof(*Args[2]));
		}
		if (AParametricTree* Tree = Subsystem->SpawnDefaultTree(Location))
		{
			UE_LOG(LogTemp, Display, TEXT("[TreeSimulation] Tree.SpawnDefault 已生成: %s @ %s"), *Tree->GetName(), *Location.ToCompactString());
		}
	}));
