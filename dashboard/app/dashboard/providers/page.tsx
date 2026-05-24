import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { ProvidersClient } from "@/components/providers/providers-client";
import { getProviders } from "@/lib/heimdall";

export const dynamic = "force-dynamic";

export default async function ProvidersPage() {
  const { providers } = await getProviders();
  return (
    <div className="space-y-6">
      <div>
        <h1 className="text-2xl font-semibold tracking-tight">Upstream providers</h1>
        <p className="text-sm text-muted-foreground">
          Pick which LLM providers Heimdall routes to. Lower priority numbers go
          first; failed providers fall over to the next in line automatically.
          API keys come from environment variables on the Heimdall host (set the
          <code className="mx-1 font-mono">secret_ref</code> field to their name).
        </p>
      </div>
      <Card>
        <CardHeader>
          <CardTitle className="text-base">Configured providers</CardTitle>
        </CardHeader>
        <CardContent>
          <ProvidersClient initial={providers} />
        </CardContent>
      </Card>
    </div>
  );
}
