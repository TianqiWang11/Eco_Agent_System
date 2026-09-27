using UnrealBuildTool;

public class PredictionSceneBridge : ModuleRules
{
    public PredictionSceneBridge(ReadOnlyTargetRules Target) : base(Target)
    {
        PCHUsage = PCHUsageMode.NoPCHs;
        bEnableUndefinedIdentifierWarnings = false;
        PublicDefinitions.Add("__has_feature(x)=0");
        PublicDependencyModuleNames.AddRange(new string[] {
            "Core", "CoreUObject", "Engine", "Json", "PixelStreaming", "TreeSimulation"
        });
    }
}
