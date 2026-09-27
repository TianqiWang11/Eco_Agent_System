using UnrealBuildTool;

public class TreeSimulation : ModuleRules
{
	public TreeSimulation(ReadOnlyTargetRules Target) : base(Target)
	{
		PCHUsage = ModuleRules.PCHUsageMode.NoPCHs;
		bEnableUndefinedIdentifierWarnings = false;
		PublicDefinitions.Add("__has_feature(x)=0");

		PublicDependencyModuleNames.AddRange(new string[]
		{
			"Core",
			"CoreUObject",
			"Engine",
			"GeometryCore",
			"GeometryFramework",
			"UMG"
		});

		PrivateDependencyModuleNames.AddRange(new string[]
		{
			"Slate",
			"SlateCore"
		});
	}
}
