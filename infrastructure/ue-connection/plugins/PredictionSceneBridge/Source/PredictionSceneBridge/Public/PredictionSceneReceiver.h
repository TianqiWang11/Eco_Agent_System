#pragma once

#include "CoreMinimal.h"
#include "GameFramework/Actor.h"
#include "Subsystems/WorldSubsystem.h"
#include "PredictionSceneReceiver.generated.h"

class AParametricTree;
class UPixelStreamingInput;

UCLASS(NotBlueprintable, Transient)
class PREDICTIONSCENEBRIDGE_API APredictionSceneReceiver : public AActor
{
    GENERATED_BODY()
public:
    APredictionSceneReceiver();
protected:
    virtual void BeginPlay() override;
    virtual void EndPlay(const EEndPlayReason::Type Reason) override;
private:
    UFUNCTION()
    void HandleInput(const FString& Descriptor);
    void RegisterPixelStreamingHandler();
    AActor* FindSource(const FString& TargetId) const;
    bool Focus(const FString& TargetId);
    void Respond(bool Ok, const FString& Action, const FString& TargetId, const FString& Message) const;

    UPROPERTY(VisibleAnywhere)
    TObjectPtr<USceneComponent> SceneRoot;
    UPROPERTY(VisibleAnywhere)
    TObjectPtr<UPixelStreamingInput> Input;
    TMap<FString, TWeakObjectPtr<AParametricTree>> PredictedTrees;
    TMap<FString, TWeakObjectPtr<AActor>> SourceTrees;
    TMap<FString, bool> OriginalHiddenState;
};

UCLASS()
class PREDICTIONSCENEBRIDGE_API UPredictionSceneWorldSubsystem : public UWorldSubsystem
{
    GENERATED_BODY()
public:
    virtual bool ShouldCreateSubsystem(UObject* Outer) const override;
    virtual void OnWorldBeginPlay(UWorld& World) override;
    virtual void Deinitialize() override;
private:
    UPROPERTY(Transient)
    TObjectPtr<APredictionSceneReceiver> Receiver;
};
