import type { ComponentPropsWithoutRef, MouseEvent } from "react";

import horizontalLockup from "@/assets/branding/aisi-lockup-horizontal.png";
import mark from "@/assets/branding/aisi-mark.png";
import stackedLockup from "@/assets/branding/aisi-lockup-stacked.png";
import wordmark from "@/assets/branding/aisi-wordmark.png";
import { cn } from "@/lib/utils";

const BRAND_IMAGE_BY_VARIANT = {
  lockup: horizontalLockup,
  mark,
  stacked: stackedLockup,
  wordmark,
} as const;

export type BrandLogoVariant = keyof typeof BRAND_IMAGE_BY_VARIANT;

type BrandLogoProps = Omit<ComponentPropsWithoutRef<"img">, "src"> & {
  variant?: BrandLogoVariant;
  href?: string;
  onClick?: ComponentPropsWithoutRef<"a">["onClick"];
};

export function BrandLogo({
  alt = "艾斯",
  className,
  draggable = false,
  variant = "lockup",
  href,
  onClick,
  ...props
}: BrandLogoProps) {
  const img = (
    <img
      src={BRAND_IMAGE_BY_VARIANT[variant]}
      alt={alt}
      draggable={draggable}
      className={cn("block select-none", className)}
      {...props}
    />
  );

  if (href || onClick) {
    return (
      <a
        href={href || "/"}
        onClick={(e) => {
          if (onClick) {
            e.preventDefault();
            onClick(e);
          }
        }}
        className="cursor-pointer"
      >
        {img}
      </a>
    );
  }

  return img;
}

type BrandLockupProps = Omit<ComponentPropsWithoutRef<"div">, "onClick"> & {
  markClassName?: string;
  subtitle?: string;
  subtitleClassName?: string;
  titleClassName?: string;
  href?: string;
  onClick?: ComponentPropsWithoutRef<"div">["onClick"];
};

export function BrandLockup({
  className,
  markClassName,
  subtitle,
  subtitleClassName,
  titleClassName,
  href,
  onClick,
  ...props
}: BrandLockupProps) {
  const content = (
    <>
      <BrandLogo
        variant="mark"
        alt="艾斯图形标志"
        className={cn("h-8 w-8 object-contain", markClassName)}
      />
      <div className="flex min-w-0 flex-col">
        <span
          className={cn(
            "text-[1rem] font-semibold leading-none tracking-[0.12em] text-foreground",
            titleClassName,
          )}
        >
          艾斯
        </span>
        {subtitle ? (
          <span
            className={cn(
              "mt-1 text-[10px] font-medium uppercase leading-none tracking-[0.24em] text-muted-foreground",
              subtitleClassName,
            )}
          >
            {subtitle}
          </span>
        ) : null}
      </div>
    </>
  );

  if (href || onClick) {
    return (
      <a
        href={href || "/"}
        onClick={(e) => {
          if (onClick) {
            e.preventDefault();
            onClick(e as unknown as MouseEvent<HTMLDivElement>);
          }
        }}
        className={cn("inline-flex items-center gap-2.5 cursor-pointer", className)}
      >
        {content}
      </a>
    );
  }

  return (
    <div className={cn("inline-flex items-center gap-2.5", className)} {...props}>
      {content}
    </div>
  );
}
