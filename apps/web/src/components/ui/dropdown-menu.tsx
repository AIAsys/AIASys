"use client";

import * as React from "react";
import { Menu } from "@base-ui/react/menu";

import { cn } from "@/lib/utils";

const BaseMenuRoot = Menu.Root;
const BaseMenuTrigger = Menu.Trigger;
const BaseMenuPortal = Menu.Portal;

const DropdownMenuPortal = BaseMenuPortal;
const BaseMenuPopup = Menu.Popup;
const BaseMenuPositioner = Menu.Positioner;
const BaseMenuBackdrop = Menu.Backdrop;
const BaseMenuItem = Menu.Item;
const BaseMenuGroup = Menu.Group;
const BaseMenuGroupLabel = Menu.GroupLabel;
const BaseMenuSeparator = Menu.Separator;
const BaseMenuSubmenuRoot = Menu.SubmenuRoot;
const BaseMenuSubmenuTrigger = Menu.SubmenuTrigger;

function DropdownMenu({
  ...props
}: React.ComponentProps<typeof BaseMenuRoot>) {
  return <BaseMenuRoot data-slot="dropdown-menu" {...props} />;
}

function DropdownMenuTrigger({
  asChild,
  children,
  ...props
}: React.ComponentProps<typeof BaseMenuTrigger> & { asChild?: boolean }) {
  if (asChild) {
    const child = React.isValidElement(children)
      ? children
      : React.Children.only(children);
    if (React.isValidElement(child)) {
      return (
        <BaseMenuTrigger
          data-slot="dropdown-menu-trigger"
          {...props}
          render={(triggerProps) =>
            React.cloneElement(child as React.ReactElement, triggerProps)
          }
        />
      );
    }
  }
  return (
    <BaseMenuTrigger data-slot="dropdown-menu-trigger" {...props}>
      {children}
    </BaseMenuTrigger>
  );
}

const DropdownMenuContent = React.forwardRef<
  React.ElementRef<typeof BaseMenuPopup>,
  React.ComponentPropsWithoutRef<typeof BaseMenuPopup> & {
    sideOffset?: number;
    align?: string;
    side?: string;
  }
>(({ className, sideOffset = 4, align, side, ...props }, ref) => (
  <DropdownMenuPortal>
    <BaseMenuPositioner
      sideOffset={sideOffset}
      align={align as any}
      side={side as any}
      className="z-50"
    >
      <BaseMenuBackdrop className="fixed inset-0 bg-black/50 data-[state=open]:animate-in data-[state=closed]:animate-out data-[state=closed]:fade-out-0 data-[state=open]:fade-in-0" />
      <BaseMenuPopup
        ref={ref}
        data-slot="dropdown-menu-content"
        className={cn(
          "bg-background text-foreground animate-in fade-in-0 zoom-in-95",
          "data-[state=closed]:animate-out data-[state=closed]:fade-out-0 data-[state=closed]:zoom-out-95",
          "border shadow-md rounded-md min-w-40 p-1",
          className,
        )}
        {...props}
      />
    </BaseMenuPositioner>
  </DropdownMenuPortal>
));
DropdownMenuContent.displayName = BaseMenuPopup.displayName;

function DropdownMenuItem({
  className,
  inset,
  ...props
}: React.ComponentProps<typeof BaseMenuItem> & {
  inset?: boolean;
}) {
  return (
    <BaseMenuItem
      data-slot="dropdown-menu-item"
      className={cn(
        "relative flex cursor-pointer select-none items-center rounded-sm px-2 py-1.5 text-sm outline-none",
        "focus:bg-accent focus:text-accent-foreground",
        inset && "pl-8",
        className,
      )}
      {...props}
    />
  );
}

const DropdownMenuLabel = React.forwardRef<
  React.ElementRef<typeof BaseMenuGroupLabel>,
  React.ComponentPropsWithoutRef<typeof BaseMenuGroupLabel>
>(({ className, ...props }, ref) => (
  <BaseMenuGroup
    ref={ref}
    className={cn("px-2 py-1.5 text-sm font-semibold", className)}
    {...props}
  >
    <BaseMenuGroupLabel>{props.children}</BaseMenuGroupLabel>
  </BaseMenuGroup>
));
DropdownMenuLabel.displayName = "DropdownMenuLabel";

const DropdownMenuSeparator = React.forwardRef<
  React.ElementRef<typeof BaseMenuSeparator>,
  React.ComponentPropsWithoutRef<typeof BaseMenuSeparator>
>(({ className, ...props }, ref) => (
  <BaseMenuSeparator
    ref={ref}
    className={cn("-mx-1 my-1 h-px bg-border", className)}
    {...props}
  />
));
DropdownMenuSeparator.displayName = BaseMenuSeparator.displayName;

const DropdownMenuGroup = BaseMenuGroup;

const DropdownMenuSub = BaseMenuSubmenuRoot;

function DropdownMenuSubTrigger({
  className,
  inset,
  ...props
}: React.ComponentProps<typeof BaseMenuSubmenuTrigger> & {
  inset?: boolean;
}) {
  return (
    <BaseMenuSubmenuTrigger
      data-slot="dropdown-menu-sub-trigger"
      className={cn(
        "relative flex cursor-pointer select-none items-center rounded-sm px-2 py-1.5 text-sm outline-none",
        "focus:bg-accent focus:text-accent-foreground data-[state=open]:bg-accent data-[state=open]:text-accent-foreground",
        inset && "pl-8",
        className,
      )}
      {...props}
    />
  );
}

function DropdownMenuSubContent({
  className,
  ...props
}: React.ComponentProps<typeof BaseMenuPopup>) {
  return (
    <BaseMenuPortal>
      <BaseMenuPositioner>
        <BaseMenuPopup
          data-slot="dropdown-menu-sub-content"
          className={cn(
            "z-50 bg-background text-foreground animate-in fade-in-0 zoom-in-95",
            "data-[state=closed]:animate-out data-[state=closed]:fade-out-0 data-[state=closed]:zoom-out-95",
            "border shadow-md rounded-md min-w-40 p-1",
            className,
          )}
          {...props}
        />
      </BaseMenuPositioner>
    </BaseMenuPortal>
  );
}

export {
  DropdownMenu,
  DropdownMenuTrigger,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuLabel,
  DropdownMenuSeparator,
  DropdownMenuGroup,
  DropdownMenuSub,
  DropdownMenuSubTrigger,
  DropdownMenuSubContent,
};
