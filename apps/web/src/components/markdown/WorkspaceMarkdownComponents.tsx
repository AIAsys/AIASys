import React, { useMemo } from "react";
import type { Components } from "react-markdown";

import { cn } from "@/lib/utils";
import {
  resolveWorkspaceMarkdownReference,
  type WorkspaceMarkdownLinkScope,
} from "@/utils/workspaceMarkdownLinks";

interface WorkspaceMarkdownComponentsOptions {
  currentFileName?: string;
  currentScope?: WorkspaceMarkdownLinkScope;
  onOpenWorkspacePath?: (
    path: string,
    scope: WorkspaceMarkdownLinkScope,
    suffix?: string,
  ) => void;
  resolveWorkspaceImageSrc?: (
    path: string,
    scope: WorkspaceMarkdownLinkScope,
    suffix?: string,
  ) => string | null | undefined;
  baseComponents?: Components;
  linkClassName?: string;
}

type AnchorProps = React.AnchorHTMLAttributes<HTMLAnchorElement> & {
  node?: unknown;
};

type ImageProps = React.ImgHTMLAttributes<HTMLImageElement> & {
  node?: unknown;
};

export function createWorkspaceMarkdownComponents({
  currentFileName,
  currentScope = "workspace",
  onOpenWorkspacePath,
  resolveWorkspaceImageSrc,
  baseComponents,
  linkClassName,
}: WorkspaceMarkdownComponentsOptions): Components {
  const BaseAnchor = baseComponents?.a as
    | React.ComponentType<AnchorProps>
    | undefined;
  const BaseImage = baseComponents?.img as
    | React.ComponentType<ImageProps>
    | undefined;

  const renderImage = (props: ImageProps) => {
    if (BaseImage) {
      return <BaseImage {...props} />;
    }

    const { node: _node, ...domProps } = props;
    return <img {...domProps} />;
  };

  return {
    ...baseComponents,
    a: (props: AnchorProps) => {
      const { href, children, node: _node, onClick, className, ...rest } = props;
      const reference = resolveWorkspaceMarkdownReference(href, {
        currentFileName,
        currentScope,
      });

      if (reference && onOpenWorkspacePath) {
        return (
          <button
            type="button"
            className={cn(
              "inline cursor-pointer break-words p-0 text-left align-baseline text-blue-700 underline underline-offset-2 hover:text-blue-800",
              linkClassName,
              className,
            )}
            title={`打开 ${reference.scope === "global" ? "/global" : "/workspace"}/${reference.path}`}
            onClick={(event) => {
              event.stopPropagation();
              onOpenWorkspacePath(reference.path, reference.scope, reference.suffix);
            }}
            onDoubleClick={(event) => event.stopPropagation()}
            onPointerDown={(event) => event.stopPropagation()}
          >
            {children}
          </button>
        );
      }

      if (BaseAnchor) {
        return <BaseAnchor {...props} />;
      }

      return (
        <a
          href={href}
          className={className}
          onClick={onClick}
          target={href && /^[a-z][a-z0-9+.-]*:/i.test(href) ? "_blank" : undefined}
          rel={href && /^[a-z][a-z0-9+.-]*:/i.test(href) ? "noreferrer" : undefined}
          {...rest}
        >
          {children}
        </a>
      );
    },
    img: (props: ImageProps) => {
      const { src, alt, title, className, ...rest } = props;
      const reference = resolveWorkspaceMarkdownReference(src, {
        currentFileName,
        currentScope,
      });
      const resolvedSrc = reference
        ? resolveWorkspaceImageSrc?.(
            reference.path,
            reference.scope,
            reference.suffix,
          )
        : undefined;

      if (resolvedSrc) {
        return renderImage({
          ...rest,
          src: resolvedSrc,
          alt: alt ?? "",
          title,
          className,
        });
      }

      return renderImage({
        ...rest,
        src,
        alt: alt ?? "",
        title,
        className,
      });
    },
  };
}

export function useWorkspaceMarkdownComponents(
  options: WorkspaceMarkdownComponentsOptions,
): Components {
  const {
    currentFileName,
    currentScope,
    onOpenWorkspacePath,
    resolveWorkspaceImageSrc,
    baseComponents,
    linkClassName,
  } = options;

  return useMemo(
    () =>
      createWorkspaceMarkdownComponents({
        currentFileName,
        currentScope,
        onOpenWorkspacePath,
        resolveWorkspaceImageSrc,
        baseComponents,
        linkClassName,
      }),
    [
      currentFileName,
      currentScope,
      onOpenWorkspacePath,
      resolveWorkspaceImageSrc,
      baseComponents,
      linkClassName,
    ],
  );
}
