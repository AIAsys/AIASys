"use client";

import * as React from "react";
import { X } from "lucide-react";
import { Dialog as BaseDialogNamespace } from "@base-ui/react/dialog";

import { cn } from "@/lib/utils";

const BaseDialogRoot = BaseDialogNamespace.Root;
const BaseDialogTrigger = BaseDialogNamespace.Trigger;
const BaseDialogClose = BaseDialogNamespace.Close;
const BaseDialogPortal = BaseDialogNamespace.Portal;

const DialogPortal = BaseDialogPortal;
const BaseDialogBackdrop = BaseDialogNamespace.Backdrop;
const BaseDialogPopup = BaseDialogNamespace.Popup;
const BaseDialogTitle = BaseDialogNamespace.Title;
const BaseDialogDescription = BaseDialogNamespace.Description;

function Dialog({
  ...props
}: React.ComponentProps<typeof BaseDialogRoot>) {
  return <BaseDialogRoot data-slot="dialog" {...props} />;
}

function DialogTrigger({
  asChild,
  children,
  ...props
}: React.ComponentProps<typeof BaseDialogTrigger> & { asChild?: boolean }) {
  if (asChild) {
    const child = React.isValidElement(children)
      ? children
      : React.Children.only(children);
    if (React.isValidElement(child)) {
      return (
        <BaseDialogTrigger
          data-slot="dialog-trigger"
          {...props}
          render={(triggerProps) =>
            React.cloneElement(child as React.ReactElement, triggerProps)
          }
        />
      );
    }
  }
  return (
    <BaseDialogTrigger data-slot="dialog-trigger" {...props}>
      {children}
    </BaseDialogTrigger>
  );
}

function DialogClose({
  asChild,
  children,
  ...props
}: React.ComponentProps<typeof BaseDialogClose> & { asChild?: boolean }) {
  if (asChild) {
    const child = React.isValidElement(children)
      ? children
      : React.Children.only(children);
    if (React.isValidElement(child)) {
      return (
        <BaseDialogClose
          data-slot="dialog-close"
          {...props}
          render={(closeProps) =>
            React.cloneElement(child as React.ReactElement, closeProps)
          }
        />
      );
    }
  }
  return (
    <BaseDialogClose data-slot="dialog-close" {...props}>
      {children}
    </BaseDialogClose>
  );
}

const DialogOverlay = React.forwardRef<
  React.ElementRef<typeof BaseDialogBackdrop>,
  React.ComponentPropsWithoutRef<typeof BaseDialogBackdrop>
>(({ className, ...props }, ref) => (
  <BaseDialogBackdrop
    ref={ref}
    className={cn(
      "fixed inset-0 z-50 bg-black/80 data-[state=open]:animate-in data-[state=closed]:animate-out data-[state=closed]:fade-out-0 data-[state=open]:fade-in-0",
      className,
    )}
    {...props}
  />
));
DialogOverlay.displayName = BaseDialogBackdrop.displayName;

const DialogContent = React.forwardRef<
  React.ElementRef<typeof BaseDialogPopup>,
  React.ComponentPropsWithoutRef<typeof BaseDialogPopup> & {
    onEscapeKeyDown?: (event: KeyboardEvent) => void;
    onPointerDownOutside?: (event: PointerEvent) => void;
    onOpenAutoFocus?: (event: Event) => void;
  }
>(({ className, children, onEscapeKeyDown, onPointerDownOutside, onOpenAutoFocus, ...props }, ref) => {
  const internalRef = React.useRef<HTMLDivElement | null>(null);

  React.useEffect(() => {
    if (!onEscapeKeyDown && !onPointerDownOutside) return;

    const handleKeyDown = (event: KeyboardEvent) => {
      if (event.key === "Escape" && onEscapeKeyDown) {
        onEscapeKeyDown(event);
      }
    };

    const handlePointerDownOutside = (event: PointerEvent) => {
      if (onPointerDownOutside) {
        onPointerDownOutside(event);
      }
    };

    document.addEventListener("keydown", handleKeyDown);
    document.addEventListener("pointerdown", handlePointerDownOutside);

    return () => {
      document.removeEventListener("keydown", handleKeyDown);
      document.removeEventListener("pointerdown", handlePointerDownOutside);
    };
  }, [onEscapeKeyDown, onPointerDownOutside]);

  React.useEffect(() => {
    if (!onOpenAutoFocus) return;

    const handleFocus = (event: Event) => {
      onOpenAutoFocus(event);
    };

    const popup = internalRef.current;
    if (popup) {
      popup.addEventListener("focusin", handleFocus as EventListener);
      return () => {
        popup.removeEventListener("focusin", handleFocus as EventListener);
      };
    }
  }, [onOpenAutoFocus]);

  return (
    <BaseDialogPortal>
      <DialogOverlay />
      <BaseDialogPopup
        ref={(node) => {
          internalRef.current = node;
          if (typeof ref === "function") {
            ref(node);
          } else if (ref) {
            ref.current = node;
          }
        }}
        className={cn(
          "fixed left-[50%] top-[50%] z-50 grid w-full max-w-lg translate-x-[-50%] translate-y-[-50%] gap-4 border bg-card p-6 shadow-lg duration-200 data-[state=open]:animate-in data-[state=closed]:animate-out data-[state=closed]:fade-out-0 data-[state=open]:fade-in-0 data-[state=closed]:zoom-out-95 data-[state=open]:zoom-in-95 data-[state=closed]:slide-out-to-left-1/2 data-[state=closed]:slide-out-to-top-[48%] data-[state=open]:slide-in-from-left-1/2 data-[state=open]:slide-in-from-top-[48%] sm:rounded-2xl",
          className,
        )}
        {...props}
      >
        {children}
        <DialogClose className="absolute right-4 top-4 rounded-sm opacity-70 ring-offset-background transition-opacity hover:opacity-100 focus:outline-none focus:ring-2 focus:ring-ring focus:ring-offset-2 disabled:pointer-events-none data-[state=open]:bg-accent data-[state=open]:text-muted-foreground">
          <X className="h-4 w-4" />
          <span className="sr-only">Close</span>
        </DialogClose>
      </BaseDialogPopup>
    </BaseDialogPortal>
  );
});
DialogContent.displayName = BaseDialogPopup.displayName;

const DialogHeader = ({
  className,
  ...props
}: React.HTMLAttributes<HTMLDivElement>) => (
  <div
    className={cn(
      "flex flex-col space-y-1.5 text-center sm:text-left",
      className,
    )}
    {...props}
  />
);
DialogHeader.displayName = "DialogHeader";

const DialogFooter = ({
  className,
  ...props
}: React.HTMLAttributes<HTMLDivElement>) => (
  <div
    className={cn(
      "flex flex-col-reverse sm:flex-row sm:justify-end sm:space-x-2",
      className,
    )}
    {...props}
  />
);
DialogFooter.displayName = "DialogFooter";

const DialogTitle = React.forwardRef<
  React.ElementRef<typeof BaseDialogTitle>,
  React.ComponentPropsWithoutRef<typeof BaseDialogTitle>
>(({ className, ...props }, ref) => (
  <BaseDialogTitle
    ref={ref}
    className={cn(
      "text-lg font-semibold leading-none tracking-tight",
      className,
    )}
    {...props}
  />
));
DialogTitle.displayName = "DialogTitle";

const DialogDescription = React.forwardRef<
  React.ElementRef<typeof BaseDialogDescription>,
  React.ComponentPropsWithoutRef<typeof BaseDialogDescription>
>(({ className, ...props }, ref) => (
  <BaseDialogDescription
    ref={ref}
    className={cn("text-sm text-muted-foreground", className)}
    {...props}
  />
));
DialogDescription.displayName = "DialogDescription";

export {
  Dialog,
  DialogTrigger,
  DialogClose,
  DialogPortal,
  DialogOverlay,
  DialogContent,
  DialogHeader,
  DialogFooter,
  DialogTitle,
  DialogDescription,
};
