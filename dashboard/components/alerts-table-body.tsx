"use client";

import { useState } from "react";

import { AlertDrawer } from "@/components/alert-drawer";
import { CategoryBadge } from "@/components/category-badge";
import { LayerBadge } from "@/components/layer-badge";
import { TableBody, TableCell, TableRow } from "@/components/ui/table";
import { absoluteTime, relativeTime, truncate } from "@/lib/format";
import type { Alert } from "@/lib/types";
import { cn } from "@/lib/utils";

export function AlertsTableBody({ alerts }: { alerts: Alert[] }) {
  const [openId, setOpenId] = useState<number | null>(null);

  if (alerts.length === 0) {
    return (
      <TableBody>
        <TableRow>
          <TableCell
            colSpan={6}
            className="text-center text-muted-foreground py-12"
          >
            No alerts match these filters.
          </TableCell>
        </TableRow>
      </TableBody>
    );
  }

  return (
    <>
      <TableBody>
        {alerts.map((a) => (
          <TableRow
            key={a.id}
            tabIndex={0}
            onClick={() => setOpenId(a.id)}
            onKeyDown={(e) => {
              if (e.key === "Enter" || e.key === " ") {
                e.preventDefault();
                setOpenId(a.id);
              }
            }}
            className={cn(
              "align-top cursor-pointer transition-colors",
              "hover:bg-white/[0.03] focus:bg-white/[0.05] focus:outline-none"
            )}
          >
            <TableCell className="font-mono text-xs">
              <div title={absoluteTime(a.timestamp)}>
                {relativeTime(a.timestamp)}
              </div>
              <div className="text-muted-foreground text-[10px]">
                {absoluteTime(a.timestamp)}
              </div>
            </TableCell>
            <TableCell className="font-mono text-xs">
              {a.masked_ip}
              {a.country_code ? (
                <span className="text-[10px] text-muted-foreground ml-1">
                  · {a.country_code}
                </span>
              ) : null}
            </TableCell>
            <TableCell>
              <LayerBadge layer={a.triggered_layer} />
            </TableCell>
            <TableCell>
              <CategoryBadge category={a.owasp_category} />
            </TableCell>
            <TableCell className="font-mono text-xs">
              <div>{a.rule}</div>
              {a.snippet ? (
                <div className="text-muted-foreground text-[10px] mt-0.5">
                  match: {truncate(a.snippet, 60)}
                </div>
              ) : null}
            </TableCell>
            <TableCell className="text-sm">
              <div className="line-clamp-2">{a.blocked_prompt}</div>
              <div className="text-muted-foreground text-[10px] mt-0.5">
                {a.detail ?? ""}
              </div>
            </TableCell>
          </TableRow>
        ))}
      </TableBody>

      <AlertDrawer
        alertId={openId}
        onOpenChange={(open) => {
          if (!open) setOpenId(null);
        }}
      />
    </>
  );
}
