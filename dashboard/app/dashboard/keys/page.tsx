import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { KeysClient } from "@/components/keys/keys-client";
import { getApiKeys } from "@/lib/heimdall";

export const dynamic = "force-dynamic";

export default async function KeysPage() {
  const { keys } = await getApiKeys();
  return (
    <div className="space-y-6">
      <div>
        <h1 className="text-2xl font-semibold tracking-tight">API keys</h1>
        <p className="text-sm text-muted-foreground">
          Issue Heimdall keys (<code className="font-mono">sk_hd_…</code>) and use
          them as the Bearer token when calling{" "}
          <code className="font-mono">/v1/chat/completions</code>. Every key is
          tenant-scoped — your alerts, costs, and budget all attribute back here.
        </p>
      </div>
      <Card>
        <CardHeader>
          <CardTitle className="text-base">Your keys</CardTitle>
        </CardHeader>
        <CardContent>
          <KeysClient initialKeys={keys} />
        </CardContent>
      </Card>
    </div>
  );
}
