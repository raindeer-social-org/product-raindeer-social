"use client";

import { useBrand } from "@/lib/brand-context";
import { PageHeader } from "@/components/ui/PageHeader";
import { Card, CardBody, CardHeader } from "@/components/ui/Card";
import { EmptyState } from "@/components/ui/EmptyState";
import { SocialConnectionsPanel } from "./social-connections-panel";

export default function SocialAccountsPage() {
  const { selectedBrand } = useBrand();

  return (
    <div>
      <PageHeader
        title="Connections"
        description={
          selectedBrand
            ? `Social accounts connected for ${selectedBrand.name}.`
            : "Select a brand to manage its social account connections."
        }
      />

      {!selectedBrand ? (
        <EmptyState title="No brand selected" description="Choose a brand to see its connections." />
      ) : (
        <Card>
          <CardHeader
            title="Where you publish"
            description="Connect a platform below — the OAuth flow opens in this tab and brings you back here once it's authorized. Add, remove or re-authorize any of these any time."
          />
          <CardBody>
            <SocialConnectionsPanel />
          </CardBody>
        </Card>
      )}
    </div>
  );
}
