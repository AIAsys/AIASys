"use client"

import * as React from "react"
import { AlertDialog as BaseAlertDialogNamespace } from "@base-ui/react/alert-dialog"

import { cn } from "@/lib/utils"
import { buttonVariants } from "@/components/ui/button"

const BaseAlertDialogRoot = BaseAlertDialogNamespace.Root
const BaseAlertDialogTrigger = BaseAlertDialogNamespace.Trigger
const BaseAlertDialogPortal = BaseAlertDialogNamespace.Portal
const BaseAlertDialogPopup = BaseAlertDialogNamespace.Popup
const BaseAlertDialogBackdrop = BaseAlertDialogNamespace.Backdrop
const BaseAlertDialogTitle = BaseAlertDialogNamespace.Title
const BaseAlertDialogDescription = BaseAlertDialogNamespace.Description
const BaseAlertDialogClose = BaseAlertDialogNamespace.Close

const AlertDialog = BaseAlertDialogRoot

const AlertDialogTrigger = BaseAlertDialogTrigger

const AlertDialogPortal = BaseAlertDialogPortal

const AlertDialogOverlay = React.forwardRef<
  React.ElementRef<typeof BaseAlertDialogBackdrop>,
  React.ComponentPropsWithoutRef<typeof BaseAlertDialogBackdrop>
>(({ className, ...props }, ref) => (
  <BaseAlertDialogBackdrop
    className={cn(
      "fixed inset-0 z-50 bg-black/80 data-[state=open]:animate-in data-[state=closed]:animate-out data-[state=closed]:fade-out-0 data-[state=open]:fade-in-0",
      className
    )}
    {...props}
    ref={ref}
  />
))
AlertDialogOverlay.displayName = BaseAlertDialogBackdrop.displayName

const AlertDialogContent = React.forwardRef<
  React.ElementRef<typeof BaseAlertDialogPopup>,
  React.ComponentPropsWithoutRef<typeof BaseAlertDialogPopup>
>(({ className, ...props }, ref) => {
  React.useEffect(() => {
    return () => {
      const style = window.getComputedStyle(document.body)
      if (
        style.pointerEvents === "none" ||
        style.overflow === "hidden" ||
        style.userSelect === "none" ||
        style.cursor === "wait"
      ) {
        document.body.style.pointerEvents = ""
        document.body.style.overflow = ""
        document.body.style.userSelect = ""
        document.body.style.cursor = ""
      }
    }
  }, [])
  return (
    <AlertDialogPortal>
      <AlertDialogOverlay />
      <BaseAlertDialogPopup
        ref={ref}
        className={cn(
          "fixed left-[50%] top-[50%] z-50 grid w-full max-w-lg translate-x-[-50%] translate-y-[-50%] gap-4 border bg-background p-6 shadow-lg duration-200 data-[state=open]:animate-in data-[state=closed]:animate-out data-[state=closed]:fade-out-0 data-[state=open]:fade-in-0 data-[state=closed]:zoom-out-95 data-[state=open]:zoom-in-95 data-[state=closed]:slide-out-to-left-1/2 data-[state=closed]:slide-out-to-top-[48%] data-[state=open]:slide-in-from-left-1/2 data-[state=open]:slide-in-from-top-[48%] sm:rounded-lg",
          className
        )}
        {...props}
      />
    </AlertDialogPortal>
  )
})
AlertDialogContent.displayName = BaseAlertDialogPopup.displayName

const AlertDialogHeader = ({
  className,
  ...props
}: React.HTMLAttributes<HTMLDivElement>) => (
  <div
    className={cn(
      "flex flex-col space-y-2 text-center sm:text-left",
      className
    )}
    {...props}
  />
)
AlertDialogHeader.displayName = "AlertDialogHeader"

const AlertDialogFooter = ({
  className,
  ...props
}: React.HTMLAttributes<HTMLDivElement>) => (
  <div
    className={cn(
      "flex flex-col-reverse sm:flex-row sm:justify-end sm:space-x-2",
      className
    )}
    {...props}
  />
)
AlertDialogFooter.displayName = "AlertDialogFooter"

const AlertDialogTitle = React.forwardRef<
  React.ElementRef<typeof BaseAlertDialogTitle>,
  React.ComponentPropsWithoutRef<typeof BaseAlertDialogTitle>
>(({ className, ...props }, ref) => (
  <BaseAlertDialogTitle
    ref={ref}
    className={cn("text-lg font-semibold", className)}
    {...props}
  />
))
AlertDialogTitle.displayName = BaseAlertDialogTitle.displayName

const AlertDialogDescription = React.forwardRef<
  React.ElementRef<typeof BaseAlertDialogDescription>,
  React.ComponentPropsWithoutRef<typeof BaseAlertDialogDescription>
>(({ className, ...props }, ref) => (
  <BaseAlertDialogDescription
    ref={ref}
    className={cn("text-sm text-muted-foreground", className)}
    {...props}
  />
))
AlertDialogDescription.displayName = BaseAlertDialogDescription.displayName

function AlertDialogAction({
  className,
  children,
  asChild,
  ...props
}: React.ComponentProps<typeof BaseAlertDialogClose> & {
  className?: string
  asChild?: boolean
}) {
  if (asChild) {
    const child = React.isValidElement(children)
      ? children
      : React.Children.only(children);
    if (React.isValidElement(child)) {
      return (
        <BaseAlertDialogClose
          className={cn(buttonVariants(), className)}
          {...props}
          render={(closeProps) =>
            React.cloneElement(child as React.ReactElement, closeProps)
          }
        />
      );
    }
  }
  return (
    <BaseAlertDialogClose
      className={cn(buttonVariants(), className)}
      {...props}
    >
      {children}
    </BaseAlertDialogClose>
  );
}

function AlertDialogCancel({
  className,
  children,
  ...props
}: React.ComponentProps<typeof BaseAlertDialogClose> & {
  className?: string
}) {
  return (
    <BaseAlertDialogClose
      className={cn(
        buttonVariants({ variant: "outline" }),
        "mt-2 sm:mt-0",
        className
      )}
      {...props}
    >
      {children}
    </BaseAlertDialogClose>
  )
}

export {
  AlertDialog,
  AlertDialogPortal,
  AlertDialogOverlay,
  AlertDialogTrigger,
  AlertDialogContent,
  AlertDialogHeader,
  AlertDialogFooter,
  AlertDialogTitle,
  AlertDialogDescription,
  AlertDialogAction,
  AlertDialogCancel,
}
