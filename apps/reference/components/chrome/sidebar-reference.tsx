"use client";

/**
 * Sidebar specimen — the app-shell spine from @digithings/ui, live. An in-flow,
 * adjustable panel (drag the edge, arrow keys nudge, double-click resets) that
 * collapses to an icon rail, with a two-level menu whose active row wears the
 * accent edge. Below `md` the same children open in a Sheet. The kit stores
 * nothing: width and open state are props/callbacks, so an app persists them
 * however it likes. Dress is the kit's token utilities (`@digithings/ui/ui`).
 */
import { useState } from "react";
import { GitBranch, LayoutDashboard, PieChart, Settings } from "lucide-react";

import {
  Sidebar,
  SidebarContent,
  SidebarFooter,
  SidebarGroup,
  SidebarGroupContent,
  SidebarGroupLabel,
  SidebarHeader,
  SidebarInset,
  SidebarMenu,
  SidebarMenuButton,
  SidebarMenuItem,
  SidebarMenuSub,
  SidebarMenuSubButton,
  SidebarMenuSubItem,
  SidebarProvider,
  SidebarRail,
  SidebarTrigger,
} from "@digithings/ui/ui";

const SPINE = [
  { label: "Brief", icon: LayoutDashboard },
  { label: "Portfolio", icon: PieChart, children: ["Holdings", "Theses", "Ledger"] },
  { label: "Pipeline", icon: GitBranch },
];

export function SidebarReference() {
  const [active, setActive] = useState("Holdings");
  const [width, setWidth] = useState(240);

  return (
    <section className="section-block" id="sidebar">
      <p className="kicker">{"// sidebar"}</p>
      <h2 className="title">A spine you can resize.</h2>
      <p className="section-copy">
        <code>Sidebar</code> from <code>@digithings/ui</code> is the tool-shaped navigation: a
        persistent panel beside the content, never over it. Drag the edge to set its width (
        <code>{width}px</code> now), collapse it to a rail with the trigger, or focus the edge and
        use the arrow keys. Utilitarian on purpose — hairlines, mono type, one accent edge.
      </p>

      <div className="mt-[1.2rem] border border-hair">
        <SidebarProvider
          className="h-[26rem]"
          width={width}
          onWidthChange={setWidth}
          keyboardShortcut={false}
        >
          <Sidebar className="h-full">
            <SidebarHeader className="h-10 flex-row items-center justify-between border-b border-hair p-0 ps-3 pe-1">
              <span className="font-mono text-[0.8rem] text-ink group-data-[collapsible=icon]:hidden">
                digi<span className="text-accent">quant</span>
              </span>
              <SidebarTrigger />
            </SidebarHeader>
            <SidebarContent>
              <SidebarGroup className="p-0">
                <SidebarGroupLabel>Workspace</SidebarGroupLabel>
                <SidebarGroupContent>
                  <SidebarMenu>
                    {SPINE.map(({ label, icon: Icon, children }) => (
                      <SidebarMenuItem key={label}>
                        <SidebarMenuButton
                          tooltip={label}
                          isActive={!children && active === label}
                          onClick={() => setActive(children ? children[0] : label)}
                        >
                          <Icon />
                          <span>{label}</span>
                        </SidebarMenuButton>
                        {children ? (
                          <SidebarMenuSub>
                            {children.map((c) => (
                              <SidebarMenuSubItem key={c}>
                                <SidebarMenuSubButton
                                  render={<button type="button" />}
                                  isActive={active === c}
                                  onClick={() => setActive(c)}
                                >
                                  <span>{c}</span>
                                </SidebarMenuSubButton>
                              </SidebarMenuSubItem>
                            ))}
                          </SidebarMenuSub>
                        ) : null}
                      </SidebarMenuItem>
                    ))}
                  </SidebarMenu>
                </SidebarGroupContent>
              </SidebarGroup>
            </SidebarContent>
            <SidebarFooter className="border-t border-hair p-0">
              <SidebarMenu>
                <SidebarMenuItem>
                  <SidebarMenuButton tooltip="Settings">
                    <Settings />
                    <span>Settings</span>
                  </SidebarMenuButton>
                </SidebarMenuItem>
              </SidebarMenu>
            </SidebarFooter>
            <SidebarRail />
          </Sidebar>
          <SidebarInset className="p-4 font-mono text-[0.78rem] text-ink-soft">
            Content sits beside the panel — resize it and this column reflows.
          </SidebarInset>
        </SidebarProvider>
      </div>
    </section>
  );
}
