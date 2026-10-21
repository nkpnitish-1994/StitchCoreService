export type EnvironmentName = "beta" | "production";
export type EnvironmentConfig = {
  name: EnvironmentName; account: string; region: string; apiDesiredCount: number;
  apiCpu: number; apiMemoryMiB: number; deletionProtection: boolean;
  backupRetentionDays: number; logRetentionDays: number;
};
export function environmentConfig(name: string, initialize = false): EnvironmentConfig {
  if (name !== "beta" && name !== "production") throw new Error("Set env=beta or env=production");
  const production = name === "production";
  return {
    name, account: process.env.CDK_DEFAULT_ACCOUNT ?? "", region: "ap-southeast-2",
    apiDesiredCount: initialize ? 0 : production ? 2 : 1,
    apiCpu: 512, apiMemoryMiB: 1024, deletionProtection: production,
    backupRetentionDays: production ? 14 : 3, logRetentionDays: production ? 90 : 14,
  };
}
