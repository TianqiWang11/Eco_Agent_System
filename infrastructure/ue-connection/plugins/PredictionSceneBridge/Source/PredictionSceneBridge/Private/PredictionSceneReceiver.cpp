#include "PredictionSceneReceiver.h"

#include "Camera/PlayerCameraManager.h"
#include "Async/Async.h"
#include "Components/SceneComponent.h"
#include "Dom/JsonObject.h"
#include "Engine/World.h"
#include "Engine/Engine.h"
#include "Engine/GameInstance.h"
#include "EngineUtils.h"
#include "GameFramework/PlayerController.h"
#include "GameFramework/Pawn.h"
#include "IPixelStreamingModule.h"
#include "IPixelStreamingInputHandler.h"
#include "IPixelStreamingStreamer.h"
#include "Kismet/GameplayStatics.h"
#include "ParametricTreeActor.h"
#include "PixelStreamingInputComponent.h"
#include "Serialization/JsonReader.h"
#include "Serialization/JsonSerializer.h"
#include "TreeGeneratorSubsystem.h"
#include "TreePresetLibrary.h"

namespace
{
bool SafeId(const FString& Value)
{
    if (Value.IsEmpty() || Value.Len() > 64) return false;
    for (TCHAR C : Value)
    {
        if (!FChar::IsAlnum(C) && C != TEXT('_') && C != TEXT('-')) return false;
    }
    return true;
}
bool Measurement(const TSharedPtr<FJsonObject>& Action, const TCHAR* Name, double& Value, double Min, double Max)
{
    return Action->TryGetNumberField(Name, Value) && FMath::IsFinite(Value)
        && Value >= Min && Value <= Max;
}
}

APredictionSceneReceiver::APredictionSceneReceiver()
{
    PrimaryActorTick.bCanEverTick = false;
    SceneRoot = CreateDefaultSubobject<USceneComponent>(TEXT("SceneRoot"));
    RootComponent = SceneRoot;
    Input = CreateDefaultSubobject<UPixelStreamingInput>(TEXT("PixelStreamingInput"));
}

void APredictionSceneReceiver::BeginPlay()
{
    Super::BeginPlay();
    IPixelStreamingModule& PixelStreaming = IPixelStreamingModule::Get();
    if (!PixelStreaming.GetInputComponents().Contains(Input))
    {
        PixelStreaming.AddInputComponent(Input);
    }
    // UE 5.4 dispatches UIInteraction from the WebRTC thread. Runtime-spawned
    // UObject receivers must be invoked on the game thread or their dynamic
    // delegates can be skipped. Preserve the standard message and fan it out
    // to every registered input component on the game thread.
    if (PixelStreaming.IsReady())
    {
        RegisterPixelStreamingHandler();
    }
    else
    {
        PixelStreaming.OnReady().AddWeakLambda(this, [this](IPixelStreamingModule&)
        {
            RegisterPixelStreamingHandler();
        });
    }
    UE_LOG(LogTemp, Display, TEXT("CheBaLing prediction scene receiver is ready (input components=%d)."),
        PixelStreaming.GetInputComponents().Num());
}

void APredictionSceneReceiver::RegisterPixelStreamingHandler()
{
    const TWeakObjectPtr<APredictionSceneReceiver> WeakReceiver(this);
    IPixelStreamingModule::Get().ForEachStreamer([WeakReceiver](TSharedPtr<IPixelStreamingStreamer> Streamer)
    {
        if (TSharedPtr<IPixelStreamingInputHandler> Handler = Streamer->GetInputHandler().Pin())
        {
            Handler->RegisterMessageHandler(TEXT("UIInteraction"), [WeakReceiver](FString PlayerId, FMemoryReader Ar)
            {
                const int32 CharCount = static_cast<int32>(Ar.TotalSize() / sizeof(TCHAR));
                TArray<TCHAR> Buffer;
                Buffer.SetNumUninitialized(CharCount + 1);
                Ar.Serialize(Buffer.GetData(), Ar.TotalSize());
                Buffer[CharCount] = TEXT('\0');
                const FString Raw(Buffer.GetData());
                const FString Descriptor = Raw.Mid(1);
                AsyncTask(ENamedThreads::GameThread, [WeakReceiver, Descriptor]()
                {
                    if (!IPixelStreamingModule::IsAvailable()) return;
                    APredictionSceneReceiver* Receiver = WeakReceiver.Get();
                    if (!IsValid(Receiver) && GEngine)
                    {
                        for (const FWorldContext& Context : GEngine->GetWorldContexts())
                        {
                            UWorld* World = Context.World();
                            if (!World || World->WorldType != EWorldType::Game) continue;
                            FActorSpawnParameters SpawnParameters;
                            SpawnParameters.ObjectFlags |= RF_Transient;
                            SpawnParameters.SpawnCollisionHandlingOverride = ESpawnActorCollisionHandlingMethod::AlwaysSpawn;
                            Receiver = World->SpawnActor<APredictionSceneReceiver>(
                                FVector::ZeroVector, FRotator::ZeroRotator, SpawnParameters);
                            UE_LOG(LogTemp, Display, TEXT("CheBaLing prediction receiver restored after map transition."));
                            break;
                        }
                    }
                    if (IsValid(Receiver)) Receiver->HandleInput(Descriptor);
                    for (UPixelStreamingInput* Component : IPixelStreamingModule::Get().GetInputComponents())
                    {
                        if (IsValid(Component) && (!Receiver || Component != Receiver->Input))
                        {
                            Component->OnInputEvent.Broadcast(Descriptor);
                        }
                    }
                });
            });
        }
    });
    UE_LOG(LogTemp, Display, TEXT("CheBaLing prediction UIInteraction game-thread handler registered."));
}

void APredictionSceneReceiver::EndPlay(const EEndPlayReason::Type Reason)
{
    if (IPixelStreamingModule::IsAvailable())
    {
        IPixelStreamingModule::Get().RemoveInputComponent(Input);
    }
    for (const TPair<FString, TWeakObjectPtr<AActor>>& Pair : SourceTrees)
    {
        if (AActor* Source = Pair.Value.Get())
        {
            Source->SetActorHiddenInGame(OriginalHiddenState.FindRef(Pair.Key));
        }
    }
    Super::EndPlay(Reason);
}

AActor* APredictionSceneReceiver::FindSource(const FString& TargetId) const
{
    for (TActorIterator<AActor> It(GetWorld()); It; ++It)
    {
        AActor* Candidate = *It;
        if (!IsValid(Candidate) || Candidate == this || Candidate->IsA<AParametricTree>()) continue;
        for (const FName& Tag : Candidate->Tags)
        {
            if (Tag.ToString().Equals(TargetId, ESearchCase::IgnoreCase)) return Candidate;
        }
        if (Candidate->GetName().Equals(TargetId, ESearchCase::IgnoreCase)) return Candidate;
    }
    return nullptr;
}

bool APredictionSceneReceiver::Focus(const FString& TargetId)
{
    AParametricTree* Tree = PredictedTrees.FindRef(TargetId).Get();
    APlayerController* Controller = UGameplayStatics::GetPlayerController(this, 0);
    APawn* Pawn = Controller ? Controller->GetPawn() : nullptr;
    if (!IsValid(Tree) || !Controller || !IsValid(Pawn)) return false;

    FVector Origin, Extent;
    Tree->GetActorBounds(true, Origin, Extent);

    // Frame the complete tree from a slightly elevated angle while keeping
    // the possessed pawn as view target, so controls remain available.
    const double HalfHeight = FMath::Max(static_cast<double>(Extent.Z), 100.0);
    const double HalfWidth = FMath::Max(
        static_cast<double>(FMath::Max(Extent.X, Extent.Y)), 100.0);
    const double HorizontalFov = Controller->PlayerCameraManager
        ? Controller->PlayerCameraManager->GetFOVAngle()
        : 90.0;
    constexpr double AspectRatio = 16.0 / 9.0;
    const double HalfHorizontalFov = FMath::DegreesToRadians(
        FMath::Clamp(HorizontalFov * 0.5, 25.0, 60.0));
    const double HalfVerticalFov = FMath::Atan(
        FMath::Tan(HalfHorizontalFov) / AspectRatio);
    const double DistanceForHeight = HalfHeight / FMath::Tan(HalfVerticalFov);
    const double DistanceForWidth = HalfWidth / FMath::Tan(HalfHorizontalFov);
    const double Distance = FMath::Clamp(
        FMath::Max(DistanceForHeight, DistanceForWidth) * 1.25,
        600.0, 8000.0);

    FVector ViewLocation = Pawn->GetActorLocation();
    if (Controller->PlayerCameraManager)
    {
        ViewLocation = Controller->PlayerCameraManager->GetCameraLocation();
    }
    FVector Approach = Origin - ViewLocation;
    Approach.Z = 0.0;
    if (!Approach.Normalize())
    {
        Approach = FVector(1.0, 1.0, 0.0).GetSafeNormal();
    }

    const FVector Base = Origin - FVector(0.0, 0.0, Extent.Z);
    const FVector LookTarget = Base + FVector(0.0, 0.0, Extent.Z * 1.10);
    const FVector CameraLocation = LookTarget - Approach * Distance
        + FVector(0.0, 0.0, Extent.Z * 0.30);
    const FRotator ViewRotation = (LookTarget - CameraLocation).Rotation();
    const FRotator PawnRotation(0.0, ViewRotation.Yaw, 0.0);

    // Recover from older builds that left the controller on a static camera.
    Controller->SetViewTarget(Pawn);
    Pawn->TeleportTo(CameraLocation, PawnRotation, false, true);
    Controller->SetControlRotation(ViewRotation);
    Controller->ResetIgnoreLookInput();
    Controller->ResetIgnoreMoveInput();
    return Controller->GetViewTarget() == Pawn
        && !Controller->IsLookInputIgnored()
        && !Controller->IsMoveInputIgnored();
}

void APredictionSceneReceiver::HandleInput(const FString& Descriptor)
{
    TSharedPtr<FJsonObject> Root;
    if (!FJsonSerializer::Deserialize(TJsonReaderFactory<>::Create(Descriptor), Root) || !Root.IsValid())
    {
        UE_LOG(LogTemp, Error, TEXT("CheBaLing prediction descriptor JSON parsing failed."));
        return;
    }
    FString Channel;
    if (!Root->TryGetStringField(TEXT("channel"), Channel) || Channel != TEXT("chebaling.prediction")) return;
    double Version = 0;
    if (!Root->TryGetNumberField(TEXT("version"), Version) || Version != 1)
    {
        Respond(false, TEXT("unknown"), TEXT(""), TEXT("预测协议版本不受支持"));
        return;
    }
    const TSharedPtr<FJsonObject>* ActionPtr = nullptr;
    if (!Root->TryGetObjectField(TEXT("action"), ActionPtr) || !ActionPtr || !ActionPtr->IsValid()) return;
    const TSharedPtr<FJsonObject>& Action = *ActionPtr;
    FString Type, Id;
    Action->TryGetStringField(TEXT("type"), Type);
    Action->TryGetStringField(TEXT("target_id"), Id);
    UE_LOG(LogTemp, Display, TEXT("CheBaLing prediction command received: action=%s target=%s"), *Type, *Id);
    if (!SafeId(Id))
    {
        Respond(false, Type, Id, TEXT("无效的单木编号"));
        return;
    }
    if (Type == TEXT("focus_prediction"))
    {
        const bool Ok = Focus(Id);
        Respond(Ok, Type, Id, Ok ? TEXT("已聚焦预测树木") : TEXT("当前场景没有该编号的预测树木"));
        return;
    }
    if (Type != TEXT("apply_prediction"))
    {
        Respond(false, Type, Id, TEXT("不支持的预测操作"));
        return;
    }
    double Year, DBH, Height, CrownNS, CrownEW, CrownVolume;
    if (!Measurement(Action, TEXT("year"), Year, 2026, 2100)
        || !Measurement(Action, TEXT("dbh_m"), DBH, 0.01, 3.0)
        || !Measurement(Action, TEXT("tree_height_m"), Height, 0.5, 120.0)
        || !Measurement(Action, TEXT("crown_diameter_ns_m"), CrownNS, 0.1, 40.0)
        || !Measurement(Action, TEXT("crown_diameter_ew_m"), CrownEW, 0.1, 40.0)
        || !Measurement(Action, TEXT("crown_volume_m3"), CrownVolume, 0.0, 20000.0))
    {
        Respond(false, Type, Id, TEXT("预测形态参数超出模型允许范围"));
        return;
    }
    AActor* Source = SourceTrees.FindRef(Id).Get();
    if (!Source) Source = FindSource(Id);
    if (!Source)
    {
        Respond(false, Type, Id, TEXT("UE 场景中找不到该编号；未建立未经校准的坐标映射"));
        return;
    }
    UTreeGeneratorSubsystem* Generator = GetGameInstance()->GetSubsystem<UTreeGeneratorSubsystem>();
    if (!Generator)
    {
        Respond(false, Type, Id, TEXT("参数树插件尚未初始化"));
        return;
    }
    FTreeParams Params = UTreePresetLibrary::GetDefaultTreeParams();
    Params.DBH = static_cast<float>(DBH);
    Params.TreeHeight = static_cast<float>(Height);
    Params.CrownWidthNS = static_cast<float>(CrownNS);
    Params.CrownWidthEW = static_cast<float>(CrownEW);
    Params.CrownVolume = static_cast<float>(CrownVolume);
    Params.RandomSeed = static_cast<int32>(GetTypeHash(Id));
    Params.Sanitize();

    AParametricTree* Tree = PredictedTrees.FindRef(Id).Get();
    if (!Tree)
    {
        FVector Origin, Extent;
        Source->GetActorBounds(true, Origin, Extent);
        const FVector Base = Origin - FVector(0.0, 0.0, Extent.Z);
        Tree = Generator->SpawnTree(Params, FTransform(Source->GetActorRotation(), Base));
        if (!Tree)
        {
            Respond(false, Type, Id, TEXT("UE 参数树生成失败"));
            return;
        }
        Tree->Tags.AddUnique(FName(*Id));
        PredictedTrees.Add(Id, Tree);
        SourceTrees.Add(Id, Source);
        OriginalHiddenState.Add(Id, Source->IsHidden());
        Source->SetActorHiddenInGame(true);
    }
    else
    {
        Tree->ApplyParams(Params);
    }
    bool bFocus = false;
    Action->TryGetBoolField(TEXT("focus"), bFocus);
    if (bFocus) Focus(Id);
    Respond(true, Type, Id, FString::Printf(TEXT("已更新 %s 的 %d 年预测模型"), *Id, static_cast<int32>(Year)));
}

void APredictionSceneReceiver::Respond(bool Ok, const FString& Action, const FString& Id, const FString& Message) const
{
    TSharedRef<FJsonObject> Response = MakeShared<FJsonObject>();
    Response->SetStringField(TEXT("channel"), TEXT("chebaling.ue.control-status"));
    Response->SetBoolField(TEXT("ok"), Ok);
    Response->SetStringField(TEXT("action"), Action);
    Response->SetStringField(TEXT("target_id"), Id);
    Response->SetStringField(TEXT("message"), Message);
    FString Body;
    FJsonSerializer::Serialize(Response, TJsonWriterFactory<>::Create(&Body));
    Input->SendPixelStreamingResponse(Body);
    UE_LOG(LogTemp, Display, TEXT("CheBaLing prediction response: ok=%s action=%s target=%s"),
        Ok ? TEXT("true") : TEXT("false"), *Action, *Id);
}

bool UPredictionSceneWorldSubsystem::ShouldCreateSubsystem(UObject* Outer) const
{
    const UWorld* World = Cast<UWorld>(Outer);
    return World && (World->WorldType == EWorldType::Game || World->WorldType == EWorldType::PIE);
}
void UPredictionSceneWorldSubsystem::OnWorldBeginPlay(UWorld& World)
{
    Super::OnWorldBeginPlay(World);
    FActorSpawnParameters SpawnParameters;
    SpawnParameters.ObjectFlags |= RF_Transient;
    SpawnParameters.SpawnCollisionHandlingOverride = ESpawnActorCollisionHandlingMethod::AlwaysSpawn;
    Receiver = World.SpawnActor<APredictionSceneReceiver>(
        FVector::ZeroVector, FRotator::ZeroRotator, SpawnParameters);
    if (!IsValid(Receiver))
    {
        UE_LOG(LogTemp, Error, TEXT("CheBaLing prediction scene receiver failed to spawn."));
    }
}
void UPredictionSceneWorldSubsystem::Deinitialize()
{
    if (IsValid(Receiver)) Receiver->Destroy();
    Receiver = nullptr;
    Super::Deinitialize();
}
